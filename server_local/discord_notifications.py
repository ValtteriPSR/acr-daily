"""Persistent Discord scoreboards. Only fixed Discord webhook endpoints are allowed."""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler


def fault(code, text):
    from server import Fault
    from i18n import tr
    raise Fault(code, tr(text))


def validate_webhook(value):
    if not isinstance(value, str):
        fault(400, 'Enter a Discord channel webhook URL, not a server invite')
    value = value.strip()
    try:
        u = urlsplit(value)
    except ValueError:
        fault(400, 'Enter a Discord channel webhook URL, not a server invite')
    if (u.scheme != 'https' or u.netloc != 'discord.com' or u.query or u.fragment or
            not re.fullmatch(r'/api(?:/v10)?/webhooks/[0-9]{5,25}/[A-Za-z0-9_-]{20,200}', u.path)):
        fault(400, 'Enter a Discord channel webhook URL, not a server invite')
    return value


def install(store):
    store.db.executescript('''
    CREATE TABLE IF NOT EXISTS discord_settings (
      id INTEGER PRIMARY KEY, config TEXT NOT NULL, last_error TEXT NOT NULL DEFAULT '',
      last_sent REAL, next_attempt REAL NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS discord_deliveries (
      delivery_key TEXT PRIMARY KEY, message_id TEXT NOT NULL, digest TEXT NOT NULL);
    ''')


def _settings(store):
    row = store.db.execute('SELECT * FROM discord_settings WHERE id=1').fetchone()
    if not row:
        return None, {}
    return dict(row), json.loads(row['config'])


def status(store):
    with store.lock:
        row, cfg = _settings(store)
        return {'configured': bool(cfg.get('webhook')), 'enabled': cfg.get('enabled', False),
                'live': cfg.get('live', True), 'summaries': cfg.get('summaries', True),
                'language': cfg.get('language', 'pl'), 'lastError': row['last_error'] if row else '',
                'lastSent': row['last_sent'] if row else None}


def configure(store, data):
    with store.lock:
        row, previous = _settings(store)
        raw = data.get('webhook', '')
        if not isinstance(raw, str):
            fault(400, 'Invalid Discord settings')
        webhook = raw.strip()
        if webhook:
            webhook = validate_webhook(webhook)
        else:
            webhook = previous.get('webhook', '')
        enabled = data.get('enabled', False)
        for field in ('enabled', 'live', 'summaries'):
            if type(data.get(field, True if field != 'enabled' else False)) is not bool:
                fault(400, 'Invalid Discord settings')
        if enabled and not webhook:
            fault(400, 'Enter a Discord channel webhook URL, not a server invite')
        language = data.get('language', 'pl')
        if language not in ('pl', 'en'):
            fault(400, 'Invalid Discord settings')
        changed = webhook != previous.get('webhook')
        cfg = dict(webhook=webhook, enabled=enabled, live=data.get('live', True),
                   summaries=data.get('summaries', True), language=language,
                   generation=secrets.token_hex(12) if changed else previous.get('generation', secrets.token_hex(12)),
                   since=time.time() if changed or not previous.get('enabled') else previous['since'])
        store.db.execute('''INSERT INTO discord_settings(id,config) VALUES(1,?)
        ON CONFLICT(id) DO UPDATE SET config=excluded.config,last_error='',next_attempt=0''', (json.dumps(cfg),))
    return status(store)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class DeliveryError(Exception):
    def __init__(self, message, delay=60, missing=False):
        self.delay, self.missing = delay, missing
        super().__init__(message)


def send(webhook, payload, message_id=None):
    webhook = validate_webhook(webhook)
    if message_id is not None and not re.fullmatch(r'[0-9]{1,25}', message_id):
        raise DeliveryError('Invalid Discord message ID')
    url = webhook + ('/messages/' + message_id if message_id else '?wait=true')
    request = Request(url, data=json.dumps(payload).encode(), method='PATCH' if message_id else 'POST',
                      headers={'Content-Type': 'application/json', 'User-Agent': 'ACR-Rally-Club/0.2.2'})
    try:
        with build_opener(NoRedirect).open(request, timeout=10) as response:
            data = json.loads(response.read(65536))
            ident = str(data.get('id', ''))
            if not re.fullmatch(r'[0-9]{1,25}', ident):
                raise DeliveryError('Discord did not confirm delivery')
            return ident
    except HTTPError as exc:
        if exc.code == 429:
            try:
                delay = min(86400, max(1, float(json.loads(exc.read(4096)).get('retry_after', 60))))
            except (ValueError, TypeError):
                delay = 60
            raise DeliveryError('Discord rate limit; waiting before retry', delay) from None
        if exc.code in (401, 403, 404):
            raise DeliveryError('Discord webhook or message is unavailable; check channel permissions', 3600,
                                missing=bool(message_id and exc.code == 404)) from None
        raise DeliveryError('Discord HTTP error ' + str(exc.code), 60) from None
    except (URLError, TimeoutError, OSError, ValueError):
        # Never expose a webhook token in exceptions or logs.
        raise DeliveryError('Discord connection failed; retry scheduled', 60) from None


def plain(value):
    return re.sub(r'([\\`*_~|<>\[\]()])', r'\\\1', str(value).replace('\n', ' '))[:200]


def payload(store, event_id, *, summary=False, language='pl'):
    from server import format_ms
    board = store.board(event_id)
    ev, players = board['event'], board['players']
    pl = language == 'pl'
    title = ('Podsumowanie rajdu' if summary else 'Wyniki na żywo') if pl else ('Rally summary' if summary else 'Live standings')
    rows = []
    labels = {'registered': 'Zapisany' if pl else 'Registered', 'active': 'Na odcinku' if pl else 'On stage',
              'ready': 'Między odcinkami' if pl else 'Between stages', 'awaiting_results': 'Weryfikacja' if pl else 'Verification',
              'completed': 'FINISH', 'dnf': 'DNF'}
    for place, p in enumerate(players[:20], 1):
        official = format_ms(p['total']) if p['completed_stages'] else '—'
        line = f"{place}. **{plain(p['nickname'])}** · {labels[p['status']]} · SS {p['stage_index']}/{len(ev['stages'])} · {official}"
        if not summary and p['status'] != 'completed':
            provisional = store.db.execute('SELECT clock_ms FROM provisional WHERE player_id=? ORDER BY stage_index DESC LIMIT 1', (p['id'],)).fetchone()
            if provisional:
                line += (' · telemetria ' if pl else ' · telemetry ') + format_ms(provisional['clock_ms']) + (' (niepotwierdzone)' if pl else ' (unverified)')
        rows.append(line)
    done = sum(p['status'] == 'completed' for p in players)
    dnf = sum(p['status'] == 'dnf' for p in players)
    desc = (f'Uczestnicy: {len(players)} · FINISH: {done} · DNF: {dnf}\n\n' if pl else f'Participants: {len(players)} · FINISH: {done} · DNF: {dnf}\n\n')
    desc += '\n'.join(rows) or ('Brak uczestników.' if pl else 'No participants.')
    embed = {'title': (title + ' · ' + plain(ev['name']))[:256], 'description': desc[:3900],
             'color': 0xC64851, 'footer': {'text': ('Potwierdzone czasy po weryfikacji · pełna tabela na stronie' if pl else 'Official times after verification · full standings on website')}}
    origin = os.environ.get('ACR_PUBLIC_BASE_URL', '').rstrip('/')
    if origin.startswith('https://'):
        embed['url'] = origin + '/rally/' + quote(event_id, safe='')
    return {'username': 'ACR Rally Club', 'allowed_mentions': {'parse': []}, 'embeds': [embed]}


def test_connection(store):
    with store.lock:
        row, cfg = _settings(store)
        if not cfg.get('webhook'):
            fault(400, 'Save the Discord webhook first')
        if row['next_attempt'] > time.time():
            fault(429, 'Discord is waiting before retry; try again later')
    try:
        send(cfg['webhook'], {'username': 'ACR Rally Club', 'allowed_mentions': {'parse': []},
                             'content': 'ACR Rally Club · połączenie działa / connection successful.'})
    except DeliveryError as exc:
        with store.lock:
            store.db.execute('UPDATE discord_settings SET last_error=?,next_attempt=? WHERE id=1', (str(exc), time.time()+exc.delay))
        fault(502, str(exc))
    with store.lock:
        store.db.execute("UPDATE discord_settings SET last_error='',last_sent=? WHERE id=1", (time.time(),))
    return {'ok': True}


class Worker:
    def __init__(self, store):
        self.store, self.stop_event = store, threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name='discord-notifications')

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=12)

    def tick(self):
        store = self.store
        with store.lock:
            row, cfg = _settings(store)
            now = time.time()
            if not cfg.get('enabled') or row['next_attempt'] > now:
                return
            events = [dict(r) for r in store.db.execute('SELECT id,closes FROM events WHERE opens<=? AND closes>=? ORDER BY closes', (now, cfg['since']))]
        # At most four requests per poll. Persisted message IDs survive deployment.
        budget = 4
        for ev in events:
            for kind in ('live', 'summary'):
                with store.lock:
                    current, current_cfg = _settings(store)
                    if current_cfg != cfg:
                        return
                    if not cfg['live' if kind == 'live' else 'summaries']:
                        continue
                    board = store.board(ev['id'])
                    pending = any(p['status'] in ('active', 'awaiting_results') for p in board['players'])
                    closed = now >= ev['closes'] and not pending
                    if kind == 'summary' and not closed:
                        continue
                    key = cfg['generation'] + ':' + ev['id'] + ':' + kind
                    old = store.db.execute('SELECT * FROM discord_deliveries WHERE delivery_key=?', (key,)).fetchone()
                    if kind == 'summary' and old:
                        continue
                    body = payload(store, ev['id'], summary=kind == 'summary', language=cfg['language'])
                    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
                    if old and old['digest'] == digest:
                        continue
                    mid = old['message_id'] if old else None
                try:
                    sent = send(cfg['webhook'], body, mid)
                except DeliveryError as exc:
                    with store.lock:
                        if _settings(store)[1] != cfg:
                            return
                        if exc.missing:
                            store.db.execute('DELETE FROM discord_deliveries WHERE delivery_key=?', (key,))
                        store.db.execute('UPDATE discord_settings SET last_error=?,next_attempt=? WHERE id=1', (str(exc), time.time()+exc.delay))
                    return
                with store.lock:
                    if _settings(store)[1] != cfg:
                        return
                    store.db.execute('''INSERT INTO discord_deliveries(delivery_key,message_id,digest) VALUES(?,?,?)
                    ON CONFLICT(delivery_key) DO UPDATE SET message_id=excluded.message_id,digest=excluded.digest''', (key, sent, digest))
                    store.db.execute("UPDATE discord_settings SET last_error='',last_sent=?,next_attempt=0 WHERE id=1", (time.time(),))
                budget -= 1
                if budget == 0:
                    return

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                # Keep notifier failures isolated from timing/game requests. No secrets in logs.
                print('Discord notification worker: internal error; retry scheduled', flush=True)
            self.stop_event.wait(15)
