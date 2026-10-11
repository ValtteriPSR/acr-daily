"""ACR Rally Club: multi-rally seasons, clubs, divisions, teams and points.

Stdlib/SQLite only. Scores are derived from finalized per-stage results and never
accepted as a value supplied by the client. A rally scores once its window closes.
"""
from __future__ import annotations
from i18n import tr
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import secrets
import sqlite3
import time
from html import escape

CLUB_COOKIE_AGE = 365 * 86400
MAX_RALLIES = 100
MAX_DIVISIONS = 10
MAX_TEAM_SIZE = 10
DEFAULT_GENERAL = [35,25,20,16,13,11,9,7,5,3,2]
DEFAULT_DIVISION = [30,20,15,12,10,8,6,4,3,2]
DEFAULT_POWER_STAGE = [5,4,3,2,1]
TEAM_MODES = ('combined','general','division')


def _hash(value):
    return sha256(value.encode('utf-8')).hexdigest()


def _fault(code, message):
    from server import Fault
    raise Fault(code, message)


def _now():
    return time.time()


def _date(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if d.tzinfo is None: raise ValueError()
        return d.timestamp()
    except (TypeError, ValueError):
        _fault(400, tr('Dates require full ISO format with UTC or a timezone'))


def _scores(values):
    if not isinstance(values, list) or not 1 <= len(values) <= 100 or any(
            type(v) is not int or not 1 <= v <= 1000 for v in values):
        _fault(400, tr('Points: 1–100 positive integers (maximum 1000)'))
    return values


def _power_scores(values):
    """Power Stage: any configured top-N places; outside table = 0, DNF = 0.

    [] explicitly disables Power Stage. Values are zero or positive integers.
    """
    if not isinstance(values, list) or len(values) > 100 or any(
            type(v) is not int or not 0 <= v <= 1000 for v in values):
        _fault(400, tr('Power Stage: up to 100 values from 0 to 1000; an empty list disables the bonus'))
    return values


def _validate_season(data):
    if not isinstance(data,dict): _fault(400,tr('Invalid season configuration'))
    name = str(data.get('name','')).strip()
    if not 3 <= len(name) <= 120: _fault(400,tr('Season name: 3–120 characters'))
    opens, closes = _date(data.get('opensAt')), _date(data.get('closesAt'))
    if not opens < closes or closes-opens > 730*86400: _fault(400,tr('Invalid season date range'))
    general=_scores(data.get('generalPoints',DEFAULT_GENERAL))
    division=_scores(data.get('divisionPoints',DEFAULT_DIVISION))
    power=_power_scores(data.get('powerStagePoints',DEFAULT_POWER_STAGE))
    mode=data.get('teamMode','combined')
    if mode not in TEAM_MODES: _fault(400,tr('Unknown team scoring mode'))
    return name, opens, closes, general, division, power, mode


def install(store):
    with store.lock:
        store.db.executescript(r"""
        CREATE TABLE IF NOT EXISTS club_members (
          id INTEGER PRIMARY KEY, nickname TEXT NOT NULL, nickname_key TEXT NOT NULL UNIQUE,
          recovery_hash TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS club_sessions (
          session_hash TEXT PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES club_members(id),
          expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS seasons (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, opens REAL NOT NULL, closes REAL NOT NULL,
          general_points TEXT NOT NULL, division_points TEXT NOT NULL,
          power_points TEXT NOT NULL DEFAULT '[5,4,3,2,1]', team_mode TEXT NOT NULL DEFAULT 'combined', created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS season_events (
          season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
          event_id TEXT NOT NULL UNIQUE REFERENCES events(id), position INTEGER NOT NULL,
          general_points TEXT, division_points TEXT, power_points TEXT,
          PRIMARY KEY(season_id,event_id), UNIQUE(season_id,position));
        CREATE TABLE IF NOT EXISTS season_divisions (
          id INTEGER PRIMARY KEY, season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
          name TEXT NOT NULL, sort_index INTEGER NOT NULL,
          UNIQUE(season_id,name), UNIQUE(season_id,sort_index));
        CREATE TABLE IF NOT EXISTS season_teams (
          id INTEGER PRIMARY KEY, season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
          name TEXT NOT NULL, capacity INTEGER NOT NULL DEFAULT 10, UNIQUE(season_id,name));
        CREATE TABLE IF NOT EXISTS season_member_assignments (
          season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
          member_id INTEGER NOT NULL REFERENCES club_members(id),
          division_id INTEGER REFERENCES season_divisions(id),
          team_id INTEGER REFERENCES season_teams(id),
          PRIMARY KEY(season_id,member_id));
        """)
        cols={r['name'] for r in store.db.execute('PRAGMA table_info(players)')}
        if 'club_member_id' not in cols:
            store.db.execute('ALTER TABLE players ADD COLUMN club_member_id INTEGER REFERENCES club_members(id)')
        s_cols={r['name'] for r in store.db.execute('PRAGMA table_info(seasons)')}
        if 'power_points' not in s_cols:
            # Existing championships never promised PS bonuses. Migrating with []
            # preserves previously published historical point totals. New
            # seasons explicitly receive the 5-4-3-2-1 default on creation.
            store.db.execute("ALTER TABLE seasons ADD COLUMN power_points TEXT NOT NULL DEFAULT '[]'")
        tm_cols={r['name'] for r in store.db.execute('PRAGMA table_info(season_teams)')}
        if 'capacity' not in tm_cols:
            store.db.execute('ALTER TABLE season_teams ADD COLUMN capacity INTEGER NOT NULL DEFAULT 10')
        se_cols={r['name'] for r in store.db.execute('PRAGMA table_info(season_events)')}
        for field in ('general_points','division_points','power_points'):
            if field not in se_cols:
                store.db.execute(f'ALTER TABLE season_events ADD COLUMN {field} TEXT')
        store.db.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_rally_club_member
                            ON players(event_id,club_member_id) WHERE club_member_id IS NOT NULL''')
        from steam_auth import install as install_steam
        install_steam(store)


def cookie(token, *, secure=False):
    return (f'acrclub_member={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={CLUB_COOKIE_AGE}'
            + ('; Secure' if secure else ''))


def member_by_cookie(store, token, *, steam_only=False):
    if not isinstance(token,str) or not 40 <= len(token) <= 128:
        return None
    with store.lock:
        row=store.db.execute('''SELECT m.id,m.nickname,m.nickname_key,s.steam_verified,a.steam_id FROM club_sessions s
                JOIN club_members m ON m.id=s.member_id
                LEFT JOIN club_steam_accounts a ON a.member_id=m.id
                WHERE s.session_hash=? AND s.expires>?''',(_hash(token),_now())).fetchone()
        if row and steam_only and (not row['steam_verified'] or not row['steam_id']):
            return None
        return dict(row) if row else None


def _new_session(store, member_id, *, steam_verified=False):
    token=secrets.token_urlsafe(32)
    store.db.execute('''INSERT INTO club_sessions(session_hash,member_id,expires,steam_verified)
            VALUES(?,?,?,?)''', (_hash(token), member_id, _now()+CLUB_COOKIE_AGE, int(steam_verified)))
    return token


def steam_finish(store, pending, nickname=None):
    """Create a club identity only after Steam has verified its owner."""
    from steam_auth import pending_steam_id, digest
    from server import nick_key
    with store.lock:
        store._begin()
        try:
            steam_id = pending_steam_id(store, pending)
            if not steam_id:
                _fault(401, tr('Sign in through Steam before choosing your nickname.'))
            linked = store.db.execute('SELECT member_id FROM club_steam_accounts WHERE steam_id=?', (steam_id,)).fetchone()
            if linked:
                member_id = linked['member_id']
            elif nickname is None:
                store.db.execute('COMMIT')
                return None  # First sign-in: ask for a nickname; do not create a placeholder.
            else:
                nick, key = nick_key(nickname)
                # Keep the old NOT NULL column inert for compatibility with existing databases.
                # Recovery keys are neither generated nor accepted.
                row = store.db.execute('''INSERT INTO club_members(nickname,nickname_key,recovery_hash,created)
                                         VALUES(?,?,?,?)''', (nick,key,'',_now()))
                member_id = row.lastrowid
                store.db.execute('INSERT INTO club_steam_accounts(steam_id,member_id) VALUES(?,?)', (steam_id,member_id))
            token = _new_session(store, member_id, steam_verified=True)
            store.db.execute('DELETE FROM steam_pending_sessions WHERE session_hash=?', (digest(pending),))
            member = store.db.execute('SELECT nickname FROM club_members WHERE id=?', (member_id,)).fetchone()
            store.db.execute('COMMIT')
            return {'token':token, 'nickname':member['nickname'], 'memberId':member_id}
        except sqlite3.IntegrityError:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            _fault(409,tr('This nickname or Steam account is already registered. Choose another nickname or sign in again.'))
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def change_nickname(store, token, nickname):
    from server import nick_key
    nick, key = nick_key(nickname)
    with store.lock:
        store._begin()
        try:
            member = member_by_cookie(store, token, steam_only=True)
            if not member:
                _fault(401,tr('Sign in through Steam to edit your nickname.'))
            # Update display names only. IDs, attempts, tokens and results survive.
            store.db.execute('UPDATE club_members SET nickname=?,nickname_key=? WHERE id=?', (nick,key,member['id']))
            store.db.execute('UPDATE players SET nickname=?,nickname_key=? WHERE club_member_id=?', (nick,key,member['id']))
            store.db.execute('COMMIT')
        except sqlite3.IntegrityError:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            _fault(409,tr('This nickname is already used by another club member or rally participant.'))
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def club_logout(store, token, pending=None):
    with store.lock:
        if isinstance(token,str):
            store.db.execute('DELETE FROM club_sessions WHERE session_hash=?', (_hash(token),))
        if isinstance(pending,str):
            store.db.execute('DELETE FROM steam_pending_sessions WHERE session_hash=?', (_hash(pending),))


def club_join(store,event_id,member_id):
    """New per-rally player identity, bound to persistent club identity."""
    with store.lock:
        store._begin()
        try:
            erow, event = store.event(event_id)
            now=_now()
            # Registration opens when the admin publishes the rally.
            # The stage attempt is still forbidden until opensAt.
            if now >= erow['closes']:
                _fault(409,tr('Registration is closed: the rally has ended'))
            member=store.db.execute('SELECT * FROM club_members WHERE id=?',(member_id,)).fetchone()
            if member is None: _fault(401,tr('Club member not found'))
            existing=store.db.execute('''SELECT id FROM players WHERE event_id=?
                                AND (club_member_id=? OR nickname_key=?)''',
                                (event_id,member_id,member['nickname_key'])).fetchone()
            if existing: _fault(409,tr('This nickname is already entered in the rally'))
            token=secrets.token_urlsafe(32)
            cur=store.db.execute('''INSERT INTO players
                (event_id,nickname,nickname_key,token_hash,status,created,last_seen,club_member_id)
                VALUES(?,?,?,?,'registered',?,?,?)''',
                (event_id,member['nickname'],member['nickname_key'],_hash(token),now,now,member_id))
            season=store.db.execute('SELECT season_id FROM season_events WHERE event_id=?',(event_id,)).fetchone()
            if season:
                store.db.execute('''INSERT OR IGNORE INTO season_member_assignments
                            (season_id,member_id,division_id,team_id) VALUES(?,?,NULL,NULL)''',
                            (season['season_id'],member_id))
            store.db.execute('COMMIT')
            return {'ok':True,'playerId':cur.lastrowid,'nickname':member['nickname']}
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def club_player(store,event_id,member_id):
    with store.lock:
        row=store.db.execute('''SELECT * FROM players WHERE event_id=? AND club_member_id=?''',
                             (event_id,member_id)).fetchone()
        return dict(row) if row else None


def ensure_division_assigned(store,event_id,member_id):
    """Prevent a player starting a divisional rally without classification."""
    with store.lock:
        season=store.db.execute('SELECT season_id FROM season_events WHERE event_id=?',(event_id,)).fetchone()
        if season is None:return True
        div_count=store.db.execute('SELECT COUNT(*) FROM season_divisions WHERE season_id=?',
                                   (season['season_id'],)).fetchone()[0]
        if div_count==0:return True
        assigned=store.db.execute('''SELECT a.division_id FROM season_member_assignments a
                        WHERE a.season_id=? AND a.member_id=?''',
                        (season['season_id'],member_id)).fetchone()
        if assigned is None or assigned['division_id'] is None:
            _fault(409,tr('Wait for the administrator to assign your season division'))
        return True


def mint_club_ticket(store,event_id,member_id):
    from web_launcher import mint_ticket
    # Keep the existing one-use ticket gate and its atomicity. Issue an event
    # browser session scoped to this actual club player's row.
    from web_launcher import digest, WEB_SESSION_SECONDS
    with store.lock:
        p=club_player(store,event_id,member_id)
        if p is None:_fault(401,tr('Register for this rally first'))
        ensure_division_assigned(store,event_id,member_id)
        t=secrets.token_urlsafe(32)
        store.db.execute('INSERT INTO web_sessions(session_hash,player_id,expires) VALUES(?,?,?)',
                         (digest(t),p['id'],_now()+WEB_SESSION_SECONDS))
    return mint_ticket(store,t,event_id)


def members(store):
    with store.lock:
        return [dict(r) for r in store.db.execute('SELECT id,nickname,created FROM club_members ORDER BY nickname_key')]


def list_seasons(store):
    with store.lock:
        result=[]
        for s in store.db.execute('SELECT * FROM seasons ORDER BY opens DESC'):
            c=store.db.execute('SELECT COUNT(*) FROM season_events WHERE season_id=?',(s['id'],)).fetchone()[0]
            result.append({'id':s['id'],'name':s['name'],'opensAt':_iso(s['opens']),
                           'closesAt':_iso(s['closes']),'rallyCount':c})
        return result


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def season_config(store,season_id):
    with store.lock:
        s=store.db.execute('SELECT * FROM seasons WHERE id=?',(season_id,)).fetchone()
        if not s:_fault(404,tr('Season not found'))
        events=[dict(r) for r in store.db.execute('''SELECT e.id,e.config,e.opens,e.closes,
                   se.position,se.general_points,se.division_points,se.power_points
                   FROM season_events se JOIN events e ON e.id=se.event_id
                   WHERE se.season_id=? ORDER BY se.position''',(season_id,))]
        return {'id':s['id'],'name':s['name'],'opensAt':_iso(s['opens']),
                'closesAt':_iso(s['closes']),
                'generalPoints':json.loads(s['general_points']),
                'divisionPoints':json.loads(s['division_points']),
                'powerStagePoints':json.loads(s['power_points']),
                'teamMode':s['team_mode'],
                'events':[{'id':e['id'],'name':json.loads(e['config'])['name'],
                           'opensAt':_iso(e['opens']),'closesAt':_iso(e['closes']),
                           'generalPoints':json.loads(e['general_points']) if e['general_points'] else None,
                           'divisionPoints':json.loads(e['division_points']) if e['division_points'] else None,
                           'powerStagePoints':json.loads(e['power_points']) if e['power_points'] is not None else None,
                           'position':e['position']} for e in events],
                'divisions':[dict(r) for r in store.db.execute('''SELECT * FROM season_divisions
                      WHERE season_id=? ORDER BY sort_index''',(season_id,))],
                'teams':[dict(r) for r in store.db.execute('''SELECT * FROM season_teams
                      WHERE season_id=? ORDER BY name''',(season_id,))],
                'assignments':[dict(r) for r in store.db.execute('''SELECT a.member_id,a.division_id,a.team_id,
                       m.nickname FROM season_member_assignments a JOIN club_members m ON m.id=a.member_id
                       WHERE a.season_id=? ORDER BY m.nickname_key''',(season_id,))]}


def _season_locked(store,season_id):
    return bool(store.db.execute('''SELECT 1 FROM season_events se
        JOIN players p ON p.event_id=se.event_id
        WHERE se.season_id=? AND p.status <> 'registered' LIMIT 1''',
        (season_id,)).fetchone())


def save_season(store,data,season_id=None):
    name, opens, closes, gen, div, power, mode = _validate_season(data)
    with store.lock:
        store._begin()
        try:
            if season_id is None:
                season_id='season-'+datetime.now(timezone.utc).strftime('%Y')+'-'+secrets.token_hex(4)
                store.db.execute('''INSERT INTO seasons
                    (id,name,opens,closes,general_points,division_points,power_points,team_mode,created)
                    VALUES(?,?,?,?,?,?,?,?,?)''',
                    (season_id,name,opens,closes,json.dumps(gen),json.dumps(div),json.dumps(power),mode,_now()))
            else:
                if _season_locked(store,season_id):
                    _fault(409,tr('Season attempts have started — scoring rules are locked'))
                if not store.db.execute('SELECT 1 FROM seasons WHERE id=?',(season_id,)).fetchone():
                    _fault(404,tr('Season not found'))
                invalid=store.db.execute('''SELECT 1 FROM season_events se
                    JOIN events e ON e.id=se.event_id WHERE se.season_id=?
                    AND (e.opens<? OR e.closes>?) LIMIT 1''',(season_id,opens,closes)).fetchone()
                if invalid:_fault(409,tr('The new dates do not cover all season rallies'))
                store.db.execute('''UPDATE seasons SET name=?,opens=?,closes=?,general_points=?,
                     division_points=?,power_points=?,team_mode=? WHERE id=?''',
                     (name,opens,closes,json.dumps(gen),json.dumps(div),json.dumps(power),mode,season_id))
            store.db.execute('COMMIT')
            return {'ok':True,'id':season_id}
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def set_rallies(store,season_id,event_ids):
    if not isinstance(event_ids,list) or len(event_ids)>MAX_RALLIES or len(set(event_ids))!=len(event_ids):
        _fault(400,tr('The rally list must contain at most 100 distinct events'))
    with store.lock:
        store._begin()
        try:
            config=season_config(store,season_id)
            if _season_locked(store,season_id):
                _fault(409,tr('Cannot change the season calendar after attempts begin'))
            for eid in event_ids:
                if not isinstance(eid,str): _fault(400,tr('Invalid rally ID'))
                row, event=store.event(eid)
                if _date(event['opensAt']) < _date(config['opensAt']) or _date(event['closesAt']) > _date(config['closesAt']):
                    _fault(400,tr('The rally dates must fall within the season window: ')+eid)
                other=store.db.execute('SELECT season_id FROM season_events WHERE event_id=?',(eid,)).fetchone()
                if other and other['season_id']!=season_id:_fault(409,tr('The rally already belongs to another season: ')+eid)
                if not other and store.db.execute('''SELECT 1 FROM players
                        WHERE event_id=? AND status<>'registered' LIMIT 1''',(eid,)).fetchone():
                    _fault(409,tr('Cannot assign a rally to a season after it has started: ')+eid)
            overrides={r['event_id']:(r['general_points'],r['division_points'],r['power_points'])
                for r in store.db.execute('SELECT * FROM season_events WHERE season_id=?',(season_id,))}
            store.db.execute('DELETE FROM season_events WHERE season_id=?',(season_id,))
            for ix,eid in enumerate(event_ids):
                gp,dp,pp=overrides.get(eid,(None,None,None))
                store.db.execute('''INSERT INTO season_events
                    (season_id,event_id,position,general_points,division_points,power_points) VALUES(?,?,?,?,?,?)''',
                    (season_id,eid,ix,gp,dp,pp))
            store.db.execute('''INSERT OR IGNORE INTO season_member_assignments
                (season_id,member_id,division_id,team_id)
          SELECT DISTINCT ?,p.club_member_id,CAST(NULL AS INTEGER),CAST(NULL AS INTEGER) FROM season_events se
                JOIN players p ON p.event_id=se.event_id
                WHERE se.season_id=? AND p.club_member_id IS NOT NULL''',(season_id,season_id))
            store.db.execute('COMMIT')
            return {'ok':True,'rallyCount':len(event_ids)}
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def set_rally_points(store,season_id,event_id,general,division,power=None):
    """Optional per-rally score overrides. null = use season defaults."""
    gp=json.dumps(_scores(general)) if general is not None else None
    dp=json.dumps(_scores(division)) if division is not None else None
    pp=json.dumps(_power_scores(power)) if power is not None else None
    with store.lock:
        store._begin()
        try:
            found=store.db.execute('''SELECT 1 FROM season_events WHERE season_id=? AND event_id=?''',
                                   (season_id,event_id)).fetchone()
            if not found:_fault(404,tr('The rally does not belong to the season'))
            played=store.db.execute('''SELECT 1 FROM players WHERE event_id=? AND status<>'registered' LIMIT 1''',
                                    (event_id,)).fetchone()
            if played:_fault(409,tr('Cannot change scoring after the rally begins'))
            store.db.execute('''UPDATE season_events SET general_points=?,division_points=?,power_points=?
                            WHERE season_id=? AND event_id=?''',(gp,dp,pp,season_id,event_id))
            store.db.execute('COMMIT')
            return {'ok':True}
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def add_group(store,season_id,kind,name,capacity=10):
    if kind not in ('division','team'):_fault(400,tr('Unknown group type'))
    name=str(name or '').strip()
    if not 2<=len(name)<=60:_fault(400,tr('Division/team name: 2–60 characters'))
    if kind=='team' and (type(capacity) is not int or not 1<=capacity<=MAX_TEAM_SIZE):
        _fault(400,tr('Team capacity must be between 1 and 10 drivers'))
    with store.lock:
        store._begin()
        try:
            season_config(store,season_id)
            if kind=='division':
                count=store.db.execute('SELECT COUNT(*) FROM season_divisions WHERE season_id=?',(season_id,)).fetchone()[0]
                if count>=MAX_DIVISIONS:_fault(409,tr('Maximum 10 divisions'))
                idx=count
                # sparse index handling after a deletion
                taken={r[0] for r in store.db.execute('SELECT sort_index FROM season_divisions WHERE season_id=?',(season_id,))}
                while idx in taken:idx+=1
                cur=store.db.execute('''INSERT INTO season_divisions(season_id,name,sort_index)
                    VALUES(?,?,?)''',(season_id,name,idx))
            else:
                cur=store.db.execute('INSERT INTO season_teams(season_id,name,capacity) VALUES(?,?,?)',
                                     (season_id,name,capacity))
            store.db.execute('COMMIT')
            return {'ok':True,'id':cur.lastrowid}
        except sqlite3.IntegrityError:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            _fault(409,tr('This name already exists'))
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def rename_group(store,season_id,kind,group_id,name):
    if kind not in ('division','team'):_fault(400,tr('Unknown group'))
    table='season_divisions' if kind=='division' else 'season_teams'
    name=str(name or '').strip()
    if not 2<=len(name)<=60:_fault(400,tr('Invalid name'))
    with store.lock:
        r=store.db.execute(f'SELECT id FROM {table} WHERE season_id=? AND id=?',(season_id,group_id)).fetchone()
        if not r:_fault(404,tr('Group not found'))
        try:store.db.execute(f'UPDATE {table} SET name=? WHERE id=?',(name,group_id))
        except sqlite3.IntegrityError:_fault(409,tr('Name already exists'))
        return {'ok':True}


def set_team_capacity(store,season_id,team_id,capacity):
    if type(capacity) is not int or not 1<=capacity<=MAX_TEAM_SIZE:
        _fault(400,tr('Team capacity must be 1–10'))
    with store.lock:
        team=store.db.execute('SELECT * FROM season_teams WHERE season_id=? AND id=?',
                              (season_id,team_id)).fetchone()
        if team is None:_fault(404,tr('Team not found'))
        members=store.db.execute('SELECT COUNT(*) FROM season_member_assignments WHERE team_id=? AND season_id=?',
                                 (team_id,season_id)).fetchone()[0]
        if members>capacity:_fault(409,tr('Capacity is below the current number of team members'))
        store.db.execute('UPDATE season_teams SET capacity=? WHERE id=?',(capacity,team_id))
        return {'ok':True}


def delete_group(store,season_id,kind,group_id):
    if kind not in ('division','team'):_fault(400,tr('Unknown group'))
    table='season_divisions' if kind=='division' else 'season_teams'
    field='division_id' if kind=='division' else 'team_id'
    with store.lock:
        assigned=store.db.execute(f'''SELECT 1 FROM season_member_assignments
                WHERE season_id=? AND {field}=? LIMIT 1''',(season_id,group_id)).fetchone()
        if assigned:_fault(409,tr('Remove driver assignments from the group first'))
        deleted=store.db.execute(f'DELETE FROM {table} WHERE season_id=? AND id=?',(season_id,group_id))
        if not deleted.rowcount:_fault(404,tr('Group not found'))
        return {'ok':True}


def assign_member(store,season_id,member_id,division_id,team_id):
    if type(member_id) is not int:_fault(400,tr('Invalid driver'))
    if division_id is not None and type(division_id) is not int:_fault(400,tr('Invalid division'))
    if team_id is not None and type(team_id) is not int:_fault(400,tr('Invalid team'))
    with store.lock:
        store._begin()
        try:
            season_config(store,season_id)
            if not store.db.execute('SELECT 1 FROM club_members WHERE id=?',(member_id,)).fetchone():
                _fault(404,tr('The driver is not registered with the club'))
            started=store.db.execute('''SELECT 1 FROM season_events se
                    JOIN players p ON p.event_id=se.event_id
                    WHERE se.season_id=? AND p.club_member_id=?
                      AND p.status <> 'registered' LIMIT 1''',(season_id,member_id)).fetchone()
            prior=store.db.execute('''SELECT division_id,team_id FROM season_member_assignments
                        WHERE season_id=? AND member_id=?''',(season_id,member_id)).fetchone()
            if started and (not prior or prior['division_id'] != division_id or prior['team_id'] != team_id):
                _fault(409,tr('Cannot move a driver between divisions/teams after the rally starts'))
            for table,gid,tag in (('season_divisions',division_id,'dywizja'),('season_teams',team_id,tr('team'))):
                if gid is not None and not store.db.execute(f'SELECT 1 FROM {table} WHERE id=? AND season_id=?',
                                    (gid,season_id)).fetchone():
                    _fault(400,tr('Unknown ')+tag)
            if team_id is not None and (not prior or prior['team_id']!=team_id):
                count=store.db.execute('''SELECT COUNT(*) FROM season_member_assignments
                        WHERE season_id=? AND team_id=?''',(season_id,team_id)).fetchone()[0]
                capacity=store.db.execute('SELECT capacity FROM season_teams WHERE id=?',(team_id,)).fetchone()[0]
                if count>=capacity:_fault(409,f"{tr('The team is full (')}{capacity}{tr(' drivers)')}")
            store.db.execute('''INSERT INTO season_member_assignments(season_id,member_id,division_id,team_id)
                VALUES(?,?,?,?) ON CONFLICT(season_id,member_id) DO UPDATE SET
                division_id=excluded.division_id,team_id=excluded.team_id''',
                (season_id,member_id,division_id,team_id))
            store.db.execute('COMMIT')
            return {'ok':True}
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def _ranking(rows):
    """Competition ranking: tied times => 1,1,3 (same points)."""
    result={}
    last_time=None
    place=0
    for pos,row in enumerate(sorted(rows,key=lambda x:(x['total'],x['member_id'])),1):
        if row['total'] != last_time:place=pos
        result[row['member_id']]=place
        last_time=row['total']
    return result


def scoring(store,season_id,now=None):
    with store.lock:
        conf=season_config(store,season_id)
        now=_now() if now is None else now
        assignments={a['member_id']:a for a in conf['assignments']}
        members={r['id']:r['nickname'] for r in members_list_sql(store)}
        totals={id:{'memberId':id,'nickname':nick,'general':0,'division':0,'total':0,
                    'powerStage':0,'finishes':0,'divisionId':assignments.get(id,{}).get('division_id'),
                    'teamId':assignments.get(id,{}).get('team_id')}
                 for id,nick in members.items() if id in assignments}
        rallies=[]
        for ev in conf['events']:
            completed=store.db.execute('''SELECT p.club_member_id AS member_id,
                SUM(r.total_ms) AS total,COUNT(r.stage_index) AS stages
                FROM players p JOIN results r ON r.player_id=p.id
                WHERE p.event_id=? AND p.status='completed' AND p.club_member_id IS NOT NULL
                GROUP BY p.id''',(ev['id'],)).fetchall()
            nstages=len(json.loads(store.event(ev['id'])[0]['config'])['stages'])
            ranked=[dict(r) for r in completed if r['member_id'] in assignments and r['stages']==nstages]
            is_closed=ev['closesAt'] and _date(ev['closesAt'])<=now
            general_rank=_ranking(ranked)
            # Power Stage is the final configured SS, ranked by GAME-OFFICIAL
            # stage total (raw + penalties), among FINISHERS only.
            final_index=nstages-1
            last_stage_rows=store.db.execute("""SELECT p.club_member_id AS member_id,
                    r.total_ms AS total FROM results r JOIN players p ON p.id=r.player_id
                    WHERE p.event_id=? AND p.status='completed' AND
                    p.club_member_id IS NOT NULL AND r.stage_index=?""",
                    (ev['id'],final_index)).fetchall()
            eligible=set(general_rank)
            power_rank=_ranking([dict(r) for r in last_stage_rows
                                 if r['member_id'] in eligible])
            groups={}
            for r in ranked:
                d=assignments[r['member_id']]['division_id']
                if d is not None:groups.setdefault(d,[]).append(r)
            division_rank={member_id:rank for rs in groups.values() for member_id,rank in _ranking(rs).items()}
            entries=[]
            for r in sorted(ranked,key=lambda x:(x['total'],x['member_id'])):
                mid=r['member_id']
                place=general_rank[mid]
                place_div=division_rank.get(mid)
                gp=ev['generalPoints'] if ev['generalPoints'] is not None else conf['generalPoints']
                dp=ev['divisionPoints'] if ev['divisionPoints'] is not None else conf['divisionPoints']
                pp=ev['powerStagePoints'] if ev['powerStagePoints'] is not None else conf['powerStagePoints']
                place_power=power_rank.get(mid)
                power_points=(pp[place_power-1] if place_power is not None and place_power<=len(pp) else 0) if is_closed else 0
                gen_points=(gp[place-1] if place<=len(gp) else 1) if is_closed else 0
                div_points=((dp[place_div-1] if place_div<=len(dp) else 1)
                            if is_closed and place_div is not None else 0)
                entry={'memberId':mid,'nickname':members[mid],'rankGeneral':place,
                       'rankDivision':place_div,'totalMs':r['total'],
                       'pointsGeneral':gen_points,'pointsDivision':div_points,
                       'rankPowerStage':place_power,'pointsPowerStage':power_points,
                       'divisionId':assignments[mid]['division_id']}
                entries.append(entry)
                t=totals[mid]
                t['general']+=gen_points;t['division']+=div_points;t['powerStage']+=power_points
                if is_closed:t['finishes']+=1
            rallies.append({'id':ev['id'],'name':ev['name'],'closed':bool(is_closed),'results':entries})
        for t in totals.values():t['total']=t['general']+t['division']+t['powerStage']
        drivers=sorted(totals.values(),key=lambda x:(-x['total'],-x['finishes'],-x['general'],x['nickname'].casefold()))
        teams=[]
        for team in conf['teams']:
            assigned=[m for m in drivers if m['teamId']==team['id']]
            mode=conf['teamMode']
            pts=sum(m['total'] if mode=='combined' else (m['general']+m['powerStage'] if mode=='general' else m['division']) for m in assigned)
            teams.append({'id':team['id'],'name':team['name'],'points':pts,
                          'members':len(assigned),'capacity':team['capacity']})
        teams.sort(key=lambda t:(-t['points'],t['name'].casefold()))
        divisions=[]
        for div in conf['divisions']:
            ranked_members=[m for m in drivers if m['divisionId']==div['id']]
            ranked_members.sort(key=lambda m:(-m['division'],-m['finishes'],m['nickname'].casefold()))
            divisions.append({'id':div['id'],'name':div['name'],'drivers':ranked_members})
        return {'season':conf,'rallies':rallies,'drivers':drivers,'divisions':divisions,'teams':teams}


def members_list_sql(store):
    return store.db.execute('SELECT id,nickname FROM club_members ORDER BY nickname_key').fetchall()


def club_page(member,csrf,pending=False):
    field='<input type="hidden" name="csrf" value="'+escape(csrf,quote=True)+'">'
    if member and member.get('steam_verified'):
        return (tr('<h1>ACR Rally Club · profile</h1><section class="card"><h2>Welcome, ')+escape(member['nickname'])+
                tr('</h2><p>Signed in through Steam. Your club nickname can be different from your Steam profile name.</p><form action="/web/club/nickname" method="post">')+field+
                tr('<label>Club nickname <input name="nickname" required minlength="2" maxlength="24" autocomplete="nickname" value="')+escape(member['nickname'],quote=True)+
                tr('"></label> <button class="run">SAVE NICKNAME</button></form><p>Changing your nickname keeps your rally entries, attempts and results.</p><p><a href="/">Choose a rally</a> · <a href="/seasons">Seasons</a></p><form action="/web/club/logout" method="post">')+field+
                tr('<button>Sign out of the club</button></form></section>'))
    if pending:
        return (tr('<h1>Steam sign-in confirmed</h1><section class="card"><h2>Choose your club nickname</h2><p>This nickname is linked to your Steam account. You can change it later in My profile.</p><form action="/web/club/register" method="post">')+field+
                tr('<label>Club nickname <input name="nickname" required minlength="2" maxlength="24" autocomplete="nickname"></label> <button class="run">SAVE AND CONTINUE</button></form></section><form action="/web/club/logout" method="post">')+field+tr('<button>Cancel and sign out</button></form>'))
    return tr('<h1>ACR Rally Club · join the club</h1><section class="card"><h2>Sign in through Steam</h2><p>Sign in on the official Steam website, then choose your ACR Rally Club nickname. You can edit it whenever you are signed in.</p><p><a class="btn-link" href="/auth/steam">SIGN IN THROUGH STEAM</a></p><p>Your Steam password stays on Steam. The club uses your verified Steam identity to keep one account and your rally history.</p></section>')
