# Move ACR Rally Club 0.2.4 to your hosting

All server components can run on another provider. Players and administrators
still use a website; no server software runs on their personal computers.
The Windows launcher is the only local club component needed by players.

## Choose a supported hosting model

| Hosting | Supported deployment |
| --- | --- |
| Linux VPS or dedicated server with Docker Compose | Full application, Caddy HTTPS and SQLite or PostgreSQL using `deploy/compose.yaml` |
| Managed Docker platform with its own HTTPS proxy | Build `deploy/Dockerfile.render`; set the public origin and environment variables below |
| Hosting with a persistent Python process and configurable reverse proxy | Run the Python backend privately and configure a protected proxy; ask the provider about process supervision and ports |
| Ordinary shared PHP/WordPress/FTP hosting | Cannot run this Python backend by uploading its files. Use a club subdomain pointing to a separate backend, or upgrade hosting |

Use a dedicated subdomain such as `league.example.com`. An existing website can
link to that subdomain. Installing the application under a path such as
`example.com/rally/` is not supported: routes, cookies and APIs use the origin root.

Before migration, obtain the hosting provider/plan, domain, supported runtimes,
SSH or deployment access, TLS support and database options. A paid domain or
website hosting package alone does not confirm backend support.

## Full deployment on a Linux VPS

These commands run **on the destination server**, not on a player's PC.
Install Docker Engine with the Compose plugin following the provider's or Docker's
instructions. Point the subdomain's DNS A record to that server. If you publish
an AAAA record, IPv6 must reach the same server. Allow TCP 80/443; UDP 443 is
optional. Caddy needs exclusive access to those ports in this configuration.
On a server already serving other sites, have the administrator configure its
reverse proxy instead of starting a competing listener.

Clone the public application branch:

```sh
git clone --branch rally-club --single-branch https://github.com/ValtteriPSR/acr-daily.git
cd acr-daily
docker build -t acr-rally-club:0.2.4 -f deploy/Dockerfile .
```

Alternatively, extract `ACR-Rally-Club-0.2.4-Source.zip` from the GitHub release
and run the last command from its root directory.

Generate settings. Replace the domain and installer URL with your own values:

```sh
docker run --rm -it --user "$(id -u):$(id -g)" \
  --mount type=bind,source="$PWD/deploy",target=/configuration \
  acr-rally-club:0.2.4 python deploy/configure_hosting.py \
  --domain league.example.com \
  --download-url https://github.com/ValtteriPSR/acr-daily/releases/tag/v0.2.4-custom-domain \
  --postgres --output /configuration/.env
```

The `--postgres` option prompts privately for `DATABASE_URL`. To retain the
current club's accounts, rallies and results, use the existing Neon connection
string from Render's Environment tab. Do not send it in public messages.
Omit `--postgres` only for a **new empty club** using SQLite. Switching from
PostgreSQL to SQLite does not migrate the existing data automatically.

Save the printed administrator URL, browser password and application key in a
password manager. They are newly generated credentials for the new installation;
the current Render credentials are unchanged. The file `deploy/.env` is private,
created with mode 0600, and never overwritten by the wizard. Use
`deploy/.env.example` if your administrator prefers manual configuration.
Single quotes in that file preserve dollar signs in the bcrypt password hash.

Start the application **only after stopping Render if both use the same database**:

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail=100
```

The app's backend port 8790 is available only inside the Docker network.
Caddy obtains and renews HTTPS certificates. `deploy/data` persists SQLite
and local server files; named volumes persist Caddy's certificate state.
The portable image installs PostgreSQL drivers, so an external Neon database
works without changing application code.

Open `https://league.example.com/healthz` and the homepage. Then use the private
URL printed by the wizard: browser username `admin` plus its password, followed
by the separate application administrator key. Inspect the public standings and
existing club records before allowing registrations. Check a controlled launch
and an actual game stage with the new EXE before running a championship.

## Managed container hosting

If the provider terminates HTTPS and forwards to one application port, build
`deploy/Dockerfile.render` from the repository root. Despite the filename, the
image does not require Render when `ACR_PUBLIC_BASE_URL` is set explicitly.
The provider should route to `PORT`, default 10000, on the container. Set:

| Variable | Value |
| --- | --- |
| `ACR_PUBLIC_BASE_URL` | Your HTTPS origin, e.g. `https://league.example.com` |
| `DATABASE_URL` | PostgreSQL connection URL; required by this container supervisor |
| `ACR_ADMIN_PATH` | `/panel-` followed by 32 random lowercase hex characters |
| `ACR_ADMIN_KEY` | Random secret of at least 32 characters |
| `ADMIN_HTTP_PASSWORD` | Separate random password of at least 16 characters |
| `ACR_GATEWAY_SECRET` | Random shared proxy secret |
| `ACR_MIN_LAUNCHER_VERSION` | `0.2.0` |
| `ACR_LAUNCHER_DOWNLOAD_URL` | GitHub release URL for the repository whose latest EXE is compiled for this origin |
| `PORT` | The provider's assigned HTTP port |

The supervisor hashes the HTTP password and runs Caddy and the backend.
The outer proxy must preserve cookies and the Authorization header. Configure
`/healthz` as its health-check path. Do not expose backend port 8790 separately.
Inject credentials at runtime; never put them in Docker build arguments or Git.

## Steam sign-in on another host

Steam OpenID uses the public origin from `ACR_PUBLIC_BASE_URL`. The callback is
`https://YOUR_DOMAIN/auth/steam/callback`. No Steam Web API key is needed for
this sign-in flow. The server must be able to send HTTPS requests to
`steamcommunity.com` to verify Steam assertions. Preserve all `club_steam_accounts`
and club tables when moving the database. On a new domain, players sign in with
the same Steam account. Recovery-key login is no longer available.

## Build the launcher for the new domain

The current EXE targets `https://acr-rally-club.onrender.com`. Changing server
DNS does not rewrite that address inside an installed client.

1. In GitHub, open **Actions → Publish Windows launcher → Run workflow**.
2. Select branch `rally-club`.
3. Set `public_url` to `https://league.example.com`, with no path.
4. Use a new tag, for example `v0.2.4-custom-domain`; never overwrite an old release.
5. Wait for the tests, Windows build and frozen import self-test to pass.
6. Set the new server's download URL to that repository's release URL. The server resolves it to `releases/latest/download/ACR-Rally-Club-Setup.exe`; ensure that repository's latest release is built for the new public origin. Use a separate fork if you operate two domains simultaneously.
7. Ask players to install it. Installation updates both the protocol handler and
   the stored server address. The EXE needs no administrator key or database URL.

Release 0.2 uses client protocol version `0.2.0`. During migration, the known
working legacy 6.3.1 client remains accepted; the incomplete 6.3.0 build stays
blocked. A launcher compiled for the old origin still contacts the old server.
Keep its address available until participants have switched.

## Migration without losing club data

Choose a maintenance window with no active rally or player attempt. Back up the
PostgreSQL database using the provider's export/backup facility or `pg_dump`
before making changes. Protect backups and store them outside the server.

The simplest migration reuses the current Neon database:

1. Prepare the new host, domain, credentials and launcher release.
2. Stop/suspend the Render application before starting the replacement.
3. Start the replacement using the same `DATABASE_URL`.
4. Verify accounts, rallies, seasons, standings and both administrator panels.
5. Distribute the new installer and reopen the club.

**Never run two club server processes against the same database.** Startup and
background cleanup can alter player attempt state. For rollback, stop the new
server first, then resume Render. Keep its old configuration until verification.

To move to a different PostgreSQL database, restore a consistent full backup on
the destination and update `DATABASE_URL` while both applications are stopped.
Preserve the schema, relationships, identity sequences and all club tables.
Browser cookies are scoped to a hostname: on a new domain players may need
**sign in through Steam again**; existing database records remain intact. Administrator sessions require signing in again.

For a SQLite installation, stop its application before copying `deploy/data`.
Online SQLite backups can also be created with `tools/backup_club_db.py`.

## Updating the new host

Back up data and choose a quiet maintenance window. With a Git checkout:

```sh
git pull --ff-only origin rally-club
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
```

Do not delete `deploy/data`, private `.env` settings, or Caddy's named volumes.
Keep only one app instance. A website-only update does not require a new EXE;
launcher or domain changes do. Source ZIP deployments should replace code only,
preserving those same private files and volumes.

References: [Docker Compose environment interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
and [Caddy basic authentication](https://caddyserver.com/docs/caddyfile/directives/basic_auth).

Discord settings and delivery state are stored in PostgreSQL and migrate with the database. Allow outbound HTTPS to `discord.com`. The notifier runs inside the server process; on sleeping free hosting, scheduled summaries wait until the process wakes. See [Discord setup](DISCORD.md).

## Portable persistent content (0.2.4)

Branding, logo, custom catalogs and private rally checkpoints are in the same SQLite/PostgreSQL database as club results. Preserve the database when moving hosts; no upload directory or provider-specific object storage is needed. The server runs as one application process with threads. It can run directly with Python 3.13 behind the provided reverse proxy when containers are unavailable; the host must support a persistent Python process and outbound PostgreSQL/Steam/Discord connections. Static-only or PHP-only hosting needs a separate backend.

Keep TLS, gateway authentication and the private admin route. The largest participant checkpoint request is bounded at 3.5 MB; reverse proxies must permit that size. The downloaded launcher remains a direct GitHub release asset. Rebuild it for a changed public club origin as described above. Run `tools/preflight.py --server --distribution`, schema tests and a complete real-game test after migration.
