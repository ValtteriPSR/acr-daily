"""Local ACR Rally Club scoreboard and first-attempt gate. Python 3.13, stdlib only.

Run from merged acr-daily root: py -3.13 server_local/server.py --import-event examples/...json
then: py -3.13 server_local/server.py
"""
from __future__ import annotations
from i18n import tr
from i18n import (request_localized, localize_document, language, language_cookie,
                  safe_return_path, SUPPORTED_LANGUAGES)
import argparse
import base64
import math
import club_settings
import attempt_updates
import admin_penalties
import telemetry_audit
import sys
# When launched with python server_local/server.py, ensure helper modules importing
# `server.Fault` see the same class as the running __main__ HTTP handler.
# Otherwise expected 4xx validation errors could be misreported as HTTP 500.
if __name__ == '__main__':
    sys.modules.setdefault('server', sys.modules['__main__'])
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import ipaddress
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from html import escape
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from database import connect_database
import threading
import time
from urllib.parse import unquote, urlparse, parse_qs, quote, urlsplit
from integrity_rules import compare as compare_settings, expected_settings
from admin_panel import AdminAuth, html as admin_html, load_catalog, validate_catalog_event
from admin_access import admin_path as get_admin_path
from web_launcher import (install_tables, enroll, browser_player, mint_ticket,
                          redeem_ticket, abort_prestart, make_cookie, csrf_ok)
from seasons import (install as install_seasons,
                     club_join, club_player, member_by_cookie, cookie as club_cookie,
                     mint_club_ticket, ensure_division_assigned, members as club_members,
                     list_seasons, season_config, save_season, set_rallies, set_rally_points,
                     add_group, rename_group, delete_group, set_team_capacity, assign_member, scoring,
                     club_page, steam_finish, change_nickname, club_logout)
import steam_auth
import discord_notifications
from season_panel import html as season_admin_html
from public_security import (PUBLIC_URL, DOWNLOAD_URL, check_config, gateway_ok,
                             check_host, browser_origin, remote_addr, RateLimiter, version_allowed,
                             launcher_release_page)

ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = Path(os.environ.get('ACR_DB_PATH', str(ROOT / 'server_local' / 'club.sqlite3')))
MAX_BODY = 64 * 1024
INACTIVE_SECONDS = 120
STATES = {'registered', 'active', 'ready', 'awaiting_results', 'completed', 'dnf'}


def utc_epoch(s):
    dt = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp requires timezone')
    return dt.timestamp()


def validate_event(event):
    if not isinstance(event, dict):
        raise ValueError('Event must be JSON object')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,63}', str(event.get('id', ''))):
        raise ValueError('Invalid rally ID')
    if 'allowBreaks' in event and type(event['allowBreaks']) is not bool:
        raise ValueError('allowBreaks must be a boolean')
    if not 3 <= len(str(event.get('name', '')).strip()) <= 120:
        raise ValueError('Invalid rally name')
    stages = event.get('stages')
    if not isinstance(stages, list) or not 2 <= len(stages) <= 40:
        raise ValueError('Need 2-40 rally stages')
    region = event.get('location')
    if region not in ('Greece', 'Alsace', 'Wales', 'MonteCarlo'):
        raise ValueError('Unknown rally location')
    prefix = {'Greece': 'Greece', 'Alsace': 'Alsace', 'Wales': 'Weles', 'MonteCarlo': 'MonteCarlo'}[region]
    for stage in stages:
        if not isinstance(stage, dict) or not str(stage.get('stageId', '')).startswith(prefix):
            raise ValueError('Stage ID differs from rally location')
        if not re.fullmatch('[A-Za-z0-9]{6,100}', str(stage['stageId'])):
            raise ValueError('Bad stage ID')
        if not isinstance(stage.get('startSeconds'), (int, float)) or not 0 <= stage['startSeconds'] < 86400:
            raise ValueError('Bad stage time')
        if not isinstance(stage.get('weatherGame'), str):
            raise ValueError('Missing weather')
    cars = event.get('allowedCars')
    if not isinstance(cars, list) or not cars or len(cars) != len(set(cars)):
        raise ValueError('Need distinct allowedCars')
    if not isinstance(event.get('carClass'), str) or not event['carClass']:
        raise ValueError('Missing car class')
    # Validate the same expected rule vocabulary used by the club builder.
    expected_settings(event)
    opening, closing = utc_epoch(event['opensAt']), utc_epoch(event['closesAt'])
    if not opening < closing or closing - opening > 90 * 86400:
        raise ValueError('Invalid event window')
    return event


class Fault(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def nick_key(nick):
    if not isinstance(nick, str) or not 2 <= len(nick.strip()) <= 24:
        raise Fault(400, tr('Nickname: 2–24 characters'))
    nick = nick.strip()
    if not re.fullmatch(r'[\w\- ]+', nick, re.UNICODE):
        raise Fault(400, tr('Nicknames may contain letters, digits, spaces, _ and -'))
    return nick, nick.casefold()


def format_ms(ms):
    ms = int(ms or 0)
    minutes, rest = divmod(ms, 60000)
    sec, millis = divmod(rest, 1000)
    return f'{minutes:02d}:{sec:02d}.{millis:03d}'


class Store:
    def __init__(self, path=DB_DEFAULT, inactive=INACTIVE_SECONDS):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.inactive = inactive
        self.lock = threading.RLock()
        self.db = connect_database(self.path)
        self.db.executescript(r"""
        CREATE TABLE IF NOT EXISTS events (
          id TEXT PRIMARY KEY, config TEXT NOT NULL, opens REAL NOT NULL, closes REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS players (
          id INTEGER PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id),
          nickname TEXT NOT NULL, nickname_key TEXT NOT NULL,
          token_hash TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'registered',
          stage_index INTEGER NOT NULL DEFAULT 0, car_id TEXT,
          created REAL NOT NULL, last_seen REAL, started REAL, terminal_reason TEXT,
          UNIQUE(event_id,nickname_key));
        CREATE TABLE IF NOT EXISTS provisional (
          player_id INTEGER NOT NULL REFERENCES players(id), stage_index INTEGER NOT NULL,
          clock_ms INTEGER NOT NULL, finished REAL NOT NULL,
          PRIMARY KEY(player_id,stage_index));
        CREATE TABLE IF NOT EXISTS results (
          player_id INTEGER NOT NULL REFERENCES players(id), stage_index INTEGER NOT NULL,
          stage_id TEXT NOT NULL, car_id TEXT NOT NULL,
          raw_ms INTEGER NOT NULL, penalty_ms INTEGER NOT NULL, total_ms INTEGER NOT NULL,
          acr_started REAL NOT NULL, finished REAL NOT NULL,
          PRIMARY KEY(player_id,stage_index));
        """)
        club_settings.install(self)
        attempt_updates.install(self)
        admin_penalties.install(self)
        telemetry_audit.install(self)
        install_tables(self)
        install_seasons(self)
        discord_notifications.install(self)
        self.db.execute('''CREATE TABLE IF NOT EXISTS admin_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, peer TEXT NOT NULL,
          action TEXT NOT NULL, event_id TEXT, details TEXT NOT NULL)''')

    def _begin(self):
        self.db.execute('BEGIN IMMEDIATE')

    def event(self, ident):
        row = self.db.execute('SELECT * FROM events WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Fault(404, tr('Rally not found'))
        return dict(row), json.loads(row['config'])

    def import_event(self, config):
        validate_event(config)
        with self.lock:
            existing = self.db.execute('SELECT id FROM events WHERE id=?', (config['id'],)).fetchone()
            if existing:
                raise Fault(409, tr('The rally already exists (it is not overwritten after attempts begin)'))
            self.db.execute('INSERT INTO events(id,config,opens,closes) VALUES(?,?,?,?)',
                            (config['id'], json.dumps(config, ensure_ascii=False),
                             utc_epoch(config['opensAt']), utc_epoch(config['closesAt'])))

    def create_admin_event(self, config):
        """Server-controlled identifier; never trust a proposed ID from browser."""
        config = dict(config)
        with self.lock:
            self._begin()
            try:
                for _ in range(10):
                    ident = 'rally-' + datetime.now(timezone.utc).strftime('%Y%m%d') + '-' + secrets.token_hex(4)
                    if not self.db.execute('SELECT 1 FROM events WHERE id=?', (ident,)).fetchone():
                        break
                else:
                    raise Fault(503, tr('Cannot generate a unique rally ID'))
                config['id'] = ident
                validate_event(config)
                self.db.execute('INSERT INTO events(id,config,opens,closes) VALUES(?,?,?,?)',
                                (ident, json.dumps(config, ensure_ascii=False),
                                 utc_epoch(config['opensAt']), utc_epoch(config['closesAt'])))
                self.db.execute('COMMIT')
                return {'ok': True, 'id': ident}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def audit(self, peer, action, ident, details):
        """Append-only from HTTP routes; full admin edits are recoverable from snapshots."""
        with self.lock:
            self.db.execute('INSERT INTO admin_audit(ts,peer,action,event_id,details) VALUES(?,?,?,?,?)',
                            (time.time(), str(peer)[:128], action, ident,
                             json.dumps(details, ensure_ascii=False)))

    def update_event(self, ident, config):
        validate_event(config)
        if config['id'] != ident:
            raise Fault(400, tr('The rally ID cannot be changed'))
        with self.lock:
            self._begin()
            try:
                self.event(ident)
                used = self.db.execute('SELECT COUNT(*) FROM players WHERE event_id=?', (ident,)).fetchone()[0]
                if used:
                    raise Fault(409, tr('The rally has participants; configuration changes are locked'))
                self.db.execute('UPDATE events SET config=?,opens=?,closes=? WHERE id=?',
                                (json.dumps(config, ensure_ascii=False),
                                 utc_epoch(config['opensAt']), utc_epoch(config['closesAt']), ident))
                self.db.execute('COMMIT')
                return {'ok': True, 'id': ident}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def delete_event(self, ident, confirm=None):
        with self.lock:
            self._begin()
            try:
                self.event(ident)
                used = self.db.execute('SELECT COUNT(*) FROM players WHERE event_id=?', (ident,)).fetchone()[0]
                if confirm is not None and confirm!=ident: raise Fault(400,'Type the rally ID to confirm permanent deletion')
                if used and confirm!=ident:
                    raise Fault(409,tr('Cannot delete a rally with participants'))
                attempt_updates.purge_event_rows(self,ident)
                self.db.execute('COMMIT')
                return {'ok': True, 'id': ident}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def admin_listing(self):
        with self.lock:
            counts = {r['event_id']: r['total'] for r in self.db.execute(
                'SELECT event_id, COUNT(*) AS total FROM players GROUP BY event_id')}
            events = self.listing()
            return [dict(ev, participantCount=counts.get(ev['id'], 0)) for ev in events]

    def listing(self):
        with self.lock:
            self._sweep()
            return [json.loads(r[0]) for r in self.db.execute('SELECT config FROM events ORDER BY opens DESC')]

    def _sweep(self):
        now = time.time()
        telemetry_audit.expire(self,now)
        self.db.execute("""UPDATE players SET status='dnf',terminal_reason='Missing complete official results after finish', started=NULL
            WHERE status='awaiting_results' AND last_seen < ?""", (now - 600,))
        self.db.execute("UPDATE players SET status='dnf',\n             terminal_reason='Client connection lost after stage start',\n             started=NULL WHERE status='active' AND last_seen < ?", (now - self.inactive,))

        self.db.execute("DELETE FROM rally_checkpoints WHERE player_id IN (SELECT id FROM players WHERE status IN ('dnf','completed'))")
        self.db.execute('''DELETE FROM rally_checkpoints WHERE stage_index=0 OR player_id IN
          (SELECT p.id FROM players p JOIN events e ON e.id=p.event_id WHERE e.closes<=?)''',(now,))
        self.db.execute('''DELETE FROM rally_recovery WHERE player_id IN
          (SELECT p.id FROM players p JOIN events e ON e.id=p.event_id
           WHERE e.closes<=? OR p.status IN ('dnf','completed'))''',(now,))

    def _auth(self, token):
        if not isinstance(token, str) or len(token) < 40:
            raise Fault(401, tr('Missing participant token'))
        row = self.db.execute('SELECT * FROM players WHERE token_hash=?',
                              (sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:
            raise Fault(401, tr('Invalid token'))
        return row

    def join(self, event_id, nick):
        nick, key = nick_key(nick)
        with self.lock:
            self._begin()
            try:
                row, event = self.event(event_id)
                if self.db.execute('SELECT 1 FROM season_events WHERE event_id=?',(event_id,)).fetchone():
                    raise Fault(403, tr('A season rally requires a club account. Register a nickname at /club'))
                now = time.time()
                # Club registration is permitted in advance; RUN remains time-gated.
                if now >= row['closes']:
                    raise Fault(409, tr('Registration is closed: the rally has ended'))
                used = self.db.execute('SELECT 1 FROM players WHERE event_id=? AND nickname_key=?',
                                       (event_id, key)).fetchone()
                if used:
                    raise Fault(409, tr('Nickname already registered; use the existing token on this computer'))
                token = secrets.token_urlsafe(32)
                cur = self.db.execute('''INSERT INTO players
                    (event_id,nickname,nickname_key,token_hash,created,last_seen)
                    VALUES(?,?,?,?,?,?)''',
                    (event_id, nick, key, sha256(token.encode()).hexdigest(), now, now))
                self.db.execute('COMMIT')
                return {'token': token, 'playerId': cur.lastrowid, 'event': event, 'nickname': nick}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def state(self, token):
        with self.lock:
            self._sweep()
            player = self._auth(token)
            row, config = self.event(player['event_id'])
            entries = self.db.execute('SELECT * FROM results WHERE player_id=? ORDER BY stage_index',
                                      (player['id'],)).fetchall()
            d = {k: player[k] for k in ('nickname', 'status', 'stage_index', 'car_id', 'terminal_reason')}
            d.update({'event': config, 'results': [dict(e) for e in entries]})
            d.update(attempt_updates.recovery_state(self,player['id']))
            d['dnfStage']=min(player['stage_index']+1,len(config['stages'])) if player['status']=='dnf' else None
            return d

    def _integrity_or_dnf(self, player, event, settings):
        """Server-side fail-closed protocol validation (client is NOT a trusted attestor)."""
        problems = compare_settings(event, settings)
        if problems:
            reason = tr('Rally Weekend settings changed: ') + '; '.join(problems[:3])
            if player['status']=='registered' or (player['status']=='ready' and event.get('allowBreaks',True)):
                attempt_updates.require_recovery(self,player,reason)
                return reason
            self.db.execute("UPDATE players SET status='dnf',terminal_reason=?,started=NULL WHERE id=?",
                            (reason[:300], player['id']))
            return reason
        return None

    def integrity_violation(self, token, reason):
        """Client-reported mismatch while joining, waiting, driving, or finalizing."""
        with self.lock:
            self._begin()
            try:
                p = self._auth(token)
                if p['status'] in ('completed','dnf'):
                    raise Fault(409, tr('The rally has already ended'))
                msg = (tr('Rally Weekend settings mismatch: ') + str(reason))[:300]
                _,event=self.event(p['event_id'])
                if p['status']=='registered' or (p['status']=='ready' and event.get('allowBreaks',True)):
                    out=attempt_updates.require_recovery(self,p,msg)
                    self.db.execute('COMMIT')
                    return out
                self.db.execute("UPDATE players SET status='dnf',terminal_reason=?,started=NULL WHERE id=?",
                                (msg,p['id']))
                self.db.execute('COMMIT')
                return {'ok':True,'status':'dnf'}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def start(self, token, event_id, stage_index, car_id, settings=None):
        with self.lock:
            self._begin()
            try:
                self._sweep()
                p = self._auth(token)
                row, config = self.event(event_id)
                if p['event_id'] != event_id:
                    raise Fault(403, tr('Rally differs from the registered event'))
                if p['club_member_id'] is not None:
                    ensure_division_assigned(self,event_id,p['club_member_id'])
                now = time.time()
                if not row['opens'] <= now <= row['closes']:
                    raise Fault(409, tr('The rally is not currently active'))
                if p['status'] not in ('registered', 'ready') or p['stage_index'] != stage_index:
                    raise Fault(409, tr('Attempt already used or stage locked'))
                if attempt_updates.recovery_state(self,p['id'])['recoveryRequired']:
                    raise Fault(409,tr('Close the game and launcher, then click RUN to restore Club settings. Your attempt is preserved.'))
                if stage_index < 0 or stage_index >= len(config['stages']):
                    raise Fault(400, tr('Invalid stage number'))
                if car_id not in config['allowedCars']:
                    if p['status']=='registered' or config.get('allowBreaks',True):
                        attempt_updates.require_recovery(self,p,'Car is outside the rally class; close the game and EXE launcher, then RUN again')
                        self.db.execute('COMMIT')
                    raise Fault(409, tr('Car is outside the rally class'))
                if p['car_id'] is not None and p['car_id'] != car_id:
                    if config.get('allowBreaks',True):
                        attempt_updates.require_recovery(self,p,'Restore the car selected on SS1 with RUN')
                        self.db.execute('COMMIT')
                    raise Fault(409, tr('Changing cars during the rally is not allowed'))
                reason = self._integrity_or_dnf(p, config, settings)
                if reason:
                    self.db.execute('COMMIT')
                    raise Fault(409, reason)
                self.db.execute('''UPDATE players SET status='active',car_id=?,
                    last_seen=?,started=? WHERE id=?''', (car_id, now, now, p['id']))
                self.db.execute('DELETE FROM launch_leases WHERE player_id=?', (p['id'],))
                self.db.execute('COMMIT')
                return {'ok': True, 'stageIndex': stage_index, 'status': 'active'}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def heartbeat(self, token, event_id, stage_index, settings=None, penalty_ms=None):
        with self.lock:
            self._sweep()
            p = self._auth(token)
            if p['event_id'] != event_id or p['stage_index'] != stage_index or p['status'] != 'active':
                raise Fault(409, tr('No active attempt'))
            _row, config = self.event(event_id)
            reason = self._integrity_or_dnf(p, config, settings)
            if reason:
                raise Fault(409, reason)
            attempt_updates.observe_penalty(self,p,stage_index,penalty_ms)
            self.db.execute('UPDATE players SET last_seen=? WHERE id=?', (time.time(), p['id']))
            return {'ok': True}

    def dnf(self, token, reason):
        with self.lock:
            self._begin()
            try:
                self._sweep()
                p = self._auth(token)
                if p['status'] != 'active':
                    raise Fault(409, tr('No active attempt'))
                self.db.execute("UPDATE players SET status='dnf',terminal_reason=?,started=NULL WHERE id=?",
                                (str(reason)[:300], p['id']))
                self.db.execute('COMMIT')
                return {'ok': True, 'status': 'dnf'}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def stage_end(self, token, event_id, index, clock_ms, settings=None, penalty_ms=None):
        'Persist telemetry timing and observed penalties immediately at the finish.'
        with self.lock:
            self._begin()
            try:
                self._sweep()
                p = self._auth(token)
                row, config = self.event(event_id)
                if p['event_id'] != event_id or p['status'] != 'active' or p['stage_index'] != index:
                    raise Fault(409, tr('Stage is not active / attempt already used'))
                reason = self._integrity_or_dnf(p, config, settings)
                if reason:
                    self.db.execute('COMMIT')
                    raise Fault(409, reason)
                if type(clock_ms) is not int or not 10000 <= clock_ms <= 4*60*60*1000:
                    raise Fault(400, tr('Invalid stage timer'))
                attempt_updates.observe_penalty(self,p,index,penalty_ms)
                now = time.time()
                self.db.execute('''INSERT INTO provisional(player_id,stage_index,clock_ms,finished)
                  VALUES(?,?,?,?)''', (p['id'], index, clock_ms, now))
                next_index = index + 1
                finished_all = next_index == len(config['stages'])
                if finished_all:
                    self.db.execute('DELETE FROM rally_checkpoints WHERE player_id=?',(p['id'],))
                self.db.execute('''UPDATE players SET status=?,stage_index=?,started=NULL,
                  last_seen=? WHERE id=?''', ('awaiting_results' if finished_all else 'ready',next_index,now,p['id']))
                self.db.execute('COMMIT')
                return {'ok':True,'status':'awaiting_results' if finished_all else 'ready',
                        'nextStage':next_index}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def finalize(self, token, provided):
        'Atomically commit a complete Rally Weekend, or nothing.'
        with self.lock:
            self._begin()
            try:
                self._sweep()
                p = self._auth(token)
                row, event = self.event(p['event_id'])
                stages = provided.get('stages')
                if p['status'] != 'awaiting_results' or p['stage_index'] != len(event['stages']):
                    raise Fault(409, tr('The rally is not ready for confirmation'))
                reason = self._integrity_or_dnf(p, event, provided.get('settings'))
                if reason:
                    self.db.execute('COMMIT')
                    raise Fault(409, reason)
                if not isinstance(stages, list) or len(stages) != len(event['stages']):
                    raise Fault(400, tr('An official stage result is missing'))
                prov = self.db.execute('SELECT * FROM provisional WHERE player_id=? ORDER BY stage_index',
                                       (p['id'],)).fetchall()
                if len(prov) != len(stages):
                    raise Fault(409, tr('Not all stages had a valid attempt'))
                prev_started = 0
                now = time.time()
                for idx, (record, stage, started) in enumerate(zip(stages, event['stages'], prov)):
                    if not isinstance(record, dict) or record.get('stageIndex') != idx or \
                            record.get('stageId') != stage['stageId'] or record.get('carId') != p['car_id']:
                        raise Fault(409, tr('Wrong stage or car in the official result'))
                    attempt_updates.validate_record(self,p,event,record,idx,prev_started)
                    raw, pen, total = (record.get(k) for k in ('rawMs','penaltyMs','totalMs'))
                    if any(type(x) is not int for x in (raw,pen,total)) or not 10000 <= raw <= 14400000 or \
                            not 0 <= pen <= 3600000 or raw + pen != total:
                        raise Fault(400, tr('Invalid time or penalty'))
                    acr_started = record.get('acrStarted')
                    if type(acr_started) not in (float,int) or not math.isfinite(acr_started) or \
                            not p['created'] - 60 <= acr_started <= now + 60 or \
                            acr_started <= prev_started:
                        raise Fault(409, tr('Invalid attempt start time in the ACR file'))
                    # Coarse sanity bound between telemetry and official timers; exceptions
                    # can occur with timing glitches and need manual review rather than fake score.
                    if abs(raw - started['clock_ms']) > 5000:
                        raise Fault(409, tr('Official timer differs from telemetry by more than 5 seconds'))
                    previous = self.db.execute('SELECT * FROM results WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
                    if previous and not attempt_updates.match_existing(previous,record):
                        raise Fault(409,'An accepted stage result is immutable')
                    if not previous:
                        self.db.execute('''INSERT INTO results(player_id,stage_index,stage_id,car_id,
                          raw_ms,penalty_ms,total_ms,acr_started,finished)
                          VALUES(?,?,?,?,?,?,?,?,?)''',
                          (p['id'], idx, stage['stageId'], p['car_id'], raw, pen, total, acr_started, now))
                    prev_started = acr_started
                self.db.execute("UPDATE players SET status='completed',last_seen=? WHERE id=?", (now,p['id']))
                self.db.execute('DELETE FROM rally_checkpoints WHERE player_id=?',(p['id'],))
                self.db.execute('COMMIT')
                return {'ok':True,'status':'completed'}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def board(self, event_id):
        with self.lock:
            self._sweep()
            _, event = self.event(event_id)
            players = self.db.execute('''SELECT p.id,p.nickname,p.status,p.stage_index,p.car_id,
                p.terminal_reason, COALESCE(SUM(r.total_ms),0) as total,
                COALESCE(SUM(r.penalty_ms),0) as penalty, COUNT(r.stage_index) as completed_stages
                FROM players p LEFT JOIN results r ON r.player_id=p.id
                WHERE p.event_id=? GROUP BY p.id''', (event_id,)).fetchall()
            stage_results = [dict(r) for r in self.db.execute('''SELECT r.player_id,r.stage_index,
                   r.stage_id,r.raw_ms,r.penalty_ms,r.total_ms,p.nickname
                   FROM results r JOIN players p ON p.id=r.player_id
                   WHERE p.event_id=? ORDER BY r.stage_index,r.total_ms,r.player_id''',(event_id,))]
            for r in stage_results: r['verified']=True
            pending=[dict(r) for r in self.db.execute('''SELECT v.player_id,v.stage_index,v.clock_ms AS raw_ms,
              v.clock_ms+COALESCE(t.penalty_ms,0) AS total_ms,t.penalty_ms,p.nickname FROM provisional v JOIN players p ON p.id=v.player_id
              LEFT JOIN telemetry_penalties t ON t.player_id=v.player_id AND t.stage_index=v.stage_index
              WHERE p.event_id=? AND NOT EXISTS (SELECT 1 FROM results r WHERE r.player_id=v.player_id AND r.stage_index=v.stage_index)''',(event_id,))]
            for r in pending:
                r.update(stage_id=event['stages'][r['stage_index']]['stageId'],verified=False)
            stage_results.extend(pending)
            additions=admin_penalties.totals(self,event_id)
            for result in stage_results:
                extra=additions.get((result['player_id'],result['stage_index']),{'amount':0,'reasons':[]})
                result['admin_penalty_ms']=extra['amount'];result['admin_reasons']=extra['reasons']
                result['total_ms']+=extra['amount']
                if result['penalty_ms'] is not None:result['penalty_ms']+=extra['amount']
            stage_results.sort(key=lambda r:(r['stage_index'],r['total_ms'],r['player_id']))
            players=[dict(p) for p in players]
            for p in players:
                p.update(attempt_updates.recovery_state(self,p['id']))
                p['dnfStage']=min(p['stage_index']+1,len(event['stages'])) if p['status']=='dnf' else None
                rows=[r for r in stage_results if r['player_id']==p['id']]
                p['live_total']=sum(r['total_ms'] for r in rows)
                p['admin_penalty_ms']=sum(r['admin_penalty_ms'] for r in rows)
                p['total']+=p['admin_penalty_ms']
                p['pending_stages']=sum(not r['verified'] for r in rows)
            return {'event': event, 'players': [dict(p) for p in sorted(players,
                    key=lambda p:(p['status'] != 'completed', -p['completed_stages'], p['total'], p['nickname'].lower()))],
                    'stageResults':stage_results}


STYLE = r"""
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;
background:#0d131a;color:#f4f7fb;margin:0;line-height:1.55}
main{max-width:1120px;margin:50px auto;padding:0 24px}
h1{font-size:2.5rem;letter-spacing:-.05em;margin:0 0 12px}p,small{color:#a0afc0}
header{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:35px}
a{color:#83d9ff}.card{background:#19232e;border:1px solid #344351;border-radius:15px;padding:25px;margin:15px 0}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:14px;border-bottom:1px solid #33404d}
th{font-size:.82rem;text-transform:uppercase;letter-spacing:.06em;color:#9eb1c4}tbody tr:last-child td{border:0}
.good{color:#5adeb0}.bad{color:#ff828a}.muted{color:#9eb1c4}.mono{font-variant-numeric:tabular-nums}
footer{padding:30px 0;color:#8195a7;font-size:.85rem}
button.run{padding:13px 23px;border:0;border-radius:10px;background:#13b887;color:#071a16;font-weight:800;cursor:pointer;font-size:1rem}button.run:hover{background:#3ee2b3}
"""


def site(store, identifier=None, browser=None, csrf=None, member=None):
    """Modern public pages. All data, CSRF forms and route targets retain V5 behavior."""
    from site_theme import shell
    from rally_details import stage_schedule, rally_conditions

    def pill(text, cls=''):
        return '<span class="chip '+cls+'">'+escape(text)+'</span>'

    def date_label(value):
        try:
            return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone(timedelta(hours=2))).strftime('%d.%m.%Y · %H:%M UTC+2')
        except (ValueError,TypeError):
            return str(value)[:24]

    now=time.time()
    if not identifier:
        evs=store.listing()
        upcoming=sum(utc_epoch(ev['opensAt'])>now for ev in evs)
        active=sum(utc_epoch(ev['opensAt'])<=now<=utc_epoch(ev['closesAt']) for ev in evs)
        content=(tr('<section class="hero"><span class="eyebrow">Assetto Corsa Rally · Club competition</span><h1>Rallies and events</h1><p>Choose a rally, read the rules and start with one click. Stages, standings and club results in one place.</p><p><a class="btn-link" href="/download">⬇ DOWNLOAD WINDOWS LAUNCHER</a>\u3000<a class="btn-link" href="/guide">Getting started →</a></p><div class="stats"><div class="stat"><strong>')+str(len(evs))+tr('</strong><span>Rallies</span></div><div class="stat"><strong>')+str(active)+tr('</strong><span>Live</span></div><div class="stat"><strong>')+str(upcoming)+tr('</strong><span>Scheduled</span></div></div></section>'))
        tagline=club_settings.branding()['tagline']
        if tagline:
            content=re.sub(r'(<span class="eyebrow">).*?(</span>)',lambda m:m[1]+escape(tagline)+m[2],content,count=1)
        if member:
            content+=(tr('<section class="card"><span class="section-kicker">Your profile</span>Welcome, <strong>')+escape(member['nickname'])+
                      tr('</strong>. <a href="/club">View club account →</a></section>'))
        content+=(tr('<div class="card-head"><div><span class="section-kicker">Calendar</span><h2>Available rallies</h2></div><a class="btn-link" href="/seasons">Season standings →</a></div>'))
        content+='<div class="grid-cards">'
        archived=[]
        for ev in evs:
            eid=escape(ev['id'],quote=True)
            opening,closing=utc_epoch(ev['opensAt']),utc_epoch(ev['closesAt'])
            label,cl=(tr('LIVE'),'chip-active') if opening<=now<=closing else ((tr('COMING SOON'),'chip-upcoming') if now<opening else (tr('FINISHED'),'chip-ended'))
            card=('<article class="rally-card"><div class="hero-inline">'+pill(label,cl)+
                      '<span class="muted">'+escape(ev['location'])+'</span></div>'
                      '<h2><a href="/rally/'+eid+'">'+escape(ev['name'])+'</a></h2>'
                      '<p>'+str(len(ev['stages']))+tr(' special stages · ')+escape(ev['carClass'])+'</p>'
                      '<div class="rally-foot"><small>'+escape(date_label(ev['opensAt']))+'</small>'
                      '<a class="btn-link" href="/rally/'+eid+tr('">View rally →</a></div></article>'))
            if closing<now: archived.append(card)
            else: content+=card
        content+='</div>'
        if archived: content+='<details class="round archive"><summary>'+escape(tr('Past rallies'))+' · '+str(len(archived))+'</summary><div class="grid-cards">'+''.join(archived)+'</div></details>'
        if not evs:content+=tr('<div class="empty">No rallies yet. The organizer will add them in the administrator panel.</div>')
        return shell(tr('ACR Rally Club — Rallies'),content,active='rallies')

    data=store.board(identifier)
    ev=data['event'];eid=escape(ev['id'],quote=True)
    total_stages=len(ev['stages'])
    finished=sum(p['status']=='completed' for p in data['players'])
    content=(tr('<div><a class="backlink" href="/">← All rallies</a></div><section class="hero"><span class="eyebrow">Rally Weekend / ')+escape(ev['location'])+'</span>'
             '<h1>'+escape(ev['name'])+'</h1><p>'+escape(ev['carClass'])+' · '+str(total_stages)+tr(' special stages</p><div class="stats"><div class="stat"><strong>')+str(total_stages)+tr('</strong><span>stages</span></div><div class="stat"><strong>')+str(len(data['players']))+tr('</strong><span>Participants</span></div><div class="stat"><strong>')+str(finished)+tr('</strong><span>Finished</span></div></div></section><div class="split"><section class="card"><span class="section-kicker">Round information</span><h2>Schedule</h2><p class="rally-meta"><strong>Opens:</strong> ')+escape(date_label(ev['opensAt']))+tr('</p><p class="rally-meta"><strong>Closes:</strong> ')+escape(date_label(ev['closesAt']))+tr('</p><p class="rally-meta"><strong>Location:</strong> ')+escape(ev['location'])+tr('</p><p class="rally-meta"><strong>Car class:</strong> ')+escape(ev['carClass'])+'</p>'+stage_schedule(ev)+'</section><div class="rally-side">')
    content+='<div id="rally-recovery-warning">'
    warned=[p for p in data['players'] if p.get('recoveryRequired')]
    if warned:
        content+='<div class="recovery-warning" role="status">'+escape(tr('Configuration or car does not match the rally. Your attempt is preserved. Close ACR and the launcher EXE before RUN. If the EXE is still open, confirm its restart in the dialog. No times are accepted until recovery.'))+'<br>'+escape(', '.join(p['nickname'] for p in warned))+'</div>'
    content+='</div>'
    content+=tr('<section class="card"><span class="section-kicker">Driver area</span><h2>Your entry</h2>')
    if csrf:
        csrf_field='<input type="hidden" name="csrf" value="'+escape(csrf,quote=True)+'">'
        if browser is None and member is not None:
            content+=tr('<p>Your racing nickname is <strong>')+escape(member['nickname'])+'</strong>.</p>'
            content+=('<form action="/web/enroll" method="post">'+csrf_field+
                      '<input type="hidden" name="eventId" value="'+eid+tr('"><button class="run" type="submit">REGISTER FOR RALLY</button></form>'))
        elif browser is None:
            seasonal=store.db.execute('SELECT 1 FROM season_events WHERE event_id=?',(ev['id'],)).fetchone()
            content+=tr('<p><a href="/club">Sign in through Steam</a> and choose your club nickname to enter rallies.</p>')
            if not seasonal and not PUBLIC_URL:
                content+=('<form action="/web/enroll" method="post">'+csrf_field+
                    '<input type="hidden" name="eventId" value="'+eid+tr('"><label for="nickname">Driver nickname</label><div class="toolbar"><input id="nickname" name="nickname" required minlength="2" maxlength="24" autocomplete="nickname" placeholder="Your nickname"><button class="run" type="submit">REGISTER FOR RALLY</button></div></form>'))
        else:
            status=browser['status']
            labels={'registered':tr('REGISTERED'),'ready':tr('BETWEEN STAGES'),'active':tr('ON STAGE'),'completed':tr('FINISH'),'dnf':'DNF','awaiting_results':tr('VERIFICATION')}
            content+='<p><strong>'+escape(browser['nickname'])+'</strong> · '+pill(labels.get(status,status),'status-done' if status=='completed' else 'status-dnf' if status=='dnf' else '')+'</p>'
            waiting_division=False
            if member is not None:
                try:ensure_division_assigned(store,ev['id'],member['id'])
                except Fault:waiting_division=True
            rally_open=utc_epoch(ev['opensAt']) <= time.time() < utc_epoch(ev['closesAt'])
            if status in ('registered','ready') and not waiting_division and rally_open:
                content+=('<form action="/web/run" method="post">'+csrf_field+
                    '<input type="hidden" name="eventId" value="'+eid+tr('"><button class="run" type="submit">▶ RUN RALLY</button></form><p><small>Need the launcher? <a href="/launcher">Installation guide</a>.</small></p>'))
            elif waiting_division:
                content+=tr('<p class="muted">Waiting for the organizer to assign your division.</p>')
            elif status in ('registered','ready') and time.time() < utc_epoch(ev['opensAt']):
                content+=tr('<p class="muted">Entry confirmed. RUN RALLY will be available from ')+escape(date_label(ev['opensAt']))+'.</p>'
            else:
                content+=tr('<p class="muted">RUN is locked — the attempt is in progress or has ended.</p>')
    content+='</section>'+rally_conditions(ev)+'</div></div>'
    content+=tr('<section class="card"><div class="card-head"><div><span class="section-kicker">Rally standings</span><h2>Overall results</h2></div>').replace('<section class="card">','<section class="card" id="rally-classification">',1)+pill(str(len(data['players']))+tr(' drivers'))+'</div>'
    content+=(tr('<div class="toolbar"><label for="driver-search">Search drivers</label><input type="search" id="driver-search" placeholder="Enter a driver nickname…" autocomplete="off"></div>'))
    content+=(tr('<div class="table-scroll"><table><thead><tr><th>Position</th><th>Driver</th><th>Car</th><th>SS</th><th>Total time</th><th>Status</th></tr></thead><tbody>'))
    for i,p in enumerate(data['players'],1):
        label={'completed':tr('FINISH'),'dnf':'DNF','ready':tr('BETWEEN STAGES'),'active':tr('ON STAGE'),'registered':tr('REGISTERED'),'awaiting_results':tr('VERIFICATION')}.get(p['status'],p['status'])
        status_css='status-done' if p['status']=='completed' else 'status-dnf' if p['status']=='dnf' else ''
        if p.get('recoveryRequired'):
            label=tr('RESTORE WITH RUN')
            status_css='status-warning'
        status_text=label+((' · '+str(p['terminal_reason'])[:100]) if p['status']=='dnf' and p.get('terminal_reason') else '')
        if p.get('dnfStage'):
            status_text='DNF · '+tr('SS ')+str(p['dnfStage'])+((' · '+str(p['terminal_reason'])[:100]) if p.get('terminal_reason') else '')
        result=format_ms(p.get('live_total',p['total'])) if p['stage_index'] else '—'
        if p.get('pending_stages'): result+=' · '+tr('Provisional')
        admin_note=('<small class="admin-penalty-note">'+escape(tr('Admin penalty'))+' +'+format_ms(p['admin_penalty_ms'])+'</small>') if p.get('admin_penalty_ms') else ''
        content+=('<tr data-driver="'+escape(p['nickname'],quote=True)+'"><td class="rank-col">'+str(i)+'</td><td><strong>'+escape(p['nickname'])+'</strong></td>'
                  '<td>'+escape(p['car_id'] or '—')+'</td><td>'+str(p['stage_index'])+'/'+str(total_stages)+'</td>'
                  '<td class="mono"><strong>'+escape(result)+'</strong>'+admin_note+'</td><td>'+pill(status_text,status_css)+'</td></tr>')
    content+='</tbody></table></div>'
    if not data['players']:content+=tr('<div class="empty">No drivers have registered yet.</div>')
    content+=tr('<p class="table-meta">Only drivers with FINISH status count toward the final standings. DNF prevents another attempt.</p></section>')
    content+=tr('<section class="card"><span class="section-kicker">Detailed results</span><h2>Individual stage results</h2>').replace('<section class="card">','<section class="card" id="rally-stage-results">',1)
    for index,stage in enumerate(ev['stages']):
        stage_rows=[r for r in data['stageResults'] if r['stage_index']==index]
        content+='<details class="round"'+''+tr('><summary><span>SS ')+str(index+1)+' · '+escape(stage['stageId'])+'</span>'+pill(str(len(stage_rows))+tr(' results'))+'</summary>'
        content+=tr('<div class="table-scroll"><table><thead><tr><th>#</th><th>Driver</th><th>RAW</th><th>Penalties</th><th>Official time</th></tr></thead><tbody>')
        for place,r in enumerate(stage_rows,1):
            penalty_css='bad' if (r['penalty_ms'] is not None and r['penalty_ms']>0) or r.get('admin_penalty_ms',0)>0 else 'good' if r['penalty_ms']==0 else 'muted'
            admin_note=('<small class="admin-penalty-note">'+escape(tr('Admin penalty'))+' +'+format_ms(r['admin_penalty_ms'])+' · '+escape('; '.join(r['admin_reasons']))+'</small>') if r.get('admin_penalty_ms') else ''
            content+=('<tr><td class="rank-col">'+str(place)+'</td><td>'+escape(r['nickname'])+'</td>'
                    '<td class="mono">'+format_ms(r['raw_ms'])+'</td>'
                    '<td class="mono '+penalty_css+'">'+('+'+format_ms(r['penalty_ms']) if r['penalty_ms'] is not None else '+'+format_ms(r['admin_penalty_ms'])+' + ?' if r.get('admin_penalty_ms') else '—')+'</td>'
                    '<td class="mono"><strong>'+format_ms(r['total_ms'])+'</strong>'+admin_note+('' if r.get('verified',True) else '<small class="muted"> '+escape(tr('Telemetry · pending save confirmation'))+'</small>')+'</td></tr>')
        content+='</tbody></table></div>'
        if not stage_rows:content+=tr('<div class="empty">Results appear after every stage; telemetry times await save confirmation.</div>')
        content+='</details>'
    content+='</section>'
    from site_theme import RALLY_FILTER_JS
    trace_section,trace_script=telemetry_audit.section(ev['id'])
    run_section,run_script=__import__('run_dialog').section()
    return shell('ACR Rally Club — '+ev['name'],content+trace_section+run_section,active='rallies',scripts=RALLY_FILTER_JS+__import__('live_results').SCRIPT+trace_script+run_script)


def _is_loopback_hostname(hostname):
    """Only the browser's standard loopback aliases; never a domain ending in 'localhost'."""
    if hostname is None:
        return False
    name = hostname.lower().rstrip('.')
    if name == 'localhost':
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def allowed_browser_origin(origin, request_host, bound_port):
    """Check Origin without confusing localhost and 127.0.0.1 on the same local port.

    A foreign domain, different port, `null`, malformed origin or embedded path
    still fails. For non-loopback hosts we retain the old exact-origin check.
    CSRF cookie+form token is checked separately and always remains mandatory.
    """
    if not isinstance(origin, str) or not isinstance(request_host, str):
        return False
    try:
        src = urlsplit(origin)
        dest = urlsplit('http://' + request_host)
        if (src.scheme not in ('http', 'https') or
                src.username is not None or src.password is not None or
                src.path or src.query or src.fragment or
                dest.username is not None or dest.password is not None or
                dest.path or dest.query or dest.fragment or
                src.hostname is None or dest.hostname is None):
            return False
        # URL parsing also validates bracketed IPv6 and numeric ports.
        src_port = src.port if src.port is not None else (443 if src.scheme == 'https' else 80)
        dest_port = dest.port if dest.port is not None else 80
        if _is_loopback_hostname(src.hostname) and _is_loopback_hostname(dest.hostname):
            return src_port == dest_port == bound_port
        return origin in ('http://' + request_host, 'https://' + request_host)
    except ValueError:
        return False



def allowed_null_local_form_origin(origin, request_host, bound_port, peer_address, fetch_site):
    """Compatibility for browsers sending Origin: null on this LOCAL test server.

    This is not a general allowance for opaque origins. A matching hidden CSRF
    token and CSRF cookie are mandatory in _require_web_form(), and cross-site
    fetch metadata is rejected. This exception is valid only for loopback peers
    accessing the expected loopback hostname/port.
    """
    if origin != 'null' or fetch_site not in (None, '', 'same-origin', 'same-site', 'none'):
        return False
    try:
        if not ipaddress.ip_address(peer_address).is_loopback:
            return False
        target = urlsplit('http://' + request_host)
        if (target.username is not None or target.password is not None or
                target.path or target.query or target.fragment or
                target.hostname is None or
                not _is_loopback_hostname(target.hostname)):
            return False
        target_port = target.port if target.port is not None else 80
        return target_port == bound_port
    except (ValueError, TypeError):
        return False



def private_admin_page(html_page, url_path):
    # Only admin HTML links are rewritten; API routes remain /api/admin/*.
    return (html_page.replace('href="/admin/seasons"', 'href="'+url_path+'/seasons"')
                     .replace('href="/admin"', 'href="'+url_path+'"'))

def make_handler(store, admin=None, catalog_root=None):
    # A separate password file is generated automatically on first server start.
    admin = admin or AdminAuth()
    secret_admin_path = get_admin_path(admin.key_path)
    catalog_root = catalog_root or ROOT
    limiter = RateLimiter()
    class Handler(BaseHTTPRequestHandler):
        server_version = 'ACRClubLocal/0.1'
        def _write(self, code, value, mime='application/json; charset=utf-8', extra_headers=None):
            if mime.startswith('text/html') and isinstance(value, str):
                value = localize_document(value)
            payload = value.encode('utf-8') if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Language', language())
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
            if PUBLIC_URL:
                self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
            if extra_headers:
                for header, val in extra_headers.items():
                    for item in (val if isinstance(val, list) else [val]):
                        self.send_header(header, item)
            self.end_headers()
            self.wfile.write(payload)

        def _gateway_guard(self):
            if not gateway_ok(self.headers) or not check_host(self.headers):
                raise Fault(403, tr('Invalid HTTPS gateway or server address'))

        def _remote_ip(self):
            return remote_addr(self.headers,self.client_address[0])

        def _client_version(self):
            if not version_allowed(self.headers.get('X-ACR-Launcher-Version')):
                raise Fault(426, tr('Outdated launcher: version 0.2.0 or a compatible legacy 6.3.1 launcher is required. Install the latest EXE from /download. Updating the server ZIP does not replace the installed launcher.'))

        def _limit(self, name, count):
            if not limiter.allow(self._remote_ip(),name,count):
                raise Fault(429, tr('Too many requests. Try again later.'))

        def _secure_cookie(self):
            return bool(PUBLIC_URL) or self.headers.get('X-Forwarded-Proto')=='https'

        def _cookies(self):
            try:
                cookie = SimpleCookie()
                cookie.load(self.headers.get('Cookie', ''))
                return {k: v.value for k,v in cookie.items()}
            except Exception:
                return {}

        def _steam_origin(self):
            return PUBLIC_URL or 'http://127.0.0.1:' + str(self.server.server_port)

        def _club_member(self, cookies):
            return member_by_cookie(store, cookies.get('acrclub_member'), steam_only=bool(PUBLIC_URL))

        def log_message(self, fmt, *args):
            # OpenID assertions and state values are authentication material.
            if self.path.startswith('/auth/steam/callback'):
                return super().log_message('Steam callback %s', str(args[1]) if len(args)>1 else '')
            return super().log_message(fmt, *args)

        def _form(self):
            ctype = self.headers.get('Content-Type','').split(';',1)[0].lower()
            if ctype != 'application/x-www-form-urlencoded':
                raise Fault(415, tr('An HTML form is required'))
            try:
                length = int(self.headers.get('Content-Length','0'))
            except ValueError:
                raise Fault(400, tr('Invalid Content-Length'))
            if not 0 < length <= 4096:
                raise Fault(413, tr('Invalid form length'))
            try:
                data = parse_qs(self.rfile.read(length).decode('utf-8'), strict_parsing=True)
                return {k:v[0] for k,v in data.items()}
            except (ValueError, UnicodeError):
                raise Fault(400, tr('Invalid form data'))

        def _require_web_form(self, data):
            cookies = self._cookies()
            if not csrf_ok(cookies.get('acrclub_csrf'), data.get('csrf')):
                raise Fault(403, tr('Missing or invalid form token (CSRF)'))
            origin = self.headers.get('Origin')
            fetch_site = self.headers.get('Sec-Fetch-Site')
            # Sec-Fetch-Site can identify genuine cross-site requests even when
            # Origin is omitted or set to the opaque literal "null".
            if fetch_site == 'cross-site':
                print('Rejected cross-site web form:', repr(origin), flush=True)
                raise Fault(403, tr('Request origin is not allowed'))
            if PUBLIC_URL and not browser_origin(origin, self.headers):
                raise Fault(403, tr('Forms from another domain are not allowed'))
            if origin and not PUBLIC_URL:
                host = self.headers.get('Host', '')
                allowed = allowed_browser_origin(origin, host, self.server.server_port)
                if origin == 'null':
                    allowed = allowed_null_local_form_origin(
                        origin, host, self.server.server_port,
                        self.client_address[0], fetch_site)
                if not allowed:
                    print('Rejected browser Origin:', repr(origin[:180]),
                          'Host:', repr(host[:180]),
                          'Sec-Fetch-Site:', repr(fetch_site), flush=True)
                    raise Fault(403, tr('Request origin is not allowed'))
            return cookies

        def _redirect(self, location, *, cookie=None):
            headers={'Location':location}
            if cookie: headers['Set-Cookie']=cookie
            return self._write(303, '', 'text/plain; charset=utf-8', headers)

        def _body(self):
            try:
                length = int(self.headers.get('Content-Length','0'))
            except ValueError:
                raise Fault(400, tr('Invalid Content-Length'))
            if not 0 < length <= (400000 if self.path == '/api/admin/branding' else 3500000 if self.path in ('/api/checkpoint','/api/recovery-checkpoint') else MAX_BODY):
                raise Fault(413, tr('Payload too large'))
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise Fault(400, tr('Invalid JSON'))
            if not isinstance(body, dict):
                raise Fault(400, tr('A JSON object is required'))
            return body

        def _token(self):
            auth = self.headers.get('Authorization','')
            if not auth.startswith('Bearer '):
                raise Fault(401, tr('Missing token'))
            return auth[7:]

        def _admin_cookie(self):
            try:
                cookie = SimpleCookie()
                cookie.load(self.headers.get('Cookie', ''))
                part = cookie.get('acrclub_admin')
                return part.value if part else None
            except Exception:
                return None

        def _require_admin_local(self):
            if PUBLIC_URL:
                self._gateway_guard()  # Caddy must also protect /admin and /api/admin/*
                return
            try:
                if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                    raise Fault(403, tr('The administrator panel is only available locally on the server'))
            except ValueError:
                raise Fault(403, tr('Invalid connection address'))

        def _require_admin(self):
            self._require_admin_local()
            if not admin.valid(self._admin_cookie()):
                raise Fault(401, tr('No administrator session'))

        def _require_admin_post(self):
            # Cross-site HTML forms cannot send this header; foreign fetch()
            # with the header triggers a denied CORS preflight.
            if self.headers.get('X-ACR-Admin') != '1':
                raise Fault(403, tr('Invalid administrator request'))
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise Fault(403, tr('Request origin is not allowed'))
            origin = self.headers.get('Origin')
            if origin and not (browser_origin(origin, self.headers) if PUBLIC_URL else allowed_browser_origin(
                    origin, self.headers.get('Host', ''), self.server.server_port)):
                print('Rejected admin Origin:', repr(origin[:180]),
                      'Host:', repr(self.headers.get('Host', '')[:180]), flush=True)
                raise Fault(403, tr('Request origin is not allowed'))
            content_type = self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if content_type != 'application/json':
                raise Fault(415, tr('application/json is required'))

        @request_localized
        @club_settings.context(store)
        def do_GET(self):
            try:
                self._gateway_guard()
                path = unquote(urlparse(self.path).path)
                if path == '/auth/steam':
                    self._limit('steam-sign-in', 20)
                    location, state = steam_auth.start(store, self._steam_origin())
                    return self._redirect(location, cookie=steam_auth.cookie('acrclub_steam_state', state, secure=self._secure_cookie()))
                if path == '/auth/steam/callback':
                    self._limit('steam-callback', 20)
                    pending = steam_auth.callback(store, urlparse(self.path).query,
                                                  self._cookies().get('acrclub_steam_state'), self._steam_origin())
                    expired = steam_auth.cookie('acrclub_steam_state', '', secure=self._secure_cookie(), age=0)
                    if pending is None:
                        return self._redirect('/club', cookie=expired)
                    account = steam_finish(store, pending)
                    cookies = [expired]
                    if account:
                        cookies += [club_cookie(account['token'], secure=self._secure_cookie()),
                                    steam_auth.cookie('acrclub_steam_pending', '', secure=self._secure_cookie(), age=0)]
                    else:
                        cookies += [steam_auth.cookie('acrclub_steam_pending', pending, secure=self._secure_cookie()),
                                    steam_auth.cookie('acrclub_member', '', secure=self._secure_cookie(), age=0)]
                    return self._redirect('/club', cookie=cookies)
                if path == '/language':
                    query = parse_qs(urlparse(self.path).query)
                    chosen = query.get('lang', [''])[0]
                    if chosen not in SUPPORTED_LANGUAGES:
                        raise Fault(400, tr('Unsupported language'))
                    return self._write(303, '', 'text/plain; charset=utf-8', {
                        'Location': safe_return_path(query.get('next', ['/'])[0]),
                        'Set-Cookie': language_cookie(chosen, self._secure_cookie()),
                    })
                if path == secret_admin_path + '/seasons':
                    self._require_admin_local()
                    return self._write(200, private_admin_page(season_admin_html(), secret_admin_path), 'text/html; charset=utf-8',
                        {'Content-Security-Policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'"})
                if path == '/api/admin/discord':
                    self._require_admin()
                    return self._write(200, discord_notifications.status(store))
                if path == '/api/admin/seasons':
                    self._require_admin()
                    return self._write(200, {'seasons':list_seasons(store)})
                if path == '/api/admin/club-members':
                    self._require_admin()
                    return self._write(200, {'members':club_members(store)})
                if path.startswith('/api/admin/seasons/'):
                    self._require_admin()
                    return self._write(200, season_config(store,path.removeprefix('/api/admin/seasons/')))
                if path == '/healthz':
                    return self._write(200, {'status':'ok'})
                if path == '/download':
                    if not DOWNLOAD_URL:
                        raise Fault(503,tr('The installer will be available after the first GitHub Release is published'))
                    return self._write(302,'','text/plain; charset=utf-8',{'Location':launcher_release_page(DOWNLOAD_URL)})
                if path == '/guide':
                    from driver_guide import page
                    return self._write(200,page(),'text/html; charset=utf-8')
                if path == '/club':
                    csrf=secrets.token_urlsafe(24)
                    cookies = self._cookies()
                    member=self._club_member(cookies)
                    pending=steam_auth.pending_steam_id(store,cookies.get('acrclub_steam_pending'))
                    from site_theme import shell
                    content=shell(tr('ACR Rally Club — Club account'),
                                  tr('<section class="hero"><span class="eyebrow">Club members</span><h1>Club account</h1><p>Your nickname for the season, rallies and divisions.</p></section>')+
                                  club_page(member,csrf,pending=bool(pending)),active='club')
                    return self._write(200,content,'text/html; charset=utf-8',
                         {'Set-Cookie':make_cookie('acrclub_csrf',csrf,secure=self._secure_cookie())})
                if path == '/seasons':
                    from season_views import season_list
                    return self._write(200,season_list(list_seasons(store)),'text/html; charset=utf-8')
                if path.startswith('/season/') and len(path.split('/'))==3:
                    from season_views import season_detail
                    return self._write(200,season_detail(scoring(store,path.rsplit('/',1)[-1])),
                                       'text/html; charset=utf-8')
                if path == '/api/seasons':
                    return self._write(200,{'seasons':list_seasons(store)})
                if path.startswith('/api/seasons/'):
                    return self._write(200,scoring(store,path.rsplit('/',1)[-1]))
                if path == secret_admin_path:
                    self._require_admin_local()
                    return self._write(200, private_admin_page(admin_html(), secret_admin_path), 'text/html; charset=utf-8',
                                       {'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; form-action 'self'; base-uri 'none'"})
                if path == '/club-logo':
                    logo=club_settings.public(store)['logo']
                    if not logo: raise Fault(404,'Logo not set')
                    raw=base64.b64decode(logo.split(',',1)[1])
                    self.send_response(200)
                    self.send_header('Content-Type','image/png')
                    self.send_header('Content-Length',str(len(raw)))
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Cache-Control','no-cache')
                    self.send_header('Content-Security-Policy',"default-src 'none'")
                    self.end_headers();self.wfile.write(raw);return
                if path == '/api/checkpoint':
                    self._client_version()
                    return self._write(200,attempt_updates.checkpoint(store,self._token()))
                if path == '/api/recovery-checkpoint':
                    return self._write(200,attempt_updates.checkpoint(store,self._token(),recovery=True))
                if path == '/api/catalog':
                    return self._write(200,club_settings.catalog(store,catalog_root))
                if path == '/api/admin/time-penalties':
                    self._require_admin()
                    event_id=parse_qs(urlparse(self.path).query).get('eventId',[''])[0]
                    return self._write(200,admin_penalties.listing(store,event_id))
                if path.startswith('/api/telemetry/'):
                    parts=path.split('/')
                    if len(parts)==4:
                        return self._write(200,telemetry_audit.summaries(store,parts[3]),'text/html; charset=utf-8')
                    if len(parts)==6 and parts[4]=='driver' and parts[5].isdigit():
                        return self._write(200,telemetry_audit.driver(store,parts[3],int(parts[5])),'text/html; charset=utf-8')
                    raise Fault(404,tr('Not found'))
                if path == '/api/admin/branding':
                    self._require_admin()
                    return self._write(200,club_settings.public(store))
                if path == '/api/admin/catalog':
                    self._require_admin()
                    try:
                        return self._write(200, club_settings.catalog(store, catalog_root))
                    except ValueError as exc:
                        raise Fault(500, str(exc))
                if path == '/api/admin/events':
                    self._require_admin()
                    return self._write(200, {'events': store.admin_listing()})
                if path == '/launcher':
                    from site_theme import shell
                    info = (tr('<section class="hero"><span class="eyebrow">Start a rally / Windows</span><h1>ACR Club Launcher</h1><p>Install once. Then start rallies with one click on RUN RALLY.</p><p><a class="btn-link" href="/download">⬇ Download Windows installer</a></p></section><section class="card"><h2>How to get started?</h2><p>Download the installer, run it and allow the launcher to open from the website.</p><p>Sign in through Steam, choose a club nickname and a rally and click RUN RALLY. The launcher prepares the save and starts ACR through Steam.</p><p>Navigate manually to START STAGE. Details: <a href="/guide">driver guide →</a></p></section>'))
                    return self._write(200, shell('ACR Rally Club — Launcher',info,active='launcher'),
                                       'text/html; charset=utf-8')
                if path in ('/','/index.html'):
                    return self._write(200, site(store), 'text/html; charset=utf-8')
                if path.startswith('/rally/') and len(path.split('/')) == 3:
                    event_id = path.split('/')[2]
                    cookies=self._cookies()
                    member=self._club_member(cookies)
                    if member is not None:
                        # A persistent club account is authoritative. Never let a
                        # stale per-event browser cookie show another rider's identity.
                        actor=club_player(store,event_id,member['id'])
                    else:
                        actor=None if PUBLIC_URL else browser_player(store,cookies.get('acrclub_browser'),event_id)
                    csrf = secrets.token_urlsafe(24)
                    return self._write(200, site(store, event_id, actor, csrf, member), 'text/html; charset=utf-8',
                                       {'Set-Cookie':make_cookie('acrclub_csrf',csrf,
                                           secure=self._secure_cookie())})
                if path == '/api/events':
                    return self._write(200, {'events': store.listing()})
                if path.startswith('/api/events/'):
                    return self._write(200, {'event': store.event(path.rsplit('/',1)[-1])[1]})
                if path == '/api/me':
                    return self._write(200, store.state(self._token()))
                if path.startswith('/api/results/'):
                    return self._write(200,site(store,path.rsplit('/',1)[-1]),'text/html; charset=utf-8')
                if path.startswith('/api/board/'):
                    return self._write(200, store.board(path.rsplit('/',1)[-1]))
                raise Fault(404, tr('Not found'))
            except Fault as exc:
                if self.path.startswith('/auth/steam'):
                    from site_theme import shell
                    page = shell(tr('Steam sign-in'), '<section class="card"><h1>'+tr('Steam sign-in')+'</h1><p>'+escape(str(exc))+'</p><p><a class="btn-link" href="/auth/steam">'+tr('Try Steam sign-in again')+'</a></p></section>',active='club')
                    return self._write(exc.code,page,'text/html; charset=utf-8')
                self._write(exc.code, {'error': str(exc)})
            except Exception:
                self._write(500, {'error': tr('Server error')})

        @request_localized
        @club_settings.context(store)
        def do_POST(self):
            try:
                self._gateway_guard()
                path = unquote(urlparse(self.path).path)
                if path == '/web/club/register':
                    self._limit(path,6)
                    data=self._form()
                    cookies=self._require_web_form(data)
                    account=steam_finish(store,cookies.get('acrclub_steam_pending'),data.get('nickname',''))
                    return self._redirect('/club',cookie=[club_cookie(account['token'],secure=self._secure_cookie()),
                        steam_auth.cookie('acrclub_steam_pending','',secure=self._secure_cookie(),age=0)])
                if path in ('/web/club/nickname','/web/club/logout'):
                    self._limit(path,20)
                    data=self._form()
                    cookies=self._require_web_form(data)
                    if path.endswith('/nickname'):
                        change_nickname(store,cookies.get('acrclub_member'),data.get('nickname',''))
                        return self._redirect('/club')
                    club_logout(store,cookies.get('acrclub_member'),cookies.get('acrclub_steam_pending'))
                    return self._redirect('/club',cookie=[
                        steam_auth.cookie('acrclub_member','',secure=self._secure_cookie(),age=0),
                        steam_auth.cookie('acrclub_steam_pending','',secure=self._secure_cookie(),age=0)])
                if path in ('/web/enroll','/web/run'):
                    self._limit(path,20)
                    data = self._form()
                    cookies = self._require_web_form(data)
                    event_id = data.get('eventId','')
                    # Validate an existing event and forbid path-based redirects.
                    store.event(event_id)
                    member=self._club_member(cookies)
                    if PUBLIC_URL and member is None:
                        raise Fault(401,tr('Sign in through Steam and choose a club nickname before entering or starting a rally.'))
                    if path == '/web/enroll':
                        if PUBLIC_URL and member is None:
                            raise Fault(403, tr('A club account is required in the public league (/club)'))
                        if member is not None:
                            club_join(store,event_id,member['id'])
                            return self._redirect('/rally/'+quote(event_id,safe=''))
                        cookie = enroll(store, event_id, data.get('nickname',''))
                        return self._redirect('/rally/' + quote(event_id, safe=''),
                                              cookie=make_cookie('acrclub_browser',cookie,secure=self._secure_cookie()))
                    if 'application/json' not in self.headers.get('Accept',''):
                        return self._redirect('/rally/'+quote(event_id,safe=''))
                    if member is not None:
                        ticket=mint_club_ticket(store,event_id,member['id'])
                    else:
                        ticket = mint_ticket(store, cookies.get('acrclub_browser'), event_id)
                    protocol = 'acrclub://start?ticket=' + quote(ticket,safe='')
                    return self._write(200, {'protocol':protocol,'expiresIn':60})
                if path.startswith('/web/'):
                    raise Fault(404, tr('Not found'))
                data = self._body()
                if path.startswith('/api/admin/'):
                    self._require_admin_local()
                    self._require_admin_post()
                    if path == '/api/admin/login':
                        self._limit(path,6)
                        token = admin.login(data.get('key'), self._remote_ip())
                        if not token:
                            store.audit(self.client_address[0], 'login_failed', None, {})
                            raise Fault(401, tr('Invalid key or temporary sign-in lockout'))
                        store.audit(self.client_address[0], 'login_ok', None, {})
                        return self._write(200, {'ok': True}, extra_headers={'Set-Cookie': admin.cookie(token,secure=self._secure_cookie())})
                    self._require_admin()
                    if path == '/api/admin/logout':
                        admin.logout(self._admin_cookie())
                        return self._write(200, {'ok': True}, extra_headers={'Set-Cookie': admin.expired_cookie()})
                    if path == '/api/admin/branding':
                        return self._write(200,club_settings.configure(store,data))
                    if path == '/api/admin/catalog':
                        return self._write(200,club_settings.save_catalog(store,data))
                    if path == '/api/admin/time-penalties':
                        return self._write(200,admin_penalties.add(store,data,self.client_address[0]))
                    if path == '/api/admin/time-penalties/revoke':
                        return self._write(200,admin_penalties.revoke(store,data,self.client_address[0]))
                    if path == '/api/admin/discord':
                        out=discord_notifications.configure(store,data)
                        store.audit(self.client_address[0],'discord_config',None,{'enabled':out['enabled']})
                        return self._write(200,out)
                    if path == '/api/admin/discord/test':
                        self._limit(path,3)
                        return self._write(200,discord_notifications.test_connection(store))
                    if path == '/api/admin/seasons':
                        out=save_season(store,data)
                        store.audit(self.client_address[0],'season_create',out['id'],{'config':data})
                        return self._write(200,out)
                    if path.startswith('/api/admin/seasons/'):
                        bits=path.removeprefix('/api/admin/seasons/').split('/')
                        if len(bits)!=2:raise Fault(404,tr('Season operation not found'))
                        season_id=bits[0]
                        operation=bits[1] if len(bits)>1 else ''
                        if operation=='delete':
                            return self._write(200,attempt_updates.purge_season(store,season_id,data.get('confirmId'),data.get('deleteRallies') is True))
                        if operation=='config':
                            out=save_season(store,data,season_id)
                        elif operation=='rallies':
                            out=set_rallies(store,season_id,data.get('eventIds'))
                        elif operation=='rally-points':
                            out=set_rally_points(store,season_id,data.get('eventId'),
                                                data.get('generalPoints'),data.get('divisionPoints'),
                                                data.get('powerStagePoints'))
                        elif operation=='assign':
                            out=assign_member(store,season_id,data.get('memberId'),
                                              data.get('divisionId'),data.get('teamId'))
                        elif operation=='groups':
                            action=data.get('action');kind=data.get('kind')
                            if action=='add':out=add_group(store,season_id,kind,data.get('name'),data.get('capacity',10))
                            elif action=='rename':out=rename_group(store,season_id,kind,data.get('id'),data.get('name'))
                            elif action=='capacity' and kind=='team':
                                out=set_team_capacity(store,season_id,data.get('id'),data.get('capacity'))
                            elif action=='delete':out=delete_group(store,season_id,kind,data.get('id'))
                            else:raise Fault(400,tr('Unknown group operation'))
                        else:raise Fault(404,tr('Season operation not found'))
                        store.audit(self.client_address[0],'season_'+operation,season_id,{'request':data})
                        return self._write(200,out)
                    if path == '/api/admin/events':
                        try:
                            validate_catalog_event(data, club_settings.catalog(store, catalog_root))
                            answer = store.create_admin_event(data)
                            store.audit(self.client_address[0], 'create', answer['id'],
                                        {'after': store.event(answer['id'])[1]})
                        except ValueError as exc:
                            raise Fault(400, str(exc))
                        return self._write(200, answer)
                    if path.startswith('/api/admin/events/'):
                        rest = path.removeprefix('/api/admin/events/')
                        if rest.endswith('/delete'):
                            ident = rest.removesuffix('/delete')
                            before = store.event(ident)[1]
                            if data.get('confirmId')!=ident: raise Fault(400,'Type the rally ID to confirm permanent deletion')
                            answer = store.delete_event(ident,data['confirmId'])
                            return self._write(200, answer)
                        try:
                            validate_catalog_event(data, club_settings.catalog(store, catalog_root))
                            before = store.event(rest)[1]
                            answer = store.update_event(rest, data)
                            store.audit(self.client_address[0], 'update', rest,
                                        {'before': before, 'after': data})
                            return self._write(200, answer)
                        except ValueError as exc:
                            raise Fault(400, str(exc))
                    raise Fault(404, tr('Administrator operation not found'))
                if path == '/api/launcher/abort':
                    self._client_version()
                    return self._write(200, abort_prestart(store,self._token()))
                if path == '/api/launcher/redeem':
                    self._client_version()
                    self._limit(path,30)
                    out = redeem_ticket(store, data.get('ticket'))
                elif path == '/api/join':
                    self._limit(path,12)
                    if PUBLIC_URL:
                        raise Fault(403,tr('Register on the club website; nickname registration through the old API is disabled'))
                    out = store.join(data.get('eventId'), data.get('nickname'))
                elif path == '/api/start':
                    self._client_version()
                    with store.lock:
                        actor=store._auth(self._token());_,ev=store.event(actor['event_id'])
                        v=self.headers.get('X-ACR-Launcher-Version','')
                        if ev.get('launcherProtocol')=='0.2.4' and (not re.fullmatch(r'0\.[0-9]+\.[0-9]+',v) or tuple(map(int,v.split('.')))<(0,2,9)):
                            raise Fault(426,'Install the latest 0.2.9 launcher from /download for this rally')
                    out = store.start(self._token(), data.get('eventId'), data.get('stageIndex'), data.get('carId'), data.get('settings'))
                elif path == '/api/heartbeat':
                    self._client_version()
                    out = store.heartbeat(self._token(), data.get('eventId'), data.get('stageIndex'), data.get('settings'), data.get('penaltyMs'))
                elif path == '/api/telemetry-penalty':
                    self._client_version()
                    out = attempt_updates.late_penalty(store,self._token(),data)
                elif path == '/api/live-telemetry':
                    self._client_version()
                    self._limit(path,600)
                    out=telemetry_audit.submit(store,self._token(),data)
                elif path == '/api/integrity-violation':
                    out = store.integrity_violation(self._token(),data.get('reason', tr('Settings mismatch')))
                elif path == '/api/dnf':
                    out = store.dnf(self._token(), data.get('reason', 'Wycofanie'))
                elif path == '/api/stage-end':
                    self._client_version()
                    out = store.stage_end(self._token(),data.get('eventId'),data.get('stageIndex'),data.get('clockMs'),data.get('settings'),data.get('penaltyMs'))
                elif path == '/api/stage-result':
                    self._client_version()
                    out = attempt_updates.stage_result(store,self._token(),data)
                elif path == '/api/checkpoint':
                    self._client_version()
                    self._limit(path,12)
                    out = attempt_updates.checkpoint(store,self._token(),data)
                elif path == '/api/recovery-checkpoint':
                    self._client_version()
                    self._limit(path,12)
                    out=attempt_updates.checkpoint(store,self._token(),data,recovery=True)
                elif path == '/api/recovery-ack':
                    self._client_version()
                    out=attempt_updates.recovery_ack(store,self._token(),data)
                elif path == '/api/finalize':
                    self._client_version()
                    out = store.finalize(self._token(),data)
                else:
                    raise Fault(404, tr('Not found'))
                self._write(200, out)
            except Fault as exc:
                self._write(exc.code, {'error': str(exc)})
            except Exception as exc:
                print('Error', type(exc).__name__, str(exc), flush=True)
                self._write(500, {'error': tr('Server error')})

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1', help='127.0.0.1 = only this PC; 0.0.0.0 = LAN (trusted network only)')
    parser.add_argument('--port', type=int, default=8790)
    parser.add_argument('--db', default=str(DB_DEFAULT))
    parser.add_argument('--import-event', metavar='FILE')
    args = parser.parse_args()
    check_config()
    store = Store(args.db)
    if args.import_event:
        event = json.loads(Path(args.import_event).read_text(encoding='utf-8-sig'))
        store.import_event(event)
        print('Imported:', event['id'])
        return
    auth = AdminAuth()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, auth))
    print(f'ACR Rally Club: http://127.0.0.1:{args.port}/', flush=True)
    base_url = os.environ.get('ACR_PUBLIC_BASE_URL') or f'http://127.0.0.1:{args.port}'
    print(f'PRYWATNY PANEL ADMIN: {base_url}{get_admin_path(auth.key_path)}', flush=True)
    if os.environ.get('ACR_ADMIN_KEY'):
        print('ADMIN KEY: set in ACR_ADMIN_KEY (value hidden)', flush=True)
    else:
        print(f'KLUCZ ADMIN w pliku: {auth.key_path}', flush=True)
    print(f'Listening on {args.host}:{args.port}; Ctrl+C to stop', flush=True)
    notifier = discord_notifications.Worker(store) if os.environ.get('ACR_DISCORD_NOTIFIER', '1') != '0' else None
    if notifier:
        notifier.start()
    cleanup_stop=threading.Event()
    def expire_save_copies():
        while not cleanup_stop.wait(30):
            try:
                with store.lock:store._sweep()
            except Exception as exc:
                print('Save cleanup retry:',type(exc).__name__,flush=True)
    threading.Thread(target=expire_save_copies,daemon=True).start()
    try:
        server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        print('\nBye')
    finally:
        cleanup_stop.set()
        server.server_close()
        if notifier:
            notifier.stop()
        store.db.close()

if __name__ == '__main__':
    main()
