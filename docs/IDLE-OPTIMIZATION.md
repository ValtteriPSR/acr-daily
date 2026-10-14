# Idle operation and telemetry retention

This is a server-only update. VERSION and the launcher protocol remain 0.2.16;
existing launchers continue to use the same endpoints and JSON payloads.

## Allowing Neon to suspend

The previous cleanup thread queried the DB every 30 seconds. The Discord worker
also checked it every 15 seconds. Either could prevent a five-minute idle suspend.

Workers now inspect in-memory mutation versions and scheduled deadlines first.
When idle, housekeeping reconciles at most once an hour. Game start, heartbeat,
finish, recovery and administrative changes invalidate the relevant data and
schedule immediately. Existing active-stage and official-result timeouts are
unchanged. Registered players and service/prestart breaks do not become active
stages merely because maintenance wakes up.

Deterministic reads use an on-demand cache: up to 256 entries / 4 MiB, maximum
1 MiB and 2,000 rows per entry, 15-minute TTL. Cache hits execute no SQL. A cache
expiry does not start a refresh job; the next request refreshes it. Transactional
reads always bypass the cache. Writes invalidate affected entries on commit,
including removal of deleted rallies from memory. Failed/uncertain commits also
invalidate. Session expiry is checked against the current clock on every use;
logout/revocation through this application invalidates cached identities.

The cache is intended for the existing **single-instance** service. Direct SQL
edits outside the application may take up to 15 minutes to appear in cached
reads. Do not scale the deployment to multiple instances without replacing this
invalidation scheme with a shared revision mechanism. Admin-panel changes are
visible immediately on the existing instance.

PostgreSQL already uses a pool with minimum zero connections and a 60-second idle
connection timeout. The first uncached request automatically acquires a connection
and wakes Neon. Render Free may also take about a minute to wake its server.
These changes do not guarantee a monthly quota under arbitrary real traffic.

## Data lifecycle

* A rally belonging to an expired/archived season loses raw trace chunks and trace
  summaries once the rally has been closed for seven days **and** its season has
  ended. A running season retains its traces. Standalone rallies keep the prior
  30-day retention policy.
* Cleanup runs on startup, when necessary on requests, and at the next scheduled
  maintenance (up to one hour while running). A sleeping server cleans up when
  it next wakes. There is no keep-alive cron.
* Official results, provisional finish records, observed game penalties,
  administrator penalties (including reasons and revocations), timing guard
  evidence, season membership and scores remain. `telemetry_penalties` contains
  race penalties and is deliberately **not** removed as raw telemetry.
* New trace chunks are compressed when smaller, with the old JSON format still
  readable. Wire formats, digests and duplicate-batch checks do not change.
  Decoding is bounded to 64 KiB per batch.
* Manual confirmed rally deletion removes all related rows from the active club
  DB, including traces, penalties, results, tickets, leases, checkpoints,
  recovery/quarantine records, season links, delivery records and relevant audit
  entries. Shared club accounts and the season itself remain. Cached reads are
  invalidated as part of this deletion.
* Historical backups, platform request logs and already published Discord
  messages are not erased by deleting a rally from the active database.

Postgres DELETE releases space for reuse; it need not immediately reduce the
displayed allocated size. No blocking VACUUM FULL is performed during racing.

## Verification

`tests/test_idle_optimization.py` checks zero SQL during simulated idle periods,
read-cache reuse/expiry/invalidation, transaction rollback and fresh critical
reads, session expiry/revocation, first start after idle, unchanged active-stage
and official-result timeouts, safe service breaks, lossless old/new trace formats,
retention boundaries, preservation of result/penalty rows and complete confirmed
deletion. It runs in both the SQLite and disposable PostgreSQL suites. Existing
game-save, resume, timing, HTTP and browser regressions remain required.
