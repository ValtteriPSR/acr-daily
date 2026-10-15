# Oracle Cloud deployment

Production has moved to Oracle Cloud Frankfurt, including PostgreSQL.
See [the deployment report](STATUS-20261015.md) for verified checks, backup
identifiers, remaining game validation and rollback requirements.
Application/launcher version: 0.2.16. Runtime source commit:
`760a085795329d1d2372cb6abb9ac1db7ad56e49`.

## Running layout

One Oracle Linux 9.8 A1 VM: 1 OCPU, 2 GB RAM, 50 GB boot disk.
Public HTTP/HTTPS reaches Caddy; app and PostgreSQL have no published ports.
All services use rootful Podman Quadlet and systemd. SELinux remains enforcing.
PostgreSQL 18 stores data under `/opt/acr/postgres`, mounted at
`/var/lib/postgresql` (PostgreSQL 18 image layout). Use the image's postgres UID
and GID to own the host data directory before startup; a root-owned 0700
mount prevents PostgreSQL initialization.

Root-only files under `/opt/acr`:

- `production.env`: application configuration and the local database URL.
- `gateway.env`: domain, existing administrator route/password hash and gateway secret.
- `postgres.env`: database bootstrap password and database name.
- `local-database.env`: application role connection URL for recovery/configuration.
- `Caddyfile`, `data/`, `postgres/`, `backups/` and pinned `source/` checkout.

Environment files are 0600; directories holding credentials are 0700. Never
commit them, print them in agent commands, or publish backup archives.
Run Command bodies/output can be retained by OCI, so secret transfer used
authenticated encryption with a private receiving key on the target machine.

Application role `acr_club` is not a superuser. Database `acr_club` is owned by
that role. The application connects to host `database` on the isolated container
network; the administrative bootstrap role is used only for maintenance.
PostgreSQL settings are bounded for this small VM: 128 MB shared buffers,
40 connections and 4 MB work_mem. PostgreSQL readiness gates application startup.

## Service installation and recovery

The bootstrap scripts prepare the pinned image only. `cloud-init.yaml` is an
alternative Ubuntu/SSH preparation route; the actual deployment uses
`cloud-init-oracle-linux.yaml` and `prepare-oracle-linux.sh` with official Oracle
packages. OCI Run Command provides administration when SSH is unavailable.
The agent's `ocarun` sudo access requires tightly restricted OCI command issuers.
Its dynamic group is scoped to the dedicated compartment and self-targeted
command execution. Do not deploy account-wide signing keys onto the VM.

Before installing the templates under `/etc/containers/systemd`, create the
private environment files, initialize the database, restore a current dump and
compare data. Preserve existing administrator/Steam configuration. Do not run
two club processes against production: caches/background workers assume one
active writer. Stop the old writer before the final dump and cutover.

Copy the `quadlet/` files into `/etc/containers/systemd`, then run:

```sh
systemctl daemon-reload
systemctl start acr-caddy.service
systemctl is-active acr-postgres.service acr-app.service acr-caddy.service
```

The generated units' `[Install] WantedBy=multi-user.target` establishes boot
activation. They depend on the network; Caddy requires the app and the app
requires PostgreSQL. Check generated units with Podman's system generator and
`systemctl cat`, not by trying to enable the generated services manually.
The domain's A record is `acr` → `92.5.82.116`; Caddy manages public TLS.
Do not use a CNAME record whose target is a literal IP address.

## Backups

Scheduled backups are now enabled: database every six hours, full recovery
archive daily, isolated restore test weekly. See [schedule and short retention](scheduled/README.md).
Short history expires after 2/7 days; the last verified database/full copies
remain available without expiration. The manual script below is independent.

`backup-once.sh` is a root-only, manually invoked full database/configuration
snapshot, not a scheduled job. Required host dependencies: Podman, Python and
Oracle's `oci` Python SDK. It checks the custom dump's catalog before archiving,
uses unique object names, verifies upload Content-MD5, and records a SHA256
manifest locally. Initial migration restore was tested in PostgreSQL 18.

Set `ACR_BACKUP_NAMESPACE` to the tenancy Object Storage namespace and optionally
`ACR_BACKUP_BUCKET` (default `acr-migration-backups`) when invoking it.
The instance principal needs only this scoped policy (replace the compartment ID):

```text
Allow dynamic-group acr-club-command-agents to manage objects in compartment id COMPARTMENT_OCID where all {target.bucket.name='acr-migration-backups', target.object.name='cutover/*', request.permission='OBJECT_CREATE'}
```

This cannot overwrite or delete old copies, list objects or download them.
An authorized operator separately downloads and verifies the recorded SHA256.
Keep the bucket private. The archive contains application/database secrets.
A restore requires recreating the non-superuser application role/ownership,
restoring with `--exit-on-error --no-owner --no-acl --role=acr_club`, and checking
results, penalties and sequence state before starting the application.

The original Neon database is preserved but becomes stale after Oracle starts
accepting writes. For rollback first stop Oracle and disable/remove its boot
activation, then transfer its latest database into the rollback target. Only
then start Render and change DNS. Never simply resume Render against stale Neon.
Its automatic deploy setting is off and the service is suspended.

Legacy launchers configured directly for onrender.com must be reconfigured to
the club domain or installed again from the current club page. Launchers already
using the club domain retain it. No launcher code changed for the infrastructure
migration. Real Steam/RUN/stage/result/resume checks need the user's Windows game.

## Free tier and availability

The allocated resources fit the checked Always Free entitlement. No paid
upgrade or artificial CPU, memory or network load was introduced. Oracle can
reclaim idle Always Free compute based on seven-day resource measurements;
a simple website ping does not guarantee exemption. Backups and process restart
policies improve recovery, not uninterrupted availability or an SLA. Do not
upgrade to PAYG or create paid resources without the owner's explicit decision.

References checked during deployment:

- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/runningcommands.htm
- https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects.htm
- https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html
- https://hub.docker.com/_/postgres
