"""Immutable per-stage submissions, bounded private resume copies and explicit purges."""
import base64
import gzip
import hashlib
import io
import json
import math
import time
from integrity_rules import compare as compare_settings

MAX_SAVE = 4 * 1024 * 1024
MAX_PACKED = 2 * 1024 * 1024
MAX_CHECKPOINT_STORAGE = 64 * 1024 * 1024


def install(store):
    store.db.execute('''CREATE TABLE IF NOT EXISTS telemetry_penalties (
      player_id INTEGER NOT NULL REFERENCES players(id), stage_index INTEGER NOT NULL,
      penalty_ms INTEGER NOT NULL, updated REAL NOT NULL,
      PRIMARY KEY(player_id,stage_index))''')
    store.db.execute('''CREATE TABLE IF NOT EXISTS rally_checkpoints (
      player_id INTEGER PRIMARY KEY REFERENCES players(id), stage_index INTEGER NOT NULL,
      payload TEXT NOT NULL, digest TEXT NOT NULL, created REAL NOT NULL)''')


def observe_penalty(store,p,idx,value):
    from server import Fault
    if value is None: return
    if type(value) is not int or not 0<=value<=3600000:
        raise Fault(400,'Invalid telemetry penalty')
    # Zero may be an unsupported game field. Only positive observations form a floor.
    if value == 0: return
    old=store.db.execute('SELECT penalty_ms FROM telemetry_penalties WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
    maximum=max(value,old['penalty_ms'] if old else 0)
    accepted=store.db.execute('SELECT penalty_ms FROM results WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
    if accepted and accepted['penalty_ms']+10<maximum:
        raise Fault(409,'Telemetry penalty exceeds accepted result; administrator review required')
    store.db.execute('''INSERT INTO telemetry_penalties(player_id,stage_index,penalty_ms,updated)
      VALUES(?,?,?,?) ON CONFLICT(player_id,stage_index) DO UPDATE SET penalty_ms=excluded.penalty_ms,updated=excluded.updated''',(p['id'],idx,maximum,time.time()))


def late_penalty(store,token,data):
    from server import Fault
    with store.lock:
        p=store._auth(token);idx=data.get('stageIndex')
        if p['status'] not in ('ready','awaiting_results') or type(idx) is not int or idx!=p['stage_index']-1:
            raise Fault(409,'No just-finished stage awaiting telemetry')
        prov=store.db.execute('SELECT clock_ms FROM provisional WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
        if not prov or type(data.get('clockMs')) is not int or data['clockMs']!=prov['clock_ms']:
            raise Fault(409,'Telemetry finish does not match')
        observe_penalty(store,p,idx,data.get('penaltyMs'))
        return {'ok':True}


def validate_record(store,p,event,record,idx,previous=0):
    from server import Fault
    if not isinstance(record,dict) or type(record.get('stageIndex')) is not int or record['stageIndex']!=idx or record.get('stageId')!=event['stages'][idx]['stageId'] or record.get('carId')!=p['car_id']:
        raise Fault(409,'Wrong stage or car in the official result')
    raw,pen,total=(record.get(k) for k in ('rawMs','penaltyMs','totalMs'))
    if any(type(x) is not int for x in (raw,pen,total)) or not 10000<=raw<=14400000 or not 0<=pen<=3600000 or raw+pen!=total:
        raise Fault(400,'Invalid time or penalty')
    started=record.get('acrStarted')
    if type(started) not in (int,float) or not math.isfinite(started) or not p['created']-60<=started<=time.time()+60 or started<=previous:
        raise Fault(409,'Invalid attempt start time in the ACR file')
    prov=store.db.execute('SELECT * FROM provisional WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
    if not prov: raise Fault(409,'Stage has no telemetry finish')
    if abs(raw-prov['clock_ms'])>5000: raise Fault(409,'Official timer differs from telemetry by more than 5 seconds')
    if started>prov['finished']+60: raise Fault(409,'Result starts after its telemetry finish')
    observed=store.db.execute('SELECT penalty_ms FROM telemetry_penalties WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
    if observed and pen+10<observed['penalty_ms']:
        raise Fault(409,'Save penalty is lower than live telemetry; administrator review required')
    return raw,pen,total,started


def match_existing(old,record):
    return all(old[a]==record[b] for a,b in [('stage_id','stageId'),('car_id','carId'),('raw_ms','rawMs'),('penalty_ms','penaltyMs'),('total_ms','totalMs'),('acr_started','acrStarted')])


def stage_result(store,token,data):
    from server import Fault
    with store.lock:
        store._begin()
        try:
            store._sweep();p=store._auth(token);_,event=store.event(p['event_id'])
            idx=data.get('stageIndex')
            if p['status'] not in ('ready','active','awaiting_results') or type(idx) is not int or not 0<=idx<p['stage_index']:
                raise Fault(409,'Stage is not ready for confirmation')
            reason=store._integrity_or_dnf(p,event,data.get('settings'))
            if reason:
                store.db.execute('COMMIT');raise Fault(409,reason)
            previous=store.db.execute('SELECT acr_started FROM results WHERE player_id=? AND stage_index=?',(p['id'],idx-1)).fetchone() if idx else None
            if idx and not previous: raise Fault(409,'Confirm previous stages first')
            raw,pen,total,started=validate_record(store,p,event,data,idx,previous[0] if previous else 0)
            old=store.db.execute('SELECT * FROM results WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
            if old:
                if not match_existing(old,data): raise Fault(409,'An accepted stage result is immutable')
            else:
                store.db.execute('INSERT INTO results(player_id,stage_index,stage_id,car_id,raw_ms,penalty_ms,total_ms,acr_started,finished) VALUES(?,?,?,?,?,?,?,?,?)',(p['id'],idx,event['stages'][idx]['stageId'],p['car_id'],raw,pen,total,started,time.time()))
            store.db.execute('COMMIT');return {'ok':True,'stageIndex':idx}
        except Exception:
            if store.db.in_transaction: store.db.execute('ROLLBACK')
            raise


def checkpoint(store,token,data=None):
    from server import Fault
    with store.lock:
        p=store._auth(token);_,ev=store.event(p['event_id'])
        idx=p['stage_index']
        if p['status']!='ready' or not ev.get('allowBreaks',True) or not ev['stages'][idx].get('serviceBefore',False):
            raise Fault(409,'Resume is allowed only at a service before the next stage')
        count=store.db.execute('SELECT COUNT(*) FROM results WHERE player_id=? AND stage_index<?',(p['id'],idx)).fetchone()[0]
        if count!=idx:
            raise Fault(409,'Break not confirmed: official times and penalties for completed stages are missing')
        if data is None:
            row=store.db.execute('SELECT * FROM rally_checkpoints WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
            if not row: return {'available':False}
            return {'available':True,**json.loads(row['payload']),'digest':row['digest'],'stageIndex':idx,'playerId':p['id'],'eventId':p['event_id']}
        if data.get('stageIndex')!=idx or compare_settings(ev,data.get('settings')): raise Fault(409,'Checkpoint settings or progress do not match the rally')
        packed=data.get('save');baseline=data.get('baseline')
        if not isinstance(packed,str) or len(packed)>MAX_PACKED*4//3+8 or not isinstance(baseline,dict) or len(json.dumps(baseline))>256000: raise Fault(413,'Checkpoint is too large')
        if any(not isinstance(k,str) or type(v) is not int or not 0<=v<=10000 for k,v in baseline.items()): raise Fault(400,'Invalid checkpoint baseline')
        try:
            compressed=base64.b64decode(packed,validate=True)
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as f: raw=f.read(MAX_SAVE+1)
            if not raw or len(raw)>MAX_SAVE: raise ValueError()
        except (ValueError,OSError,EOFError): raise Fault(400,'Invalid or oversized save')
        digest=hashlib.sha256(raw).hexdigest()
        if digest!=data.get('digest'): raise Fault(400,'Checkpoint checksum mismatch')
        payload=json.dumps({'save':packed,'baseline':baseline},separators=(',',':'))
        size=store.db.execute('SELECT COALESCE(SUM(LENGTH(payload)),0) FROM rally_checkpoints WHERE player_id<>?',(p['id'],)).fetchone()[0]
        if size+len(payload)>MAX_CHECKPOINT_STORAGE: raise Fault(507,'Resume storage is full; keep the game open and contact the administrator')
        store.db.execute('INSERT INTO rally_checkpoints(player_id,stage_index,payload,digest,created) VALUES(?,?,?,?,?) ON CONFLICT(player_id) DO UPDATE SET stage_index=excluded.stage_index,payload=excluded.payload,digest=excluded.digest,created=excluded.created',(p['id'],idx,payload,digest,time.time()))
        return {'ok':True,'digest':digest,'stageIndex':idx}


def purge_event_rows(store,ident):
    for table in ('web_sessions','launch_tickets','launch_leases','rally_checkpoints','telemetry_penalties','provisional','results'):
        store.db.execute('DELETE FROM '+table+' WHERE player_id IN (SELECT id FROM players WHERE event_id=?)',(ident,))
    store.db.execute('DELETE FROM players WHERE event_id=?',(ident,))
    store.db.execute('DELETE FROM season_events WHERE event_id=?',(ident,))
    store.db.execute('DELETE FROM admin_audit WHERE event_id=? OR details LIKE ?',(ident,'%"'+ident+'"%'))
    store.db.execute('DELETE FROM discord_deliveries WHERE delivery_key LIKE ?',('%:'+ident+':%',))
    store.db.execute('DELETE FROM events WHERE id=?',(ident,))


def purge_season(store,ident,confirm,cascade=False):
    from server import Fault
    if confirm!=ident: raise Fault(400,'Type the season ID to confirm permanent deletion')
    with store.lock:
        store._begin()
        try:
            if not store.db.execute('SELECT id FROM seasons WHERE id=?',(ident,)).fetchone(): raise Fault(404,'Season not found')
            if cascade:
                ids=[r[0] for r in store.db.execute('SELECT event_id FROM season_events WHERE season_id=?',(ident,))]
                for eid in ids: purge_event_rows(store,eid)
            for table in ('season_member_assignments','season_events','season_divisions','season_teams'):
                store.db.execute('DELETE FROM '+table+' WHERE season_id=?',(ident,))
            store.db.execute('DELETE FROM seasons WHERE id=?',(ident,))
            store.db.execute('DELETE FROM admin_audit WHERE event_id=? OR details LIKE ?',(ident,'%"'+ident+'"%'))
            store.db.execute('COMMIT');return {'ok':True,'id':ident}
        except Exception:
            if store.db.in_transaction: store.db.execute('ROLLBACK')
            raise
