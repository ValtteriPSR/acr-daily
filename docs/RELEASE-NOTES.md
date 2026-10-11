## ACR Rally Club 0.2.5

- Read-only `penaltyTime` telemetry extension; positive penalties reported during driving and persisted with the provisional result at stage finish, before a game restart.
- Retain observed penalty floors on the server; reject save-confirmed penalties below those observations for review. Zero/unsupported telemetry is unknown, not evidence of no penalties.
- Attempt official save submission in the finish cycle and poll available results every 250 ms; no intentional wait for the next stage.
- Service breaks now require server-confirmed official results and penalties for every completed stage before checkpoint upload or restore. Clear launcher warning when results are missing.
- Additive SQLite/PostgreSQL table, bounded numeric validation, private attempt authentication and purge coverage. New protocol rallies require launcher 0.2.5 at stage start.

### Verification and limits

Tests cover byte offsets, stale frames, invalid floats, immediate finish submission, positive live penalties, decreasing penalty reports, lower save penalties and missing-result checkpoints. CI checks PostgreSQL, browsers, portable Docker and compiled Windows imports. The field layout and ACR support are documented by https://github.com/nobonobo/ac-telemetry (MIT); the pinned older ACR Daily reader did not expose this field. Actual game-version field behavior, exact finish timing and persistence on the results/service screen still need a Windows game test. No fabricated zero penalties, OCR guesses, process injection or full modified-client anti-cheat guarantee.

## ACR Rally Club 0.2.4

- New #141d30 background, #ed4703 accents and rectangular controls; responsive PL/EN pages.
- Editable club headings, PNG logo and top-navigation Discord invite, stored in the database.
- Past rallies and seasons archived behind collapsed details; all stage results start collapsed.
- Immediate per-stage telemetry times, followed by immutable save-confirmed times and penalties. Public results refresh every five seconds without replacing participant forms.
- Optional service breaks: the launcher uploads a bounded, private save checkpoint after game exit and restores it on the next RUN. One-sitting rallies reject restarts. The 15-minute in-stage pause limit is removed; the game, launcher and network must remain available.
- Validated, persistent car/stage catalog editor and ID discovery logs, consumed dynamically by the 0.2.4 launcher.
- Explicitly confirmed permanent deletion of rallies and seasons, including linked attempts and results when requested.
- Clear first-save setup instructions, green manual-navigation warning and updated participant guide. Installer links directly target the latest compiled GitHub EXE.
- Additive SQLite/PostgreSQL schema changes; branding, catalog and checkpoints move with the database. Generic portable hosting remains supported.

### Verification and limits

Automated tests cover server state transitions, progressive results, immutable times, malformed submissions, private checkpoint ownership and size limits, administrative authorization, destructive confirmations, translations and save/calendar checks. CI checks PostgreSQL, Docker portability and the compiled Windows launcher's module imports.

A full real-game Windows rally, game-generated mid-rally save persistence and anti-cheat resistance against a modified executable still require real-game testing. The client and local save are untrusted; these checks are not a cryptographic anti-cheat attestation. A SHA-256 checksum protects checkpoint transport consistency, not authenticity of a client-authored save. Pause checkpoints are limited to 4 MB uncompressed, 2 MB compressed, with 64 MB total server checkpoint storage.
