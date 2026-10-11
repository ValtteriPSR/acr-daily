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
