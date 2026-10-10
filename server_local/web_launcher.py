"""Website registration + one-use launch tickets (server-authoritative, stdlib)."""
from __future__ import annotations
from hashlib import sha256
import hmac
import secrets
import time


WEB_SESSION_SECONDS = 30 * 86400
LAUNCH_TICKET_SECONDS = 60
LAUNCH_LEASE_SECONDS = 300


def digest(token):
    return sha256(token.encode('ascii')).hexdigest()


def install_tables(store):
    with store.lock:
        store.db.executescript('''
          CREATE TABLE IF NOT EXISTS web_sessions (
            session_hash TEXT PRIMARY KEY,
            player_id INTEGER NOT NULL REFERENCES players(id),
            expires REAL NOT NULL
          );
          CREATE INDEX IF NOT EXISTS idx_web_sessions_exp ON web_sessions(expires);
          CREATE TABLE IF NOT EXISTS launch_tickets (
            ticket_hash TEXT PRIMARY KEY,
            player_id INTEGER NOT NULL REFERENCES players(id),
            expires REAL NOT NULL
          );
          CREATE INDEX IF NOT EXISTS idx_launch_tickets_exp ON launch_tickets(expires);
          CREATE TABLE IF NOT EXISTS launch_leases (
            player_id INTEGER PRIMARY KEY REFERENCES players(id), expires REAL NOT NULL
          );
        ''')


def enroll(store, event_id, nickname):
    """Register the nick using the existing one-per-event nickname gate."""
    result = store.join(event_id, nickname)
    cookie = secrets.token_urlsafe(32)
    with store.lock:
        store.db.execute('INSERT INTO web_sessions(session_hash,player_id,expires) VALUES(?,?,?)',
                         (digest(cookie), result['playerId'], time.time()+WEB_SESSION_SECONDS))
    # API join generated a token; never send it to the browser or put it in a URL.
    return cookie


def browser_player(store, cookie, event_id):
    if not isinstance(cookie, str) or not 40 <= len(cookie) <= 128:
        return None
    with store.lock:
        row = store.db.execute('''SELECT p.* FROM web_sessions s
          JOIN players p ON p.id=s.player_id
          WHERE s.session_hash=? AND s.expires > ? AND p.event_id=?''',
          (digest(cookie), time.time(), event_id)).fetchone()
        return dict(row) if row else None


def mint_ticket(store, cookie, event_id):
    from server import Fault
    with store.lock:
        store._begin()
        try:
            player = browser_player(store, cookie, event_id)
            if player is None:
                raise Fault(401, 'Zarejestruj nick na tej przeglądarce')
            row, _config = store.event(event_id)
            now = time.time()
            if not row['opens'] <= now <= row['closes']:
                raise Fault(409, 'Rajd jest zamknięty')
            if player['status'] not in ('registered','ready'):
                raise Fault(409, 'Próba jest już rozpoczęta lub rajd zakończony')
            leased = store.db.execute('SELECT expires FROM launch_leases WHERE player_id=?', (player['id'],)).fetchone()
            if leased is not None and leased['expires'] > now:
                raise Fault(409, 'Launcher już uruchomiony. Poczekaj na start OS-u albo upływ 5 minut.')
            existing = store.db.execute('SELECT expires FROM launch_tickets WHERE player_id=?', (player['id'],)).fetchone()
            if existing is not None and existing['expires'] > now:
                raise Fault(409, 'Bilet RUN został już wygenerowany. Poczekaj 60 sekund lub użyj poprzedniej strony.')
            store.db.execute('DELETE FROM launch_tickets WHERE player_id=? OR expires < ?', (player['id'], now))
            ticket = secrets.token_urlsafe(32)
            store.db.execute('INSERT INTO launch_tickets(ticket_hash,player_id,expires) VALUES(?,?,?)',
                             (digest(ticket), player['id'], now+LAUNCH_TICKET_SECONDS))
            store.db.execute('COMMIT')
            return ticket
        except Exception:
            if store.db.in_transaction: store.db.execute('ROLLBACK')
            raise


def redeem_ticket(store, ticket):
    from server import Fault
    if not isinstance(ticket, str) or not 40 <= len(ticket) <= 128:
        raise Fault(400, 'Nieprawidłowy bilet uruchomienia')
    with store.lock:
        store._begin()
        try:
            row = store.db.execute('''SELECT p.*,t.expires FROM launch_tickets t
              JOIN players p ON p.id=t.player_id WHERE t.ticket_hash=?''', (digest(ticket),)).fetchone()
            now = time.time()
            if row is None or now >= row['expires']:
                raise Fault(401, 'Bilet nie istnieje, wygasł lub został wykorzystany')
            erow, event = store.event(row['event_id'])
            if not erow['opens'] <= now <= erow['closes']:
                raise Fault(409, 'Rajd nie jest otwarty')
            if row['status'] not in ('registered','ready'):
                raise Fault(409, 'Próba jest już rozpoczęta lub zakończona')
            # Remove all outstanding tickets and rotate player bearer atomically.
            store.db.execute('DELETE FROM launch_tickets WHERE player_id=?',(row['id'],))
            token = secrets.token_urlsafe(32)
            store.db.execute('UPDATE players SET token_hash=? WHERE id=?',
                             (digest(token), row['id']))
            store.db.execute('INSERT OR REPLACE INTO launch_leases(player_id,expires) VALUES(?,?)',
                             (row['id'], now + LAUNCH_LEASE_SECONDS))
            store.db.execute('COMMIT')
            return {'token':token, 'event':event, 'nickname':row['nickname'],
                    'playerId':row['id'], 'status':row['status']}
        except Exception:
            if store.db.in_transaction: store.db.execute('ROLLBACK')
            raise


def abort_prestart(store, token):
    """Release RUN lease after local preparation failure. Does not reset a stage attempt.

    Only an untouched, newly registered first stage can be aborted. Bearer token
    is rotated on abort so a captured old token cannot be replayed.
    """
    from server import Fault
    with store.lock:
        store._begin()
        try:
            player=store._auth(token)
            if player['status'] != 'registered' or player['stage_index'] != 0 or player['started'] is not None:
                raise Fault(409, 'Nie można wycofać RUN po rozpoczęciu odcinka')
            store.db.execute('DELETE FROM launch_leases WHERE player_id=?', (player['id'],))
            store.db.execute('UPDATE players SET token_hash=? WHERE id=?',
                             (digest(secrets.token_urlsafe(32)), player['id']))
            store.db.execute('COMMIT')
            return {'ok':True, 'status':'registered'}
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise

def make_cookie(name, token, *, secure=False, max_age=WEB_SESSION_SECONDS):
    return (f'{name}={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={max_age}' +
            ('; Secure' if secure else ''))


def csrf_ok(cookie, posted):
    return (isinstance(cookie,str) and isinstance(posted,str) and
            len(cookie) >= 32 and hmac.compare_digest(cookie,posted))
