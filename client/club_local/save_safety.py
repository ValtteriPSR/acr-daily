"""Protected, stage-start-confirmed good copies, quarantine and atomic writes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid
from . import save_layout

def directory():
    path=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'ACR Rally Club'/'save-safety'
    path.mkdir(parents=True,exist_ok=True);return path

def digest(raw):return hashlib.sha256(raw).hexdigest()

def read_file(path):
    with Path(path).open('rb') as f:raw=f.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise save_layout.InvalidSave('Zapis przekracza bezpieczny limit 4 MB. Zachowaj oryginał; RUN wstrzymany.')
    return raw

def state():
    p=directory()/'state.json'
    if not p.exists():return {}
    try:return json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError):raise save_layout.InvalidSave('Uszkodzone metadane odzyskiwania; RUN wstrzymany.')

def record(data):
    atomic(directory()/'state.json',json.dumps(data,ensure_ascii=False,indent=2).encode())

def atomic(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        temporary=Path(f.name);f.write(raw);f.flush();os.fsync(f.fileno())
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)

def archive(raw,kind):
    p=directory()/(kind+'-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.sav')
    atomic(p,raw)
    if kind in ('before-run','quarantine'):
        for old in sorted(directory().glob(kind+'-*.sav'))[:-15]:old.unlink()
    return str(p)

def block(reason,raw=None):
    meta=state();meta['blocked']=str(reason);meta['blockedAt']=time.time()
    if raw is not None:
        meta['quarantine']=archive(raw,'quarantine');meta['badDigest']=digest(raw)
        meta['rejectedDigests']=list(dict.fromkeys(meta.get('rejectedDigests',[])+[digest(raw)]))[-50:]
    record(meta)

def ensure_run_allowed():
    meta=state()
    if meta.get('blocked') or meta.get('pending'):raise save_layout.InvalidSave('RUN wstrzymany. Przy awarii przywróć potwierdzoną kopię, zrestartuj launcher i grę, następnie uruchom prywatny OS z otwartym launcherem.')
    if not meta.get('good'):raise save_layout.InvalidSave(FIRST_WEEKEND_MESSAGE)
    try:
        good=meta['good']
        if digest(read_file(good['path']))!=good['digest']:raise ValueError('Checksum')
    except (OSError,KeyError,ValueError):raise save_layout.InvalidSave('Chroniona kopia jest niedostępna lub została zmieniona. RUN wstrzymany; uruchom prywatny OS z otwartym launcherem.')

def preflight():
    from acr_daily import saveslot
    ensure_run_allowed()
    path=Path(saveslot.SAVE)
    try:raw=read_file(path);save_layout.inspect(raw)
    except (OSError,ValueError) as exc:
        block(str(exc),raw if 'raw' in locals() else None);raise
    if digest(raw) in state().get('rejectedDigests',[]):raise save_layout.InvalidSave('Ten zapis został zgłoszony jako wadliwy. RUN wstrzymany.')
    return raw

def replace(raw,expected_source_digest=None):
    from acr_daily import saveslot
    ensure_run_allowed()
    if saveslot.game_running():raise save_layout.InvalidSave('Zamknij ACR przed podmianą zapisu.')
    save_layout.inspect(raw);path=Path(saveslot.SAVE)
    if path.exists():
        original=read_file(path)
        try:save_layout.inspect(original)
        except ValueError as exc:block(str(exc),original);raise
        if expected_source_digest and digest(original)!=expected_source_digest:raise save_layout.InvalidSave('Zapis zmienił się podczas przygotowania. Podmiana anulowana.')
        backup=archive(original,'before-run')
    else:backup=None
    # Persist an unconfirmed transaction before installing the new bytes. A
    # crash/kill cannot clear its recovery marker by skipping a final write.
    meta=state();meta.update(pending={'digest':digest(raw),'backup':backup,'created':time.time()})
    record(meta)
    if saveslot.game_running():raise save_layout.InvalidSave('Gra uruchomiła się w trakcie przygotowania. Podmiana anulowana.')
    if (backup is not None and (not path.exists() or digest(read_file(path))!=digest(original))) or (backup is None and path.exists()):raise save_layout.InvalidSave('Zapis zmienił się tuż przed podmianą. RUN wstrzymany; sprawdź grę i potwierdź kopię.')
    atomic(path,raw)
    if digest(path.read_bytes())!=digest(raw):
        block('Nie udało się potwierdzić podmiany zapisu.');raise save_layout.InvalidSave('Błąd podmiany zapisu')

def confirm_good():
    from acr_daily import saveslot
    if saveslot.game_running():raise save_layout.InvalidSave('Po sprawdzeniu działania zamknij grę, następnie potwierdź kopię.')
    raw=read_file(saveslot.SAVE);save_layout.inspect(raw)
    meta=state()
    if digest(raw) in meta.get('rejectedDigests',[]):raise save_layout.InvalidSave('Ten plik zgłoszono jako wadliwy. Przywróć inny sprawdzony zapis i pozwól grze go zapisać przed potwierdzeniem.')
    # Confirmation is an explicit user assertion after a successful game test,
    # never inferred from a parser check or a changed timestamp.
    p=archive(raw,'confirmed-good')
    meta.update(good={'path':p,'digest':digest(raw),'confirmedAt':time.time()})
    meta['confirmedCopies']=meta.get('confirmedCopies',[])+[meta['good']]
    for k in ['blocked','blockedAt','badDigest','pending']:meta.pop(k,None)
    record(meta);return p

def restore_previous():
    from acr_daily import saveslot
    if saveslot.game_running():raise save_layout.InvalidSave('Zamknij ACR przed przywróceniem kopii.')
    meta=state();candidates=meta.get('confirmedCopies') or ([meta['good']] if meta.get('good') else [])
    good=next((x for x in reversed(candidates) if x['digest'] not in meta.get('rejectedDigests',[])),None)
    # A before-RUN file is not automatically considered a known-good file.
    if not good:raise save_layout.InvalidSave('Brak kopii potwierdzonej działaniem gry. Zachowane kopie robocze są w: '+str(directory())+'. Przywróć sprawdzony zapis ręcznie i uruchom prywatny OS z otwartym launcherem.')
    raw=read_file(good['path'])
    if digest(raw)!=good['digest']:raise save_layout.InvalidSave('Kopia potwierdzona ma inną sumę kontrolną.')
    save_layout.inspect(raw)
    if digest(raw) in meta.get('rejectedDigests',[]):raise save_layout.InvalidSave('Ta kopia została zgłoszona jako wadliwa. Wymagana inna, sprawdzona kopia.')
    path=Path(saveslot.SAVE)
    if path.exists():archive(read_file(path),'quarantine')
    # Restore stays locked. It never invokes RUN or launches the game.
    meta['blocked']='Przywrócono kopię. Zrestartuj launcher i grę; uruchom prywatny OS z otwartym launcherem.'
    meta['restartRequired']=True
    meta['restoreProcess']=os.getpid()
    meta.pop('pending',None);record(meta);atomic(path,raw)
    return good['path']

def report_crash():
    from acr_daily import saveslot
    if saveslot.game_running():raise save_layout.InvalidSave('Zamknij grę przed zgłoszeniem awarii zapisu.')
    path=Path(saveslot.SAVE)
    try:raw=read_file(path) if path.exists() else None
    except save_layout.InvalidSave:raw=None
    block('Użytkownik zgłosił awarię przy wczytywaniu zapisu.',raw)

def self_test():
    """Frozen Windows EXE: real atomic writes, isolated from the player's files."""
    from acr_daily import saveslot
    import struct
    def sf(s):return struct.pack('<i',len(s)+1)+s.encode()+b'\0'
    header=bytearray(96);header[86]=1  # Supported light-penalty rule.
    stage=sf('GreeceS1TestForward')
    calendar=sf('GreeceWeekendShort')+struct.pack('<ii',1,0)+stage+bytes(84)+sf('NoZone')+bytes(24)
    settings=bytes(header)+calendar
    component=sf('RaceEventRaceSettingsRallyWeekendComponent')+struct.pack('<i',len(settings))+settings
    body=struct.pack('<i',1)+sf('DefaultRally')+struct.pack('<i',1)+sf('ERaceEventSerializableContext::RaceEventSettings')+struct.pack('<ii',0,1)+component+stage+sf('VWPoloGTIR5')+struct.pack('<i',0)+bytes(32)
    raw=b'GVAS'+bytes(16)+b'PlayerSaveGameData\0'+struct.pack('<i',len(body))+body
    old_dir=globals()['directory'];old_save=saveslot.SAVE;old_running=saveslot.game_running
    try:
        with tempfile.TemporaryDirectory() as temp:
            globals()['directory']=lambda:Path(temp)
            saveslot.SAVE=str(Path(temp)/'synthetic.sav');saveslot.game_running=lambda:False
            from types import SimpleNamespace
            frames=iter(SimpleNamespace(clock_ms=n,track='Synthetic stage',car='Synthetic car') for n in (0,100,200))
            observer=StageStartObserver(lambda message:None,SimpleNamespace(read=lambda:next(frames),close=lambda:None))
            Path(saveslot.SAVE).write_bytes(raw)
            for _ in range(3):observer.poll()
            assert (Path(temp)/'Master.sav').read_bytes()==raw
            ensure_run_allowed()
            changed=raw[:-1]+b'\1';replace(changed)
            try:ensure_run_allowed()
            except save_layout.InvalidSave:pass
            else:raise AssertionError('Unconfirmed write did not block RUN')
            report_crash();restore_previous()
            assert Path(saveslot.SAVE).read_bytes()==raw
            # Model a restarted EXE in the isolated self-test, then a new SS.
            meta=state();meta['restoreProcess']=-1;record(meta)
            frames=iter(SimpleNamespace(clock_ms=n,track='Synthetic stage',car='Synthetic car') for n in (0,100,200))
            observer=StageStartObserver(lambda message:None,SimpleNamespace(read=lambda:next(frames),close=lambda:None))
            for _ in range(3):observer.poll()
            ensure_run_allowed()
    finally:
        globals()['directory']=old_dir;saveslot.SAVE=old_save;saveslot.game_running=old_running


FIRST_WEEKEND_MESSAGE = 'ustaw w grze dowolny Rally Weekend, uruchom pierwszy OS (nie musisz kończyć), wyjdź z gry i ponownie kliknij RUN.'

def has_weekend():
    from acr_daily import saveslot
    try:
        report,_=save_layout.rally_report(read_file(saveslot.SAVE))
        return bool(report['stages'])
    except (OSError,ValueError):return False

def needs_stage_proof():
    try:ensure_run_allowed();return False
    except save_layout.InvalidSave:return True

def confirm_stage_start():
    """Only StageStartObserver may call this after a fresh, advancing clock.

    Reading twice refuses an in-flight game write. No writes to the game's SAV.
    Archive first; a failed Master/state write retains previous confirmed files.
    """
    from acr_daily import saveslot
    raw=read_file(saveslot.SAVE)
    save_layout.rally_report(raw)
    if read_file(saveslot.SAVE)!=raw:raise save_layout.InvalidSave('Gra zapisuje plik; kopia pominięta dla tego startu OS.')
    meta=state()
    if meta.get('restartRequired'):raise save_layout.InvalidSave('Zrestartuj launcher i grę przed potwierdzeniem OS.')
    if digest(raw) in meta.get('rejectedDigests',[]):raise save_layout.InvalidSave('Zapis zgłoszony jako wadliwy; kopia Master nie została zmieniona.')
    target=directory()/'Master.sav'
    if meta.get('good',{}).get('digest')==digest(raw) and target.exists() and digest(read_file(target))==digest(raw):
        for key in ('blocked','blockedAt','badDigest','pending','serverCopy'):meta.pop(key,None)
        record(meta);return str(target)
    protected=archive(raw,'confirmed-good')
    atomic(target,raw)
    good={'path':protected,'digest':digest(raw),'confirmedAt':time.time(),'proof':'stage-start'}
    meta.update(good=good,master=str(target))
    copies=meta.get('confirmedCopies',[])+[good]
    retained=copies if len(copies)<=21 else copies[:1]+copies[-20:]
    meta['confirmedCopies']=retained
    for key in ('blocked','blockedAt','badDigest','pending','serverCopy'):meta.pop(key,None)
    record(meta)
    for old in copies:
        if old not in retained:Path(old['path']).unlink(missing_ok=True)
    return str(target)

class StageStartObserver:
    """Observe any private/Club stage independently of server attempt state."""
    def __init__(self,emit,source=None):
        if source is None:
            from .live_penalties import SharedMemory
            source=SharedMemory()
        self.source=source;self.emit=emit
        self.zero=None;self.previous=None;self.pending=None
        # A restoration requires a new EXE and a closed game before rearming.
        from acr_daily import saveslot
        self.await_game_exit=bool(state().get('restartRequired'))
        self.game_running=saveslot.game_running

    def poll(self):
        if self.await_game_exit:
            if state().get('restoreProcess')==os.getpid() or self.game_running():return
            meta=state();meta.pop('restartRequired',None);meta.pop('restoreProcess',None);record(meta)
            self.await_game_exit=False
        f=self.source.read()
        if f is None:
            self.zero=None;self.previous=None;self.pending=None;return
        track=getattr(f,'track',None);car=getattr(f,'car',None)
        if not track or not car:return
        identity=(track,car)
        clock=f.clock_ms
        if clock<=0:
            self.zero=identity;self.previous=None;self.pending=None;return
        if self.zero==identity:
            self.pending=(identity,clock);self.zero=None;return
        if self.pending:
            previous,first_clock=self.pending
            if previous==identity and clock==first_clock:return
            self.pending=None
            if previous==identity and clock>first_clock:
                try:
                    path=confirm_stage_start()
                    self.emit('KOPIA MASTER: start OS potwierdzony; ustawienia zachowane automatycznie. '+path)
                except (OSError,ValueError) as exc:
                    self.emit('OSTRZEŻENIE: kopia Master nie została odświeżona: '+str(exc))
        self.previous=clock

    def close(self):self.source.close()
