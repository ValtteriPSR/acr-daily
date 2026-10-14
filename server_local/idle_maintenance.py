"""Keep race deadlines precise and stop idle maintenance from polling Postgres."""
import time

TABLES = ('players', 'events', 'seasons', 'season_events', 'rally_checkpoints',
          'rally_recovery', 'telemetry_runs', 'telemetry_chunks')
MAX_IDLE = 3600


def needed(store, now):
    # Never rely on cached scheduling within a critical game transaction.
    if store.db.in_transaction:
        return True
    return (now >= getattr(store, '_maintenance_at', 0) or
            store.db.signature(TABLES) != getattr(store, '_maintenance_signature', None))


def schedule(store, now):
    if store.db.in_transaction:
        return
    due = now + MAX_IDLE
    for row in store.db.execute("SELECT status,last_seen FROM players WHERE status IN ('active','awaiting_results') AND last_seen IS NOT NULL"):
        deadline = row['last_seen'] + (store.inactive if row['status'] == 'active' else 600)
        # Existing timeout comparisons use '<', so don't skip an exact boundary.
        due = min(due, max(now + .01, deadline + .01))
    row = store.db.execute('''SELECT MIN(e.closes) AS deadline FROM events e WHERE e.closes>? AND
      EXISTS (SELECT 1 FROM players p WHERE p.event_id=e.id AND
       (EXISTS (SELECT 1 FROM rally_checkpoints c WHERE c.player_id=p.id) OR
        EXISTS (SELECT 1 FROM rally_recovery r WHERE r.player_id=p.id)))''', (now,)).fetchone()
    if row and row['deadline'] is not None:
        due = min(due, row['deadline'] + .01)
    store._maintenance_at = due
    store._maintenance_signature = store.db.signature(TABLES)
