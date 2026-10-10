"""Steam OpenID 2.0: fixed provider, browser-bound state and one-use assertions."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import re
import secrets
import sqlite3
import time
from urllib.error import URLError
from urllib.parse import urlencode, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from i18n import tr

ENDPOINT = 'https://steamcommunity.com/openid/login'
NAMESPACE = 'http://specs.openid.net/auth/2.0'
IDENTIFIER_SELECT = 'http://specs.openid.net/auth/2.0/identifier_select'
TTL = 600


def fail(code, message):
    from server import Fault
    raise Fault(code, tr(message))


def digest(value):
    return sha256(value.encode()).hexdigest()


def install(store):
    with store.lock:
        store.db.executescript('''
        CREATE TABLE IF NOT EXISTS club_steam_accounts (
          steam_id TEXT PRIMARY KEY, member_id INTEGER NOT NULL UNIQUE REFERENCES club_members(id));
        CREATE TABLE IF NOT EXISTS steam_login_states (
          state_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS steam_assertion_nonces (
          nonce_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS steam_pending_sessions (
          session_hash TEXT PRIMARY KEY, steam_id TEXT NOT NULL, expires REAL NOT NULL);
        ''')
        columns = {r['name'] for r in store.db.execute('PRAGMA table_info(club_sessions)')}
        if 'steam_verified' not in columns:
            store.db.execute('ALTER TABLE club_sessions ADD COLUMN steam_verified INTEGER NOT NULL DEFAULT 0')


def cookie(name, value, *, secure=False, age=TTL):
    return (f'{name}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}'
            + ('; Secure' if secure else ''))


def start(store, origin):
    state = secrets.token_urlsafe(32)
    now = time.time()
    with store.lock:
        for table in ('steam_login_states', 'steam_assertion_nonces', 'steam_pending_sessions'):
            store.db.execute(f'DELETE FROM {table} WHERE expires < ?', (now,))
        store.db.execute('INSERT INTO steam_login_states(state_hash,expires) VALUES(?,?)',
                         (digest(state), now + TTL))
    return_to = origin + '/auth/steam/callback?' + urlencode({'state': state})
    params = {'openid.ns': NAMESPACE, 'openid.mode': 'checkid_setup',
              'openid.return_to': return_to, 'openid.realm': origin + '/',
              'openid.identity': IDENTIFIER_SELECT, 'openid.claimed_id': IDENTIFIER_SELECT}
    return ENDPOINT + '?' + urlencode(params), state


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def verify_with_steam(params):
    """Never fetch a callback-supplied endpoint or follow a verification redirect."""
    values = {k: v for k, v in params.items() if k.startswith('openid.')}
    values['openid.mode'] = 'check_authentication'
    request = Request(ENDPOINT, data=urlencode(values).encode(),
                      headers={'Content-Type': 'application/x-www-form-urlencoded',
                               'User-Agent': 'ACR-Rally-Club/0.2.1'})
    try:
        with build_opener(NoRedirect).open(request, timeout=12) as response:
            raw = response.read(4097)
            if response.status != 200 or len(raw) > 4096:
                return False
        lines = raw.decode('utf-8').splitlines()
        if len(lines) != len(set(line.split(':', 1)[0] for line in lines)):
            return False
        answer = dict(line.split(':', 1) for line in lines if ':' in line)
        return answer.get('is_valid') == 'true' and answer.get('ns') == NAMESPACE
    except (URLError, TimeoutError, OSError, UnicodeError, ValueError):
        fail(502, 'Steam verification is temporarily unavailable. Please try again.')


def callback(store, query, browser_state, origin):
    try:
        values = parse_qs(query, keep_blank_values=True, max_num_fields=40)
    except ValueError:
        fail(400, 'Invalid Steam sign-in response')
    if any(len(v) != 1 for v in values.values()):
        fail(400, 'Invalid Steam sign-in response')
    params = {k: v[0] for k, v in values.items()}
    state = params.get('state', '')
    if (not re.fullmatch(r'[A-Za-z0-9_-]{43}', state) or not isinstance(browser_state, str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{43}', browser_state)
            or not hmac.compare_digest(state, browser_state)):
        fail(401, 'Steam sign-in expired or belongs to another browser. Sign in again.')
    with store.lock:
        row = store.db.execute('SELECT expires FROM steam_login_states WHERE state_hash=?',
                               (digest(state),)).fetchone()
    if row is None or row['expires'] <= time.time():
        fail(401, 'Steam sign-in expired or belongs to another browser. Sign in again.')
    if params.get('openid.mode') == 'cancel':
        with store.lock:
            store.db.execute('DELETE FROM steam_login_states WHERE state_hash=?', (digest(state),))
        return None
    expected_return = origin + '/auth/steam/callback?' + urlencode({'state': state})
    claimed = params.get('openid.claimed_id', '')
    identity = re.fullmatch(r'https://steamcommunity\.com/openid/id/(7656119[0-9]{10})', claimed)
    signed = set(params.get('openid.signed', '').split(','))
    required = {'op_endpoint', 'claimed_id', 'identity', 'return_to', 'response_nonce', 'assoc_handle'}
    if (params.get('openid.ns') != NAMESPACE or params.get('openid.mode') != 'id_res'
            or params.get('openid.op_endpoint') != ENDPOINT
            or params.get('openid.return_to') != expected_return or not identity
            or params.get('openid.identity') != claimed or not required.issubset(signed)
            or not params.get('openid.sig') or not params.get('openid.assoc_handle')):
        fail(401, 'Invalid Steam sign-in response')
    nonce = params.get('openid.response_nonce', '')
    try:
        stamp = datetime.strptime(nonce[:20], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
        if not 20 < len(nonce) <= 256 or not -60 <= time.time() - stamp <= TTL:
            raise ValueError()
    except (ValueError, OverflowError):
        fail(401, 'Steam sign-in response has expired')
    if not verify_with_steam(params):
        fail(401, 'Steam could not confirm this sign-in')
    # Consume state and nonce atomically, after provider verification. Concurrent
    # callbacks may verify twice but can create only one authenticated session.
    with store.lock:
        store._begin()
        try:
            consumed = store.db.execute('DELETE FROM steam_login_states WHERE state_hash=? AND expires>?',
                                        (digest(state), time.time()))
            if consumed.rowcount != 1:
                fail(401, 'Steam sign-in response was already used')
            store.db.execute('INSERT INTO steam_assertion_nonces(nonce_hash,expires) VALUES(?,?)',
                             (digest(nonce), time.time() + TTL))
            pending = secrets.token_urlsafe(32)
            store.db.execute('INSERT INTO steam_pending_sessions(session_hash,steam_id,expires) VALUES(?,?,?)',
                             (digest(pending), identity[1], time.time() + TTL))
            store.db.execute('COMMIT')
        except sqlite3.IntegrityError:
            if store.db.in_transaction: store.db.execute('ROLLBACK')
            fail(401, 'Steam sign-in response was already used')
        except Exception:
            if store.db.in_transaction: store.db.execute('ROLLBACK')
            raise
    return pending


def pending_steam_id(store, token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    with store.lock:
        row = store.db.execute('SELECT steam_id FROM steam_pending_sessions WHERE session_hash=? AND expires>?',
                               (digest(token), time.time())).fetchone()
        return row['steam_id'] if row else None
