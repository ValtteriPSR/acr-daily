# Oracle migration — preparation, not a completed deployment

The deployed club remains on Render at commit
`760a085795329d1d2372cb6abb9ac1db7ad56e49` (launcher 0.2.16).
First move the application only; retain Neon until a separate database migration.

## Verified access and infrastructure (15 October 2026)

OCI REST authentication succeeds with the owner's registered API signing key.
Frankfurt is the subscribed home region. A dedicated compartment and network
were created, with web ingress on 80/443 and SSH restricted to the operator's
observed source address. Port 8790 and the database are not public.

Capacity reports returned unavailable but an actual free-size A1 request
succeeded. The Oracle Linux 9.8 staging machine uses 1 OCPU / 2 GB / 50 GB.
The unused Ubuntu staging machine was terminated with its boot disk after
validating administrative access and a native container build on Oracle Linux.
Both temporary and final allocations fit the checked free resource totals.

SSH is unavailable from this execution environment. Oracle Linux's supported
Run Command agent was verified: cloud-init completed, commands execute as root
through reviewed sudoers permissions, and SELinux remains Enforcing. An IAM
dynamic group is limited to the dedicated compartment and its policy allows
instances to execute only commands targeted at themselves. The original Ubuntu
bootstrap remains available for operators who have SSH access.

Render configuration was exported through the authenticated dashboard into a
protected migration file outside the repository. Do not commit it or include it
in command output. Provisioning user data contains no production secrets.
Run Command scripts and responses are retained by OCI: transfer secrets only
with encryption whose private receiving key remains on the target machine.

Production continues on Render; DNS has not changed. Native image preparation
and the complete 276-test SQLite regression suite passed on Oracle Linux ARM64.
Production credentials were transferred with authenticated hybrid encryption
and stored with mode 0600; the production application has not been started.
The staging application returned 200 for health, homepage, seasons, launcher
and guide; direct requests without the gateway secret returned 403. Native
Caddy configuration and administrator authentication checks passed (actual
administrator page and API returned 401 without credentials). Production-
equivalent staging Quadlet units remained active after the administrative
command finished; the subsequent gateway check passed. The full database export was restored into a disposable PostgreSQL 18 instance
and uploaded with configuration and unit templates into a private Oracle
Object Storage bucket. Controlled production cutover remains to be completed. No production Oracle deployment is claimed here.

## Prepared and testable

`cloud-init.yaml` prepares an Ubuntu 24.04 machine: distribution Docker/Compose,
an isolated `/opt/acr/source` checkout of the immutable production commit, and a
locally built image. It does not contain secrets, start the club, attach Neon,
change SSH authorization, or change network rules. It runs as root; do not add
untrusted users to the Docker group. Check `cloud-init status --wait` and
`sudo journalctl -u cloud-final` after creation. Keep secrets out of cloud-init
because provisioning data and logs can be retained by the platform.

The `Oracle portability` workflow builds on native AMD64 and ARM64 runners,
imports database/password dependencies, executes the complete server regression
suite in each image and validates Compose. A successful build is not a test of
Oracle capacity, billing, external connectivity or a live game launch.

## Provisioning after access is available

1. Inspect the actual home region, Always Free entitlement and existing usage.
   Choose an Always Free eligible Ubuntu 24.04 A1 Flex instance, initially
   1 OCPU / 2 GB RAM and a 50 GB boot disk, only if the console confirms those
   resources fit the free allocation. Do not use trial credits as proof of a
   permanently free configuration. Create no paid upgrades, extra volumes or
   load balancers automatically. If capacity is unavailable, pause and report it.
2. Review the SSH key and least-privilege network access before creating them.
   SSH should be restricted to the operator's network; public access should be
   limited to the intended web ports 80/443. Keep port 8790 and the DB private.
3. Apply the reviewed cloud-init and wait for preparation to finish. The current
   default Compose image label is older than the code version; run
   `sudo docker compose --env-file deploy/.env -f deploy/compose.yaml build`
   inside `/opt/acr/source` before eventual startup, so that Compose uses the
   current checkout rather than depending on a pre-existing image label.
4. Test with a disposable local database first. Do not attach a second running
   club process to the production Neon database: cache invalidation and the
   Discord/background workers currently assume one active application instance.
5. Transfer the existing domain, administrator path/key, HTTP administrator
   credentials and launcher download URL securely from the current deployment.
   Preserve Steam/session-related configuration. Do not generate replacement
   production credentials with the generic hosting wizard. Map the current
   `ADMIN_HTTP_PASSWORD` to a bcrypt `ADMIN_PASSWORD_HASH` for standalone Caddy.
   Keep the resulting `deploy/.env` root-readable only (0600), never in git.
   Inject the existing Neon DATABASE_URL securely only at cutover.
6. Before cutover, make a new code/database backup and compare result/penalty
   counts and fingerprints. Check there are no active stages or pending uploads.
   Keep a short maintenance window: stop the old writer first, start the new
   writer, change the existing domain's DNS, verify Caddy HTTPS, login, RUN,
   stage results, service/prestart resume, and Discord deliveries. Existing
   launchers can keep the same domain; don't require a new installer just for
   an IP change.
7. Keep a rollback path to Render. Old DNS may remain cached: keep the old origin
   in maintenance during transition, never run both production writers. If
   rollback is needed, stop Oracle before re-enabling Render. Separately plan
   the old onrender.com API used by any legacy launchers before retiring it.

## Availability and free limits

Oracle may reclaim idle Always Free compute after assessing seven days of CPU,
network and (for A1) memory usage. This is not simply a seven-day website visitor
counter. A tiny HTTP ping does not guarantee exemption. No artificial load or
automatic repeated instance creation has been added.

A paid/PAYG account can still use eligible Always Free allocations, but can also
incur real charges beyond them. The current public resource page does not give
an unconditional exemption from reclamation for this specific tenancy. Confirm
the policy with Oracle before relying on PAYG for that purpose. A budget alert
is not a hard spending cap. Do not upgrade the account without the owner's
explicit decision. For strict availability, consider a paid VM or preserve
fallback capacity; independent backups address recovery, not uninterrupted use.

Official references checked 15 October 2026:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://www.oracle.com/cloud/free/faq/
- https://packages.ubuntu.com/noble/arm64/docker-compose-v2
- https://docs.github.com/en/actions/reference/runners/github-hosted-runners

## Oracle Linux access and service files

`cloud-init-oracle-linux.yaml` is a minimal, secret-free alternative when SSH
is unavailable and OCI Run Command is used. It intentionally grants the agent's
`ocarun` account sudo access for administrative deployment. Restrict command
issuers in IAM and use the compartment-scoped self-execution policy described
above. Oracle Linux supports Run Command; the Ubuntu bootstrap is for SSH-based
operations. `prepare-oracle-linux.sh` records the executed preparation: install
`podman-docker`, Git and curl from Oracle repositories, open HTTP(S) host firewall
rules, and build the pinned production source. SELinux remains enforcing.
This script prepares the image only and does not start production.

The `quadlet/` templates use Podman's native systemd generator. They require
`/opt/acr/production.env` (application settings), `/opt/acr/gateway.env` (only
Caddy's domain, administrator route/hash and gateway secret), `/opt/acr/data`,
and `/opt/acr/Caddyfile`. Environment files must be 0600. Build the local image
from the pinned code first. Keep templates outside `/etc/containers/systemd`
until cutover: installing them there also enables them on the next reboot.
Never install/start them against production while Render is an active writer.

Validate first with `QUADLET_UNIT_DIRS=/opt/acr/prepared-units
/usr/lib/systemd/system-generators/podman-system-generator --dryrun` (one shell
command). At coordinated cutover copy reviewed templates to
`/etc/containers/systemd`, run `systemctl daemon-reload`, and start
`acr-caddy.service` (which requires `acr-app.service`). For rollback stop the
Oracle units before resuming Render, and remove/disable automatic startup so a
later reboot cannot accidentally create a second production writer.

References for the additional route:
- https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/runningcommands.htm
- https://docs.oracle.com/en/learn/ol-podman-compose/
- https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html

## Verified migration backup

Neon's additional branch request was rejected because its branch limit is full;
no existing branch or backup was deleted. A full `pg_dump --format=custom` was
instead restored successfully with `pg_restore --exit-on-error` into disposable
PostgreSQL 18. The archive includes the dump, production/gateway configuration,
Caddyfile, prepared units and immutable source commit. It contains 12 restored
results and all dumped tables, including penalties and settings.

Private Object Storage: bucket `acr-migration-backups`, object
`before-oracle-20261015.tar.gz`, Standard tier, NoPublicAccess, 133338 bytes.
SHA256: `7bb207bc17958509c53941a96d45e39166aa402807b4af3bd844e13e366d6c5d`.
The downloaded archive matched Object Storage's Content-MD5. Its application
configuration digest matched the exported Render configuration after mapping;
the Caddy bcrypt hash accepts the existing administrator password.
The OCI API private signing key is not included in this archive or repository.

Code backup: `rollback/pre-oracle-20261015` points to production commit
`760a085795329d1d2372cb6abb9ac1db7ad56e49`. Refresh the database backup immediately
before eventual cutover if new results have arrived. This is a one-time migration
backup, not a recurring backup system.

## DNS coordination still required

Current public DNS is a CNAME from `acr.projectsimracing.pl` to
`acr-rally-club.onrender.com`, TTL 3600. The domain owner should first reduce
TTL to 300 while preserving the current target, then allow the old TTL to expire.
Do not point players to the staged server yet. At a coordinated maintenance
window replace the CNAME with an A record `acr` → `92.5.82.116`, stop the old
writer, install/start the Oracle units, and verify automatic public TLS and the
real domain. These steps must be coordinated; the staged server intentionally
does not run production yet. Neon is retained during this application migration.
Account for cached DNS and legacy onrender.com launchers before retiring Render.
