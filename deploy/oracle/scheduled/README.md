# Scheduled Oracle backups

Production schedule (Europe/Warsaw, up to two minutes jitter):

- Database: 00:15, 06:15, 12:15, 18:15 daily.
- Full recovery archive including DB, configuration, app data and units: 03:15 daily.
- Real restore test into a separate disposable database: Monday 04:45.

The first database/full upload and real restore must succeed before enabling
timers. systemd Persistent=true catches up after downtime. Jobs serialize via
flock, run at reduced CPU/I/O priority and do not restart the application.

The private Object Storage bucket is `acr-migration-backups`:

- `scheduled/database/*`: unique immutable dump objects, expire after 2 days.
- `scheduled/full/*`: unique immutable full archives, expire after 7 days.
- `latest/database.dump`, `latest/full.tar.gz`: last verified copies, replaced
  only after an immutable remote upload passes SHA256 readback. Never expire.
- Original migration snapshots: untouched by lifecycle and by this script.

Oracle lifecycle expiration is asynchronous (day-based rounding and usually up
to another day for execution); this is not an exact 48-hour/168-hour cutoff.
The newest verified copies persist even if the VM stops and short history ages
out. Bucket versioning is disabled, so replacing `latest` cannot accumulate
hidden previous versions. No bucket-wide expiration rule is installed.

The VM principal can create/read scheduled objects, but cannot overwrite/delete
them. Only the two exact latest keys allow overwrite; ETag conditions protect
against concurrent replacement. Deletion permission belongs to the regional
Object Storage service and only covers scheduled database/full prefixes.
No account API signing key is installed on the VM. Backups contain credentials
and must never be made public or attached to GitHub issues.

Files: `/opt/acr/backup-scheduled.py`, root-only `backup-schedule.env` with
ACR_BACKUP_NAMESPACE and ACR_BACKUP_BUCKET, and systemd template/timers in this
folder installed under `/etc/systemd/system`. OCI Python SDK is a host dependency.

```sh
systemctl start acr-backup@database.service
systemctl start acr-backup@full.service
systemctl start acr-backup@verify.service
systemctl enable --now acr-backup-database.timer acr-backup-full.timer acr-backup-verify.timer
systemctl list-timers 'acr-backup-*'
journalctl -u 'acr-backup@*.service'
```

Success manifests and separate failure records are root-only under
`/opt/acr/backups/scheduled/`. A failed upload/readback leaves the previous latest
copy untouched. A restore failure cleans up only its unique disposable DB.
Every upload checks Content-MD5 and verifies SHA256 by reading the remote object.
The weekly test downloads and restores the latest database, checks club tables,
results and penalty tables, and validates the full archive's recovery files.

Failures set the systemd unit to failed and write a failure status record; no
external message destination was configured. External outage/backup-age alerts
require choosing a notification channel. A host timer cannot run while the VM
is stopped. This is a single-account Oracle backup; Google Drive/off-account
copies have not been enabled. Application and launcher versions remain 0.2.16.

## Validation

`python deploy/oracle/scheduled/test_backup.py` covers corrupt remote readback,
upload failure, preserving the last verified copy, safe disposable DB cleanup,
invalid dump rejection and bounded lifecycle filters. Before production timer
activation, test real PostgreSQL dump/upload/restore and verify all three timers.

References:

- https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm
- https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm
