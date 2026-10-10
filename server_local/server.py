"""Local ACR Rally Club scoreboard and first-attempt gate. Python 3.13, stdlib only.

Run from merged acr-daily root: py -3.13 server_local/server.py --import-event examples/...json
then: py -3.13 server_local/server.py
"""
from __future__ import annotations
import argparse
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
from seasons import (install as install_seasons, club_register, club_recover,
                     club_join, club_player, member_by_cookie, cookie as club_cookie,
                     mint_club_ticket, ensure_division_assigned, members as club_members,
                     list_seasons, season_config, save_season, set_rallies, set_rally_points,
                     add_group, rename_group, delete_group, set_team_capacity, assign_member, scoring,
                     club_page)
from season_panel import html as season_admin_html
from public_security import (PUBLIC_URL, DOWNLOAD_URL, check_config, gateway_ok,
                             check_host, browser_origin, remote_addr, RateLimiter, version_allowed)

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
        raise Fault(400, 'Nick: od 2 do 24 znaków')
    nick = nick.strip()
    if not re.fullmatch(r'[\w\- ]+', nick, re.UNICODE):
        raise Fault(400, 'Nick może zawierać litery, cyfry, spacje, _ i -')
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
        self.db.executescript('''
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
        ''')
        install_tables(self)
        install_seasons(self)
        self.db.execute('''CREATE TABLE IF NOT EXISTS admin_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, peer TEXT NOT NULL,
          action TEXT NOT NULL, event_id TEXT, details TEXT NOT NULL)''')

    def _begin(self):
        self.db.execute('BEGIN IMMEDIATE')

    def event(self, ident):
        row = self.db.execute('SELECT * FROM events WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Fault(404, 'Nie znaleziono rajdu')
        return dict(row), json.loads(row['config'])

    def import_event(self, config):
        validate_event(config)
        with self.lock:
            existing = self.db.execute('SELECT id FROM events WHERE id=?', (config['id'],)).fetchone()
            if existing:
                raise Fault(409, 'Rajd już istnieje (nie nadpisujemy po rozpoczęciu prób)')
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
                    raise Fault(503, 'Nie można wygenerować unikalnego ID rajdu')
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
            raise Fault(400, 'Nie można zmienić ID rajdu')
        with self.lock:
            self._begin()
            try:
                self.event(ident)
                used = self.db.execute('SELECT COUNT(*) FROM players WHERE event_id=?', (ident,)).fetchone()[0]
                if used:
                    raise Fault(409, 'Rajd ma już uczestników; zmiana konfiguracji jest zablokowana')
                self.db.execute('UPDATE events SET config=?,opens=?,closes=? WHERE id=?',
                                (json.dumps(config, ensure_ascii=False),
                                 utc_epoch(config['opensAt']), utc_epoch(config['closesAt']), ident))
                self.db.execute('COMMIT')
                return {'ok': True, 'id': ident}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def delete_event(self, ident):
        with self.lock:
            self._begin()
            try:
                self.event(ident)
                used = self.db.execute('SELECT COUNT(*) FROM players WHERE event_id=?', (ident,)).fetchone()[0]
                if used:
                    raise Fault(409, 'Nie można usunąć rajdu z uczestnikami')
                self.db.execute('DELETE FROM events WHERE id=?', (ident,))
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
            return [json.loads(r[0]) for r in self.db.execute('SELECT config FROM events ORDER BY opens DESC')]

    def _sweep(self):
        now = time.time()
        self.db.execute("""UPDATE players SET status='dnf',terminal_reason='Brak pełnego oficjalnego zapisu po mecie', started=NULL
            WHERE status='awaiting_results' AND last_seen < ?""", (now - 600,))
        self.db.execute('''UPDATE players SET status='dnf',
             terminal_reason='Po rozpoczęciu OS utracono kontakt z klientem',
             started=NULL WHERE status='active' AND last_seen < ?''', (now - self.inactive,))

    def _auth(self, token):
        if not isinstance(token, str) or len(token) < 40:
            raise Fault(401, 'Brak tokenu uczestnika')
        row = self.db.execute('SELECT * FROM players WHERE token_hash=?',
                              (sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:
            raise Fault(401, 'Nieprawidłowy token')
        return row

    def join(self, event_id, nick):
        nick, key = nick_key(nick)
        with self.lock:
            self._begin()
            try:
                row, event = self.event(event_id)
                if self.db.execute('SELECT 1 FROM season_events WHERE event_id=?',(event_id,)).fetchone():
                    raise Fault(403, 'Rajd sezonowy wymaga konta klubowego. Zarejestruj nick na /club')
                now = time.time()
                # Club registration is permitted in advance; RUN remains time-gated.
                if now >= row['closes']:
                    raise Fault(409, 'Zapisy zamknięte: rajd już się zakończył')
                used = self.db.execute('SELECT 1 FROM players WHERE event_id=? AND nickname_key=?',
                                       (event_id, key)).fetchone()
                if used:
                    raise Fault(409, 'Nick już zarejestrowany; na tym komputerze użyj istniejącego tokenu')
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
            return d

    def _integrity_or_dnf(self, player, event, settings):
        """Server-side fail-closed protocol validation (client is NOT a trusted attestor)."""
        problems = compare_settings(event, settings)
        if problems:
            reason = 'Zmienione ustawienia Rally Weekend: ' + '; '.join(problems[:3])
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
                    raise Fault(409, 'Rajd jest już zakończony')
                msg = ('Niezgodność ustawień Rally Weekend: ' + str(reason))[:300]
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
                    raise Fault(403, 'Inny rajd niż zarejestrowany')
                if p['club_member_id'] is not None:
                    ensure_division_assigned(self,event_id,p['club_member_id'])
                now = time.time()
                if not row['opens'] <= now <= row['closes']:
                    raise Fault(409, 'Rajd nie jest teraz aktywny')
                if p['status'] not in ('registered', 'ready') or p['stage_index'] != stage_index:
                    raise Fault(409, 'Próba już wykorzystana lub etap zablokowany')
                if stage_index < 0 or stage_index >= len(config['stages']):
                    raise Fault(400, 'Nieprawidłowy numer OS')
                if car_id not in config['allowedCars']:
                    raise Fault(409, 'Auto spoza klasy rajdu')
                if p['car_id'] is not None and p['car_id'] != car_id:
                    raise Fault(409, 'Zmiana samochodu w trakcie rajdu zabroniona')
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

    def heartbeat(self, token, event_id, stage_index, settings=None):
        with self.lock:
            self._sweep()
            p = self._auth(token)
            if p['event_id'] != event_id or p['stage_index'] != stage_index or p['status'] != 'active':
                raise Fault(409, 'Brak aktywnej próby')
            _row, config = self.event(event_id)
            reason = self._integrity_or_dnf(p, config, settings)
            if reason:
                raise Fault(409, reason)
            self.db.execute('UPDATE players SET last_seen=? WHERE id=?', (time.time(), p['id']))
            return {'ok': True}

    def dnf(self, token, reason):
        with self.lock:
            self._begin()
            try:
                self._sweep()
                p = self._auth(token)
                if p['status'] != 'active':
                    raise Fault(409, 'Brak aktywnej próby')
                self.db.execute("UPDATE players SET status='dnf',terminal_reason=?,started=NULL WHERE id=?",
                                (str(reason)[:300], p['id']))
                self.db.execute('COMMIT')
                return {'ok': True, 'status': 'dnf'}
            except Exception:
                if self.db.in_transaction: self.db.execute('ROLLBACK')
                raise

    def stage_end(self, token, event_id, index, clock_ms, settings=None):
        'Mark a telemetry finish. Official game results are submitted only after all stages.'
        with self.lock:
            self._begin()
            try:
                self._sweep()
                p = self._auth(token)
                row, config = self.event(event_id)
                if p['event_id'] != event_id or p['status'] != 'active' or p['stage_index'] != index:
                    raise Fault(409, 'Etap nie jest aktywny / próba już wykorzystana')
                reason = self._integrity_or_dnf(p, config, settings)
                if reason:
                    self.db.execute('COMMIT')
                    raise Fault(409, reason)
                if type(clock_ms) is not int or not 10000 <= clock_ms <= 4*60*60*1000:
                    raise Fault(400, 'Nieprawidłowy timer OS-u')
                now = time.time()
                self.db.execute('''INSERT INTO provisional(player_id,stage_index,clock_ms,finished)
                  VALUES(?,?,?,?)''', (p['id'], index, clock_ms, now))
                next_index = index + 1
                finished_all = next_index == len(config['stages'])
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
                    raise Fault(409, 'Rajd nie jest gotowy do zatwierdzenia')
                reason = self._integrity_or_dnf(p, event, provided.get('settings'))
                if reason:
                    self.db.execute('COMMIT')
                    raise Fault(409, reason)
                if not isinstance(stages, list) or len(stages) != len(event['stages']):
                    raise Fault(400, 'Brak oficjalnego wyniku któregoś OS-u')
                prov = self.db.execute('SELECT * FROM provisional WHERE player_id=? ORDER BY stage_index',
                                       (p['id'],)).fetchall()
                if len(prov) != len(stages):
                    raise Fault(409, 'Nie wszystkie OS-y miały legalną próbę')
                prev_started = 0
                now = time.time()
                for idx, (record, stage, started) in enumerate(zip(stages, event['stages'], prov)):
                    if not isinstance(record, dict) or record.get('stageIndex') != idx or \
                            record.get('stageId') != stage['stageId'] or record.get('carId') != p['car_id']:
                        raise Fault(409, 'Zły OS lub samochód w oficjalnym wyniku')
                    raw, pen, total = (record.get(k) for k in ('rawMs','penaltyMs','totalMs'))
                    if any(type(x) is not int for x in (raw,pen,total)) or not 10000 <= raw <= 14400000 or \
                            not 0 <= pen <= 3600000 or raw + pen != total:
                        raise Fault(400, 'Nieprawidłowy czas lub kara')
                    acr_started = record.get('acrStarted')
                    if not isinstance(acr_started, (float,int)) or \
                            not p['created'] - 60 <= acr_started <= now + 60 or \
                            acr_started <= prev_started:
                        raise Fault(409, 'Nieprawidłowy czas rozpoczęcia próby w pliku ACR')
                    # Coarse sanity bound between telemetry and official timers; exceptions
                    # can occur with timing glitches and need manual review rather than fake score.
                    if abs(raw - started['clock_ms']) > 5000:
                        raise Fault(409, 'Oficjalny timer różni się o >5s od zapisu telemetrii')
                    self.db.execute('''INSERT INTO results(player_id,stage_index,stage_id,car_id,
                      raw_ms,penalty_ms,total_ms,acr_started,finished)
                      VALUES(?,?,?,?,?,?,?,?,?)''',
                      (p['id'], idx, stage['stageId'], p['car_id'], raw, pen, total, acr_started, now))
                    prev_started = acr_started
                self.db.execute("UPDATE players SET status='completed',last_seen=? WHERE id=?", (now,p['id']))
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
            return {'event': event, 'players': [dict(p) for p in sorted(players,
                    key=lambda p:(p['status'] != 'completed', -p['completed_stages'], p['total'], p['nickname'].lower()))],
                    'stageResults':stage_results}


STYLE = '''
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
'''


def site(store, identifier=None, browser=None, csrf=None, member=None):
    """Modern public pages. All data, CSRF forms and route targets retain V5 behavior."""
    from site_theme import shell

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
        content=('<section class="hero"><span class="eyebrow">Assetto Corsa Rally · Oficjalna rywalizacja</span>'
                 '<h1>Rajdy i wydarzenia</h1><p>Wybierz rajd, poznaj regulamin i wystartuj jednym kliknięciem. '
                 'Odcinki, klasyfikacje i wyniki klubowe w jednym miejscu.</p>'
                 '<p><a class="btn-link" href="/download">⬇ POBIERZ LAUNCHER WINDOWS (.EXE)</a>　<a class="btn-link" href="/guide">Poradnik startu →</a></p>'
                 '<div class="stats"><div class="stat"><strong>'+str(len(evs))+'</strong><span>Rajdów</span></div>'
                 '<div class="stat"><strong>'+str(active)+'</strong><span>Trwające</span></div>'
                 '<div class="stat"><strong>'+str(upcoming)+'</strong><span>Zaplanowane</span></div></div></section>')
        if member:
            content+=('<section class="card"><span class="section-kicker">Twój profil</span>Witaj, <strong>'+escape(member['nickname'])+
                      '</strong>. <a href="/club">Zobacz konto klubowe →</a></section>')
        content+=('<div class="card-head"><div><span class="section-kicker">Kalendarz</span><h2>Dostępne rajdy</h2></div>'
                  '<a class="btn-link" href="/seasons">Wyniki sezonów →</a></div>')
        content+='<div class="grid-cards">'
        for ev in evs:
            eid=escape(ev['id'],quote=True)
            opening,closing=utc_epoch(ev['opensAt']),utc_epoch(ev['closesAt'])
            label,cl=('TRWA','chip-active') if opening<=now<=closing else (('JUŻ WKRÓTCE','chip-upcoming') if now<opening else ('ZAKOŃCZONY','chip-ended'))
            content+=('<article class="rally-card"><div class="hero-inline">'+pill(label,cl)+
                      '<span class="muted">'+escape(ev['location'])+'</span></div>'
                      '<h2><a href="/rally/'+eid+'">'+escape(ev['name'])+'</a></h2>'
                      '<p>'+str(len(ev['stages']))+' odcinki specjalne · '+escape(ev['carClass'])+'</p>'
                      '<div class="rally-foot"><small>'+escape(date_label(ev['opensAt']))+'</small>'
                      '<a class="btn-link" href="/rally/'+eid+'">Zobacz rajd →</a></div></article>')
        content+='</div>'
        if not evs:content+='<div class="empty">Brak rajdów. Organizator doda je w panelu administratora.</div>'
        return shell('ACR Rally Club — Rajdy',content,active='rallies')

    data=store.board(identifier)
    ev=data['event'];eid=escape(ev['id'],quote=True)
    total_stages=len(ev['stages'])
    finished=sum(p['status']=='completed' for p in data['players'])
    content=('<div><a class="backlink" href="/">← Wszystkie rajdy</a></div>'
             '<section class="hero"><span class="eyebrow">Rally Weekend / '+escape(ev['location'])+'</span>'
             '<h1>'+escape(ev['name'])+'</h1><p>'+escape(ev['carClass'])+' · '+str(total_stages)+' odcinków specjalnych</p>'
             '<div class="stats"><div class="stat"><strong>'+str(total_stages)+'</strong><span>OS-ów</span></div>'
             '<div class="stat"><strong>'+str(len(data['players']))+'</strong><span>Uczestników</span></div>'
             '<div class="stat"><strong>'+str(finished)+'</strong><span>Na mecie</span></div></div></section>'
             '<div class="split"><section class="card"><span class="section-kicker">Informacje o rundzie</span>'
             '<h2>Harmonogram</h2><p class="rally-meta"><strong>Start:</strong> '+escape(date_label(ev['opensAt']))+'</p>'
             '<p class="rally-meta"><strong>Koniec:</strong> '+escape(date_label(ev['closesAt']))+'</p>'
             '<p class="rally-meta"><strong>Lokalizacja:</strong> '+escape(ev['location'])+'</p>'
             '<p class="rally-meta"><strong>Klasa aut:</strong> '+escape(ev['carClass'])+'</p></section>')
    content+='<section class="card"><span class="section-kicker">Strefa kierowcy</span><h2>Twój udział</h2>'
    if csrf:
        csrf_field='<input type="hidden" name="csrf" value="'+escape(csrf,quote=True)+'">'
        if browser is None and member is not None:
            content+='<p>Startujesz pod nickiem <strong>'+escape(member['nickname'])+'</strong>.</p>'
            content+=('<form action="/web/enroll" method="post">'+csrf_field+
                      '<input type="hidden" name="eventId" value="'+eid+'">'
                      '<button class="run" type="submit">ZAPISZ SIĘ</button></form>')
        elif browser is None:
            seasonal=store.db.execute('SELECT 1 FROM season_events WHERE event_id=?',(ev['id'],)).fetchone()
            content+='<p>Masz konto? <a href="/club">Dołącz do klubu</a>, aby zachować nick na wszystkie rajdy.</p>'
            if not seasonal and not PUBLIC_URL:
                content+=('<form action="/web/enroll" method="post">'+csrf_field+
                    '<input type="hidden" name="eventId" value="'+eid+'">'
                    '<label for="nickname">Nick kierowcy</label><div class="toolbar">'
                    '<input id="nickname" name="nickname" required minlength="2" maxlength="24" autocomplete="nickname" placeholder="Twój nick">'
                    '<button class="run" type="submit">ZAPISZ SIĘ</button></div></form>')
        else:
            status=browser['status']
            labels={'registered':'ZAPISANY','ready':'MIĘDZY OS','active':'NA ODCINKU','completed':'META','dnf':'DNF','awaiting_results':'WERYFIKACJA'}
            content+='<p><strong>'+escape(browser['nickname'])+'</strong> · '+pill(labels.get(status,status),'status-done' if status=='completed' else 'status-dnf' if status=='dnf' else '')+'</p>'
            waiting_division=False
            if member is not None:
                try:ensure_division_assigned(store,ev['id'],member['id'])
                except Fault:waiting_division=True
            rally_open=utc_epoch(ev['opensAt']) <= time.time() < utc_epoch(ev['closesAt'])
            if status in ('registered','ready') and not waiting_division and rally_open:
                content+=('<form action="/web/run" method="post">'+csrf_field+
                    '<input type="hidden" name="eventId" value="'+eid+'">'
                    '<button class="run" type="submit">▶ RUN RALLY</button></form>'
                    '<p><small>Nie masz launchera? <a href="/launcher">Instrukcja instalacji</a>.</small></p>')
            elif waiting_division:
                content+='<p class="muted">Oczekujesz na przydział do dywizji przez organizatora.</p>'
            elif status in ('registered','ready') and time.time() < utc_epoch(ev['opensAt']):
                content+='<p class="muted">Zapis potwierdzony. RUN RALLY będzie dostępny od '+escape(date_label(ev['opensAt']))+'.</p>'
            else:
                content+='<p class="muted">RUN zablokowany — próba już trwa lub została zakończona.</p>'
    content+='</section></div>'
    content+='<section class="card"><div class="card-head"><div><span class="section-kicker">Klasyfikacja rajdu</span><h2>Wyniki generalne</h2></div>'+pill(str(len(data['players']))+' kierowców')+'</div>'
    content+=('<div class="toolbar"><label for="driver-search">Szukaj kierowcy</label>'
              '<input type="search" id="driver-search" placeholder="Wpisz nick kierowcy…" autocomplete="off"></div>')
    content+=('<div class="table-scroll"><table><thead><tr><th>Miejsce</th><th>Kierowca</th>'
              '<th>Samochód</th><th>OS</th><th>Łączny czas</th><th>Status</th></tr></thead><tbody>')
    for i,p in enumerate(data['players'],1):
        label={'completed':'META','dnf':'DNF','ready':'MIĘDZY OS','active':'NA ODCINKU','registered':'ZAPISANY','awaiting_results':'WERYFIKACJA'}.get(p['status'],p['status'])
        status_css='status-done' if p['status']=='completed' else 'status-dnf' if p['status']=='dnf' else ''
        status_text=label+((' · '+str(p['terminal_reason'])[:100]) if p['status']=='dnf' and p.get('terminal_reason') else '')
        result=format_ms(p['total']) if p['completed_stages'] else '—'
        content+=('<tr data-driver="'+escape(p['nickname'],quote=True)+'"><td class="rank-col">'+str(i)+'</td><td><strong>'+escape(p['nickname'])+'</strong></td>'
                  '<td>'+escape(p['car_id'] or '—')+'</td><td>'+str(p['completed_stages'])+'/'+str(total_stages)+'</td>'
                  '<td class="mono"><strong>'+escape(result)+'</strong></td><td>'+pill(status_text,status_css)+'</td></tr>')
    content+='</tbody></table></div>'
    if not data['players']:content+='<div class="empty">Nie ma jeszcze zgłoszonych kierowców.</div>'
    content+='<p class="table-meta">Do klasyfikacji końcowej liczą się tylko kierowcy ze statusem META. DNF blokuje ponowną próbę.</p></section>'
    content+='<section class="card"><span class="section-kicker">Szczegółowe wyniki</span><h2>Wyniki poszczególnych OS-ów</h2>'
    for index,stage in enumerate(ev['stages']):
        stage_rows=[r for r in data['stageResults'] if r['stage_index']==index]
        content+='<details class="round"'+(' open' if index==0 else '')+'><summary><span>OS '+str(index+1)+' · '+escape(stage['stageId'])+'</span>'+pill(str(len(stage_rows))+' wyników')+'</summary>'
        content+='<div class="table-scroll"><table><thead><tr><th>#</th><th>Kierowca</th><th>RAW</th><th>Kary</th><th>Oficjalny czas</th></tr></thead><tbody>'
        for place,r in enumerate(stage_rows,1):
            content+=('<tr><td class="rank-col">'+str(place)+'</td><td>'+escape(r['nickname'])+'</td>'
                    '<td class="mono">'+format_ms(r['raw_ms'])+'</td>'
                    '<td class="mono bad">+'+format_ms(r['penalty_ms'])+'</td>'
                    '<td class="mono"><strong>'+format_ms(r['total_ms'])+'</strong></td></tr>')
        content+='</tbody></table></div>'
        if not stage_rows:content+='<div class="empty">Wyniki pojawią się po weryfikacji całego rajdu.</div>'
        content+='</details>'
    content+='</section>'
    from site_theme import RALLY_FILTER_JS
    return shell('ACR Rally Club — '+ev['name'],content,active='rallies',scripts=RALLY_FILTER_JS)


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
            payload = value.encode('utf-8') if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
            if PUBLIC_URL:
                self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
            if extra_headers:
                for header, val in extra_headers.items():
                    self.send_header(header, val)
            self.end_headers()
            self.wfile.write(payload)

        def _gateway_guard(self):
            if not gateway_ok(self.headers) or not check_host(self.headers):
                raise Fault(403, 'Nieprawidłowa brama HTTPS lub adres serwera')

        def _remote_ip(self):
            return remote_addr(self.headers,self.client_address[0])

        def _client_version(self):
            if not version_allowed(self.headers.get('X-ACR-Launcher-Version')):
                raise Fault(426, 'Za stary launcher: wymagana wersja V6.3.1 lub nowsza. Zainstaluj najnowszy EXE ze strony /download. Sama aktualizacja ZIP serwera nie wymienia zainstalowanego launchera.')

        def _limit(self, name, count):
            if not limiter.allow(self._remote_ip(),name,count):
                raise Fault(429, 'Zbyt wiele żądań. Spróbuj później.')

        def _secure_cookie(self):
            return bool(PUBLIC_URL) or self.headers.get('X-Forwarded-Proto')=='https'

        def _cookies(self):
            try:
                cookie = SimpleCookie()
                cookie.load(self.headers.get('Cookie', ''))
                return {k: v.value for k,v in cookie.items()}
            except Exception:
                return {}

        def _form(self):
            ctype = self.headers.get('Content-Type','').split(';',1)[0].lower()
            if ctype != 'application/x-www-form-urlencoded':
                raise Fault(415, 'Wymagany formularz HTML')
            try:
                length = int(self.headers.get('Content-Length','0'))
            except ValueError:
                raise Fault(400, 'Błędny Content-Length')
            if not 0 < length <= 4096:
                raise Fault(413, 'Nieprawidłowa długość formularza')
            try:
                data = parse_qs(self.rfile.read(length).decode('utf-8'), strict_parsing=True)
                return {k:v[0] for k,v in data.items()}
            except (ValueError, UnicodeError):
                raise Fault(400, 'Nieprawidłowe dane formularza')

        def _require_web_form(self, data):
            cookies = self._cookies()
            if not csrf_ok(cookies.get('acrclub_csrf'), data.get('csrf')):
                raise Fault(403, 'Brak lub zły token formularza (CSRF)')
            origin = self.headers.get('Origin')
            fetch_site = self.headers.get('Sec-Fetch-Site')
            # Sec-Fetch-Site can identify genuine cross-site requests even when
            # Origin is omitted or set to the opaque literal "null".
            if fetch_site == 'cross-site':
                print('Rejected cross-site web form:', repr(origin), flush=True)
                raise Fault(403, 'Niedozwolone pochodzenie żądania')
            if PUBLIC_URL and not browser_origin(origin, self.headers):
                raise Fault(403, 'Formularz z innej domeny jest niedozwolony')
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
                    raise Fault(403, 'Niedozwolone pochodzenie żądania')
            return cookies

        def _redirect(self, location, *, cookie=None):
            headers={'Location':location}
            if cookie: headers['Set-Cookie']=cookie
            return self._write(303, '', 'text/plain; charset=utf-8', headers)

        def _body(self):
            try:
                length = int(self.headers.get('Content-Length','0'))
            except ValueError:
                raise Fault(400, 'Błędny Content-Length')
            if not 0 < length <= MAX_BODY:
                raise Fault(413, 'Za duże dane')
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise Fault(400, 'Nieprawidłowy JSON')
            if not isinstance(body, dict):
                raise Fault(400, 'Wymagany obiekt JSON')
            return body

        def _token(self):
            auth = self.headers.get('Authorization','')
            if not auth.startswith('Bearer '):
                raise Fault(401, 'Brak tokenu')
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
                    raise Fault(403, 'Panel administracyjny dostępny tylko lokalnie na komputerze serwera')
            except ValueError:
                raise Fault(403, 'Nieprawidłowy adres połączenia')

        def _require_admin(self):
            self._require_admin_local()
            if not admin.valid(self._admin_cookie()):
                raise Fault(401, 'Brak sesji administratora')

        def _require_admin_post(self):
            # Cross-site HTML forms cannot send this header; foreign fetch()
            # with the header triggers a denied CORS preflight.
            if self.headers.get('X-ACR-Admin') != '1':
                raise Fault(403, 'Nieprawidłowe żądanie panelu')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise Fault(403, 'Niedozwolone pochodzenie żądania')
            origin = self.headers.get('Origin')
            if origin and not (browser_origin(origin, self.headers) if PUBLIC_URL else allowed_browser_origin(
                    origin, self.headers.get('Host', ''), self.server.server_port)):
                print('Rejected admin Origin:', repr(origin[:180]),
                      'Host:', repr(self.headers.get('Host', '')[:180]), flush=True)
                raise Fault(403, 'Niedozwolone pochodzenie żądania')
            content_type = self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if content_type != 'application/json':
                raise Fault(415, 'Wymagany application/json')

        def do_GET(self):
            try:
                self._gateway_guard()
                path = unquote(urlparse(self.path).path)
                if path == secret_admin_path + '/seasons':
                    self._require_admin_local()
                    return self._write(200, private_admin_page(season_admin_html(), secret_admin_path), 'text/html; charset=utf-8',
                        {'Content-Security-Policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'"})
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
                        raise Fault(503,'Instalator zostanie udostępniony po publikacji pierwszego wydania GitHub Releases')
                    return self._write(302,'','text/plain; charset=utf-8',{'Location':DOWNLOAD_URL})
                if path == '/guide':
                    from driver_guide import page
                    return self._write(200,page(),'text/html; charset=utf-8')
                if path == '/club':
                    csrf=secrets.token_urlsafe(24)
                    member=member_by_cookie(store,self._cookies().get('acrclub_member'))
                    from site_theme import shell
                    content=shell('ACR Rally Club — Konto klubowe',
                                  '<section class="hero"><span class="eyebrow">Klubowicze</span><h1>Konto klubowe</h1>'
                                  '<p>Twój nick na cały sezon, rajdy i dywizje.</p></section>'+
                                  club_page(member,csrf),active='club')
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
                if path == '/api/admin/catalog':
                    self._require_admin()
                    try:
                        return self._write(200, load_catalog(catalog_root))
                    except ValueError as exc:
                        raise Fault(500, str(exc))
                if path == '/api/admin/events':
                    self._require_admin()
                    return self._write(200, {'events': store.admin_listing()})
                if path == '/launcher':
                    from site_theme import shell
                    info = ('<section class="hero"><span class="eyebrow">Start rajdu / Windows</span>'
                            '<h1>ACR Club Launcher</h1><p>Zainstaluj raz. Potem uruchamiaj rajdy jednym kliknięciem RUN RALLY.</p>'
                            '<p><a class="btn-link" href="/download">⬇ Pobierz instalator Windows .EXE</a></p></section>'
                            '<section class="card"><h2>Jak wystartować?</h2>'
                            '<p>Nie potrzebujesz Pythona ani plików .bat. Pobierz .EXE, uruchom go i zaakceptuj protokół acrclub://.</p>'
                            '<p>Na stronie klubu załóż konto, wybierz rajd i kliknij RUN RALLY. Launcher przygotuje zapis i uruchomi ACR przez Steam.</p>'
                            '<p>Automatyczna nawigacja zatrzyma się przy START STAGE. Szczegóły: <a href="/guide">poradnik kierowcy →</a></p></section>')
                    return self._write(200, shell('ACR Rally Club — Launcher',info,active='launcher'),
                                       'text/html; charset=utf-8')
                if path in ('/','/index.html'):
                    return self._write(200, site(store), 'text/html; charset=utf-8')
                if path.startswith('/rally/') and len(path.split('/')) == 3:
                    event_id = path.split('/')[2]
                    cookies=self._cookies()
                    member=member_by_cookie(store,cookies.get('acrclub_member'))
                    if member is not None:
                        # A persistent club account is authoritative. Never let a
                        # stale per-event browser cookie show another rider's identity.
                        actor=club_player(store,event_id,member['id'])
                    else:
                        actor=browser_player(store,cookies.get('acrclub_browser'),event_id)
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
                if path.startswith('/api/board/'):
                    return self._write(200, store.board(path.rsplit('/',1)[-1]))
                raise Fault(404, 'Nie znaleziono')
            except Fault as exc:
                self._write(exc.code, {'error': str(exc)})
            except Exception:
                self._write(500, {'error': 'Błąd serwera'})

        def do_POST(self):
            try:
                self._gateway_guard()
                path = unquote(urlparse(self.path).path)
                if path in ('/web/club/register','/web/club/recover'):
                    self._limit(path,6)
                    data=self._form()
                    self._require_web_form(data)
                    if path.endswith('/register'):
                        account=club_register(store,data.get('nickname',''))
                        page=('<html lang="pl"><meta charset="utf-8"><title>Konto klubowe</title>'
                              '<style>'+STYLE+'</style><main><h1>Zapisano do klubu!</h1><section class="card">'
                              '<p>Nick: <strong>'+escape(account['nickname'])+'</strong></p>'
                              '<p>Zapisz ten kod odzyskiwania w bezpiecznym miejscu — nie będzie ponownie wyświetlony:</p>'
                              '<p><code>'+escape(account['recovery'])+'</code></p>'
                              '<p><a href="/">Otwórz listę rajdów →</a></p></section></main></html>')
                        return self._write(200,page,'text/html; charset=utf-8',
                                           {'Set-Cookie':club_cookie(account['token'],secure=self._secure_cookie())})
                    account=club_recover(store,data.get('nickname',''),data.get('recovery',''))
                    return self._redirect('/club',cookie=club_cookie(account['token'],secure=self._secure_cookie()))
                if path in ('/web/enroll','/web/run'):
                    self._limit(path,20)
                    data = self._form()
                    cookies = self._require_web_form(data)
                    event_id = data.get('eventId','')
                    # Validate an existing event and forbid path-based redirects.
                    store.event(event_id)
                    member=member_by_cookie(store,cookies.get('acrclub_member'))
                    if path == '/web/enroll':
                        if PUBLIC_URL and member is None:
                            raise Fault(403, 'W publicznej lidze wymagane jest konto klubowe (/club)')
                        if member is not None:
                            club_join(store,event_id,member['id'])
                            return self._redirect('/rally/'+quote(event_id,safe=''))
                        cookie = enroll(store, event_id, data.get('nickname',''))
                        return self._redirect('/rally/' + quote(event_id, safe=''),
                                              cookie=make_cookie('acrclub_browser',cookie,secure=self._secure_cookie()))
                    if member is not None:
                        ticket=mint_club_ticket(store,event_id,member['id'])
                    else:
                        ticket = mint_ticket(store, cookies.get('acrclub_browser'), event_id)
                    protocol = 'acrclub://start?ticket=' + quote(ticket,safe='')
                    # Navigation might require an extra click in some browsers.
                    # The launch ticket is single-use, short-lived and is not a bearer account token.
                    safe = escape(protocol, quote=True)
                    import json as _json
                    page = ('<!doctype html><html lang="pl"><head><meta charset="utf-8">'
                            '<title>Uruchamianie ACR Rally Club</title><style>' + STYLE + '</style></head><body><main>'
                            '<h1>Uruchamianie rajdu</h1><section class="card">'
                            '<p>Jeśli przeglądarka pyta, wybierz „Otwórz ACR Club Launcher”.</p>'
                            '<p><a class="run" style="display:inline-block" href="'+safe+'">▶ OTWÓRZ LAUNCHER</a></p>'
                            '<p><small>Bilet wygaśnie po 60 sekundach. Jeśli nic się nie dzieje, '
                            'sprawdź instalację launchera lub wróć na stronę rajdu.</small></p>'
                            '<p><a href="/rally/'+escape(event_id,quote=True)+'">← Rajd</a></p></section></main>'
                            '<script>window.location.href='+_json.dumps(protocol)+';</script></body></html>')
                    return self._write(200, page, 'text/html; charset=utf-8',
                                       {'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'"})
                data = self._body()
                if path.startswith('/api/admin/'):
                    self._require_admin_local()
                    self._require_admin_post()
                    if path == '/api/admin/login':
                        self._limit(path,6)
                        token = admin.login(data.get('key'), self._remote_ip())
                        if not token:
                            store.audit(self.client_address[0], 'login_failed', None, {})
                            raise Fault(401, 'Nieprawidłowy klucz lub czasowa blokada logowania')
                        store.audit(self.client_address[0], 'login_ok', None, {})
                        return self._write(200, {'ok': True}, extra_headers={'Set-Cookie': admin.cookie(token,secure=self._secure_cookie())})
                    self._require_admin()
                    if path == '/api/admin/logout':
                        admin.logout(self._admin_cookie())
                        return self._write(200, {'ok': True}, extra_headers={'Set-Cookie': admin.expired_cookie()})
                    if path == '/api/admin/seasons':
                        out=save_season(store,data)
                        store.audit(self.client_address[0],'season_create',out['id'],{'config':data})
                        return self._write(200,out)
                    if path.startswith('/api/admin/seasons/'):
                        bits=path.removeprefix('/api/admin/seasons/').split('/')
                        if len(bits)!=2:raise Fault(404,'Nie znaleziono operacji sezonu')
                        season_id=bits[0]
                        operation=bits[1] if len(bits)>1 else ''
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
                            else:raise Fault(400,'Nieznana operacja na grupie')
                        else:raise Fault(404,'Nie znaleziono operacji sezonu')
                        store.audit(self.client_address[0],'season_'+operation,season_id,{'request':data})
                        return self._write(200,out)
                    if path == '/api/admin/events':
                        try:
                            validate_catalog_event(data, load_catalog(catalog_root))
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
                            answer = store.delete_event(ident)
                            store.audit(self.client_address[0], 'delete', ident, {'before': before})
                            return self._write(200, answer)
                        try:
                            validate_catalog_event(data, load_catalog(catalog_root))
                            before = store.event(rest)[1]
                            answer = store.update_event(rest, data)
                            store.audit(self.client_address[0], 'update', rest,
                                        {'before': before, 'after': data})
                            return self._write(200, answer)
                        except ValueError as exc:
                            raise Fault(400, str(exc))
                    raise Fault(404, 'Nie znaleziono operacji administracyjnej')
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
                        raise Fault(403,'Zapisz się na stronie klubu; rejestracja nicku przez stare API jest wyłączona')
                    out = store.join(data.get('eventId'), data.get('nickname'))
                elif path == '/api/start':
                    self._client_version()
                    out = store.start(self._token(), data.get('eventId'), data.get('stageIndex'), data.get('carId'), data.get('settings'))
                elif path == '/api/heartbeat':
                    self._client_version()
                    out = store.heartbeat(self._token(), data.get('eventId'), data.get('stageIndex'), data.get('settings'))
                elif path == '/api/integrity-violation':
                    out = store.integrity_violation(self._token(),data.get('reason', 'Niezgodność ustawień'))
                elif path == '/api/dnf':
                    out = store.dnf(self._token(), data.get('reason', 'Wycofanie'))
                elif path == '/api/stage-end':
                    self._client_version()
                    out = store.stage_end(self._token(),data.get('eventId'),data.get('stageIndex'),data.get('clockMs'),data.get('settings'))
                elif path == '/api/finalize':
                    self._client_version()
                    out = store.finalize(self._token(),data)
                else:
                    raise Fault(404, 'Nie znaleziono')
                self._write(200, out)
            except Fault as exc:
                self._write(exc.code, {'error': str(exc)})
            except Exception as exc:
                print('Error', type(exc).__name__, str(exc), flush=True)
                self._write(500, {'error': 'Błąd serwera'})

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
        print('KLUCZ ADMIN: ustawiony w zmiennej ACR_ADMIN_KEY (wartość ukryta)', flush=True)
    else:
        print(f'KLUCZ ADMIN w pliku: {auth.key_path}', flush=True)
    print(f'Listening on {args.host}:{args.port}; Ctrl+C to stop', flush=True)
    try:
        server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        print('\nBye')
    finally:
        server.server_close()
        store.db.close()

if __name__ == '__main__':
    main()
