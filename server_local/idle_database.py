"""Bounded per-process read cache; transactions always read the real database.

The club runs one server instance. Application writes invalidate dependent reads
immediately on commit. External DB edits become visible after at most 15 minutes.
No timer refreshes this cache: the first real request after expiry wakes Postgres.
"""
from collections import OrderedDict
import re
import threading
import time
from database import Result, Row

READ_TTL = 900
TABLES = set('events players provisional results club_settings seasons season_events '
             'club_members club_sessions club_steam_accounts season_divisions season_teams '
             'season_member_assignments admin_time_penalties telemetry_runs telemetry_penalties '
             'stage_starts timing_flags discord_settings discord_deliveries rally_recovery '
             'rally_checkpoints rally_save_problems web_sessions'.split())


class IdleDatabase:
    def __init__(self, database):
        self.raw = database
        self.versions = {}
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.lock = threading.RLock()
        self.local = threading.local()

    @property
    def in_transaction(self):
        return self.raw.in_transaction

    def signature(self, tables):
        with self.lock:
            return tuple(self.versions.get(t, 0) for t in ('*', *tables))

    def _changed(self, tables):
        if 'seasons' in tables:
            tables = tables | {'season_events','season_divisions','season_teams','season_member_assignments'}
        with self.lock:
            for table in tables:
                self.versions[table] = self.versions.get(table, 0) + 1
            # Remove invalid data, including deleted rallies, rather than only
            # making the old key unreachable. Bound cache memory throughout.
            for key, item in list(self.cache.items()):
                if '*' in tables or tables.intersection(item[3]):
                    self.cache_bytes -= item[2]
                    del self.cache[key]

    def execute(self, sql, params=()):
        command = sql.lstrip().split(None, 1)[0].upper()
        if command == 'BEGIN':
            result = self.raw.execute(sql, params)
            self.local.dirty = set()
            return result
        if command in ('COMMIT', 'ROLLBACK'):
            dirty = getattr(self.local, 'dirty', set())
            try:
                return self.raw.execute(sql, params)
            finally:
                self.local.dirty = set()
                # A failed COMMIT can have an uncertain server-side outcome.
                # Force fresh reads instead of presenting an old cached result.
                if command == 'COMMIT':
                    self._changed(dirty)
        transaction = self.in_transaction
        dependencies = set(re.findall(r'\b(?:FROM|JOIN)\s+([a-z_]+)', sql, re.I))
        dependencies = {t.lower() for t in dependencies}
        cacheable = command == 'SELECT' and not transaction and dependencies and dependencies <= TABLES
        key = None
        if cacheable:
            key = (sql, tuple(params), self.signature(sorted(dependencies)))
            with self.lock:
                item = self.cache.get(key)
                if item and time.monotonic() < item[0]:
                    self.cache.move_to_end(key)
                    return Result([Row(row) for row in item[1]], len(item[1]))
                if item:
                    self.cache_bytes -= item[2]
                    del self.cache[key]
        result = self.raw.execute(sql, params)
        if cacheable:
            rows = [dict(row) for row in result.fetchall()]
            size = sum(sum(len(str(v).encode()) for v in row.values()) + 128 for row in rows)
            if len(rows) <= 2000 and size <= 1024 * 1024:
                with self.lock:
                    while self.cache and (len(self.cache) >= 256 or self.cache_bytes + size > 4 * 1024 * 1024):
                        _, old = self.cache.popitem(last=False)
                        self.cache_bytes -= old[2]
                    self.cache[key] = (time.monotonic() + READ_TTL, rows, size, dependencies)
                    self.cache_bytes += size
            return Result([Row(row) for row in rows], len(rows))
        if command in ('INSERT', 'UPDATE', 'DELETE', 'REPLACE') and result.rowcount != 0:
            match = re.match(r'(?:INSERT(?: OR \w+)? INTO|UPDATE|DELETE FROM|REPLACE INTO)\s+([a-z_]+)', sql.strip(), re.I)
            tables = {match[1].lower()} if match else {'*'}
            if transaction:
                self.local.dirty = getattr(self.local, 'dirty', set()) | tables
            else:
                self._changed(tables)
        elif command in ('CREATE', 'ALTER', 'DROP'):
            self._changed({'*'})
        return result

    def executescript(self, script):
        self.raw.executescript(script)
        self._changed({'*'})

    def close(self):
        with self.lock:
            self.cache.clear()
            self.cache_bytes = 0
        self.raw.close()
