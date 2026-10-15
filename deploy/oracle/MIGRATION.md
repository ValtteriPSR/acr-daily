# Oracle migration — preparation, not a completed deployment

The deployed club remains on Render at commit
`760a085795329d1d2372cb6abb9ac1db7ad56e49` (launcher 0.2.16).
First move the application only; retain Neon until a separate database migration.

## Current blocker

The Oracle console returned `Site Unavailable / Unable to access this site` in
the agent browser, including after a reload on 15 October 2026. No account,
region, quotas, instance, network, IP address or login session could be inspected.
No Oracle resources have been created and DNS has not changed.

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
   1 OCPU / 4 GB RAM and a 50 GB boot disk, only if the console confirms those
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
