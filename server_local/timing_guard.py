"""Serwerowe sprawdzanie czasu OS — niezależne od tego, co raportuje launcher.

Launcher działa na komputerze gracza, więc każdą jego wartość da się podrobić.
Serwer zna jednak własny zegar: kiedy dostał START danego OS-u i kiedy METĘ.
Z tego wynikają dwie twarde granice:

1. Czas OS-u z gry nie może być dłuższy niż czas, który realnie upłynął między
   START a METĄ na serwerze (plus tolerancja na opóźnienie sieci). Spreparowany
   przejazd wysłany "na szybko" (bez jazdy) jest odrzucany jako DNF.
   Różnica 10–30 s nie przerywa rajdu, tylko zostaje oznaczona do weryfikacji.
2. Oficjalny wynik odczytany z zapisu gry musi pochodzić z tego podejścia:
   jego znacznik startu nie może być starszy niż START tego OS-u na serwerze
   (z marginesem na różnicę zegarów komputera gracza i serwera). Zamyka to
   podstawianie wcześniejszych, treningowych przejazdów z pliku .sav.

Pauza w grze zatrzymuje timer OS-u, więc czas rzeczywisty może być DŁUŻSZY
od czasu OS-u — to jest dozwolone (autor dopuszcza pauzy) i nie jest karane.
"""
import time

HARD_LIMIT_MS = 30_000      # więcej = fizycznie niemożliwe -> DNF
REVIEW_LIMIT_MS = 10_000    # więcej = oznaczenie do weryfikacji
CLOCK_SKEW_S = 15 * 60      # tolerancja zegara komputera gracza wobec serwera


def install(store):
    with store.lock:
        store.db.execute('''CREATE TABLE IF NOT EXISTS stage_starts (
          player_id INTEGER NOT NULL REFERENCES players(id), stage_index INTEGER NOT NULL,
          started REAL NOT NULL, PRIMARY KEY(player_id,stage_index))''')
        store.db.execute('''CREATE TABLE IF NOT EXISTS timing_flags (
          player_id INTEGER NOT NULL REFERENCES players(id), stage_index INTEGER NOT NULL,
          detail TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(player_id,stage_index))''')


def record_start(store, player_id, stage_index, now=None):
    store.db.execute('''INSERT INTO stage_starts(player_id,stage_index,started) VALUES(?,?,?)
      ON CONFLICT(player_id,stage_index) DO UPDATE SET started=excluded.started''',
                     (player_id, stage_index, now if now is not None else time.time()))


def server_start(store, player_id, stage_index):
    row = store.db.execute('SELECT started FROM stage_starts WHERE player_id=? AND stage_index=?',
                           (player_id, stage_index)).fetchone()
    return row['started'] if row else None


def check_finish(store, player_id, stage_index, clock_ms, now=None):
    """Zwraca powód DNF (str) albo None. Drobne odchyłki zapisuje jako flagę."""
    started = server_start(store, player_id, stage_index)
    if started is None:  # rajd rozpoczęty przed aktualizacją serwera
        return None
    now = now if now is not None else time.time()
    ahead = clock_ms - (now - started) * 1000
    if ahead > HARD_LIMIT_MS:
        return ('Czas OS %d (%.1f s) dłuższy niż czas rzeczywisty między startem a metą na serwerze (%.1f s)'
                % (stage_index + 1, clock_ms / 1000, (now - started)))
    if ahead > REVIEW_LIMIT_MS:
        flag(store, player_id, stage_index,
             'OS %d: czas z gry o %.1f s dłuższy niż czas serwera — do weryfikacji' % (stage_index + 1, ahead / 1000))
    return None


def check_official_start(store, player_id, stage_index, acr_started):
    """True, jeśli wynik z pliku gry mógł powstać w tym podejściu."""
    started = server_start(store, player_id, stage_index)
    return started is None or acr_started >= started - CLOCK_SKEW_S


def flag(store, player_id, stage_index, detail):
    store.db.execute('''INSERT INTO timing_flags(player_id,stage_index,detail,created) VALUES(?,?,?,?)
      ON CONFLICT(player_id,stage_index) DO UPDATE SET detail=excluded.detail,created=excluded.created''',
                     (player_id, stage_index, detail[:300], time.time()))


def flags(store, player_id):
    return [r['detail'] for r in store.db.execute(
        'SELECT detail FROM timing_flags WHERE player_id=? ORDER BY stage_index', (player_id,))]
