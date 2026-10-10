# Development, testing and releases

## Layout

- `server_local/`: Python server, database adapter, website and administration UI.
- `client/club_local/`: Windows launcher, save preparation and telemetry monitor.
- `tools/`: catalog validation, packaging, diagnostics and database tests.
- `tests/`: server, launcher and integrity regression tests.
- `deploy/`: portable Docker Compose, credential wizard, Caddy and cloud supervisor.
- `render.yaml`: example Render Free Blueprint for Frankfurt.
- `.github/workflows/`: SQLite/PostgreSQL checks and Windows releases.

## Run tests

```sh
python tools/preflight.py --server
python -m unittest discover -s tests -q
```

PostgreSQL tests require the packages in `requirements.txt` and a disposable
database URL in `TEST_DATABASE_URL`:

```sh
python -m pip install -r requirements.txt
python tools/test_postgres.py
```

The PostgreSQL suite uses isolated schemas and removes them after testing.
GitHub Actions provides PostgreSQL 18 for these tests. Do not point a test run at
club production data. Local-mode SQLite remains supported.

## Website localization

The server selects Polish or English from an HttpOnly language cookie.
`server_local/i18n.py` scopes language state to each request using context variables.
English UI literals are translated through `server_local/translations/pl.json`.
Translate static templates before inserting user data: do not translate nicknames,
rally names, IDs, API fields or other user-authored content.

Language switching validates both the supported language and the return path.
It preserves the current page, works without JavaScript, and sets the HTML `lang`
attribute. Administrator JavaScript receives localized static templates; API
errors are localized separately. Language state must never leak between requests.

## Build and publish the Windows installer

Use **Actions → Publish Windows launcher → Run workflow** on `rally-club`.
Supply the public HTTPS club origin and a new release tag, such as `v0.2.1`.
The project release and client version are `0.2.1`. Client `0.2.0` remains compatible.
The release includes the compiled EXE, a portable source ZIP and SHA256 checksums.

The workflow configures the launcher origin, downloads the six pinned upstream
modules, verifies their Git blob hashes, exports catalogs and builds a one-file
Windows executable with PyInstaller. It then runs the frozen import self-test
and publishes the EXE and its SHA256 checksum to GitHub Releases.

Set `ACR_LAUNCHER_DOWNLOAD_URL` in Render to the published installer URL when
changing releases. Never publish administrator keys, database URLs, player tokens
or recovery codes. A build self-test is not a substitute for an in-game test.

## Deployment and security

Provider-independent deployments are documented in [Hosting](HOSTING.md).
GitHub Actions builds the portable image, validates Compose/Caddy and verifies
that its PostgreSQL drivers are installed.


Render builds `deploy/Dockerfile.render` with the repository root as its context.
Caddy's unneeded privileged-port file capability is removed for the Render sandbox.
The supervisor requires credentials, hashes the HTTP password and starts the
backend behind Caddy. See [Administration](ADMINISTRATION.md) for environment setup.

The server validates origins, trusted gateway headers, CSRF tokens, launch leases,
client versions and official result consistency. The client is not a trusted
attestor. A changed client or game save must not bypass server attempt rules.

Upstream ACR Daily client revision:
`135466d177e47039e0a8b6a6af2716379554c9e9`.
The MIT license and verified catalog files are retained. `RELEASE-MANIFEST.json`
records the current source hashes; it excludes generated files and secrets.

## Steam authentication

`server_local/steam_auth.py` implements the fixed Steam OpenID 2.0 provider.
The callback validates browser-bound state, origin, claimed SteamID, signed
fields and nonce age, then verifies the assertion directly with Steam over HTTPS.
State and nonces are consumed atomically; duplicate responses cannot mint a
session. Unrecognized users select a nickname before a club account is created.

The database migration adds Steam identity, pending sign-in and nonce tables
plus `club_sessions.steam_verified`. Old sessions cannot act as Steam sessions.
Linking a legacy account requires Steam verification and its existing recovery
code; old sessions are revoked. Nickname edits update club and rally display
names transactionally without altering member IDs, attempt state or results.
Steam IDs are not included in public standings. Logout revokes the club session.

Tests exercise signature rejection, state binding, replay, expiry, onboarding,
legacy linking, nickname conflicts, unchanged attempt identity and browser HTTP
cookies. PostgreSQL runs the same Steam suite in isolated schemas. Unit tests
mock Valve signature verification; a real Steam user must still confirm the
first production sign-in on Valve's website.

References: [Steam OpenID provider](https://steamcommunity.com/dev) and
[OpenID Authentication 2.0](https://openid.net/specs/openid-authentication-2_0.html).
