"""An authenticated Club checkpoint takes precedence over any local weekend."""
import base64
import gzip
import hashlib
import io
from pathlib import Path
import os
import tempfile
from .integrity_rules import compare


def _game_modules():
    from acr_daily import rallyweekend,saveslot
    return rallyweekend,saveslot


def _report(raw):
    from . import integrity
    return integrity.report_from_save(raw)


def restore(api,event,player_id,state,log):
    recovery=bool(state.get('recoveryRequired'))
    if recovery and state['status']=='registered' and state['stage_index']==0:
        return None  # Rebuild the canonical calendar; do not store a save before OS1.
    if state['status']!='ready' and not (recovery and state['status']=='registered'): return None
    idx=state['stage_index']
    if type(idx) is not int or not 0<=idx<len(event['stages']) or (idx==0 and not recovery):
        raise RuntimeError('Nieprawidłowy postęp rajdu na serwerze; zapis nie został zmieniony')
    if not event.get('allowBreaks',True):
        raise RuntimeError('Rajd wymaga jazdy na raz; nie można przywrócić przerwy')
    # Legacy events allowed unchanged local continuation outside service. They
    # cannot have a server checkpoint there; preserve that existing behavior.
    if not recovery and not event['stages'][idx].get('serviceBefore',False) and event.get('launcherProtocol')!='0.2.4':
        return None
    checkpoint=api.call('/api/recovery-checkpoint' if recovery else '/api/checkpoint')
    if not checkpoint.get('available'):
        if recovery and idx==0: return None  # A fresh canonical calendar is safe before any stage.
        if recovery:
            raise RuntimeError('Brak zatwierdzonej kopii przed kolejnym OS-em. Podejście i wyniki zachowane; skontaktuj się z administratorem. Nie odtwarzam OS1 ani postępu z samych czasów.')
        if event.get('launcherProtocol')=='0.2.4':
            raise RuntimeError('Brak zatwierdzonej kopii przerwy na serwerze. Nie odtwarzam postępu z prywatnego Rally Weekend; skontaktuj się z administratorem.')
        log('Starszy rajd: brak kopii na serwerze. Wznowienie wymaga oryginalnego, niezmienionego lokalnego zapisu Club.')
        return None
    if checkpoint.get('playerId')!=player_id or checkpoint.get('eventId')!=event['id'] or checkpoint.get('stageIndex')!=idx:
        log('OSTRZEŻENIE: ID gracza, rajdu lub OS-u kopii nie zgadza się z RUN. Ponownie sprawdzam właściwą kopię; lokalny zapis pozostaje bez zmian.')
        checkpoint=api.call('/api/recovery-checkpoint' if recovery else '/api/checkpoint')
        if not checkpoint.get('available') or checkpoint.get('playerId')!=player_id or checkpoint.get('eventId')!=event['id'] or checkpoint.get('stageIndex')!=idx:
            raise RuntimeError('Kopia nie odpowiada temu graczowi, rajdowi lub OS-owi; zamknij grę i launcher, następnie ponów RUN. Zapis nie został zmieniony')
    packed=checkpoint.get('save')
    if not isinstance(packed,str) or len(packed)>2*1024*1024*4//3+8:
        raise RuntimeError('Nieprawidłowy rozmiar kopii zapisu')
    try:
        compressed=base64.b64decode(packed,validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source:
            raw=source.read(4*1024*1024+1)
    except (ValueError,OSError,EOFError) as exc:
        raise RuntimeError('Nie można odczytać kopii zapisu z serwera') from exc
    if not raw or len(raw)>4*1024*1024 or hashlib.sha256(raw).hexdigest()!=checkpoint.get('digest'):
        raise RuntimeError('Nieprawidłowa suma kontrolna kopii; zapis nie został zmieniony')
    baseline=checkpoint.get('baseline')
    if not isinstance(baseline,dict) or len(str(baseline))>256000 or any(not isinstance(k,str) or type(v) is not int or not 0<=v<=10000 for k,v in baseline.items()):
        raise RuntimeError('Nieprawidłowa baza wyników kopii')
    rallyweekend,saveslot=_game_modules()
    if compare(event,_report(raw)):
        raise RuntimeError('Kopia ma inne ustawienia rajdu; zapis nie został zmieniony')
    progress=rallyweekend.progress(raw)
    if (idx and (not progress or progress.get('done')!=idx)) or (not idx and progress and progress.get('done',0)!=0):
        raise RuntimeError('Kopia nie zawiera postępu przed właściwym OS-em; zapis nie został zmieniony')
    if saveslot.game_running():
        raise RuntimeError('Zamknij ACR przed przywróceniem kopii Club')
    # replace() backs up the current local save, including a private weekend,
    # before atomically installing the authenticated checkpoint. No local save
    # parsing or local-session prerequisite is needed for a server restore.
    target=Path(saveslot.SAVE)
    if target.exists():
        saveslot.replace(raw)
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as out:
            temporary=Path(out.name);out.write(raw)
        try: os.replace(temporary,target)
        finally: temporary.unlink(missing_ok=True)
    log(f'Przywrócono osobistą kopię Club z serwera przed OS {idx+1}; lokalny Rally Weekend nie ma pierwszeństwa.')
    if recovery:
        api.call('/api/recovery-ack',{'digest':checkpoint['digest'],'settings':_report(raw)})
    return {'eventId':event['id'],'playerId':player_id,'baseline':baseline}
