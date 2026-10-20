## ACR Rally Club 0.2.17

- Fix automatic RUN restarts of the Windows onefile launcher. The new process gets an independent PyInstaller runtime instead of reusing files removed when the old process exits; this addresses missing temporary base_library.zip errors reported as connection failures.
- Validate the built EXE on Windows: restart through the production helper, wait for the original bootloader and extraction to disappear, then import HTTPS dependencies and read the child's bundled standard library.
- Keep TLS certificate verification, RUN ticket handling, save protections and stage/attempt rules unchanged.
- Close the game and all old launcher windows, then install the new EXE once. No Python installation or reset of game settings is required.
- Release domain: https://acr.projectsimracing.pl.

## ACR Rally Club 0.2.16

- Clarify the breaks-allowed condition: exiting at service or before the SS clock starts is permitted.
- Report the server response before announcing DNF. A ready/registered attempt with recoveryRequired is shown as a preserved break/warning, including exit from the SS2 start line before the countdown ends; the launcher final status follows the existing server status.
- Keep the same integrity-violation requests, checkpoint rules and attempt accounting. Actual active-stage or one-sitting DNF remains DNF.
- Regression checks distinguish preserved prestart exit from actual active-stage DNF. No server race/exit policy changes.

## ACR Rally Club 0.2.15

- Add Open launcher — save tools on the public Launcher page, in Polish and English. The acrclub://tools link has no participant ticket and opens the EXE management window without starting ACR, preparing Club settings or consuming an attempt.
- If the launcher is already open, an authenticated local handoff focuses its current window without restarting the process, including during an active SS. Existing restore guards still require the game to be closed and the Club monitor to be inactive.
- Strictly reject tickets, fragments or extra paths on the tools link. Windows frozen self-test checks both RUN and tools handoff; regression checks cover no-ticket startup and safe focus during an active SS. Browser checks verify the button in PL/EN at desktop/mobile sizes.
- Requires installing launcher 0.2.15 once; older launchers do not recognize the new tools link. Subsequent tools access needs no reinstall or RUN RALLY.

## ACR Rally Club 0.2.14

- Check missing SAV/Rally Weekend before stale pending/blocked launcher flags, without discarding protected copies. Missing data enters private setup instead of suggesting restoration from a copy that does not exist.
- Keep the launcher open during setup. Show yellow instructions outside the collapsed console: create any Rally Weekend, start SS1 and wait for the countdown and Master confirmation, then exit and RUN RALLY. Private setup sends no Club start/results and consumes no Club attempt.
- Show Master-created confirmation in yellow without expanding the console. Private SS proof clears stale local transaction markers only after a valid start; existing corruption/hash safeguards stay active.
- Highlight Getting started / JAK WYSTARTOWAĆ in orange in navigation, with matching hover/current-page styles. Update the PL/EN guide and regression checks.

## ACR Rally Club 0.2.13

- Hide the participant console by default with an expand/collapse button; remove the Block RUN button.
- Quietly preserve the existing private Rally Weekend save before the first Club write. No Master confirmation/setup request when a weekend already exists. Only a missing weekend shows instructions to create a weekend and pass the SS countdown with the launcher closed.
- Report Master generation/replacement in the console with restoration guidance. A fresh, advancing SS start confirms and atomically replaces the single Master copy. Preserve the original until that confirmation; remove legacy good/quarantine archives only after the new copy commits. Single replaceable quarantine and before-RUN files prevent accumulation.
- Restore directly from the protected copy and report a matching failed server checkpoint. Keep a restart requirement; a new launcher process with the game closed can RUN without a separate private proof stage. Rejected hashes cannot be installed again. Accepted server results remain unchanged.
- Tests cover quiet initial preservation and immediate Club preparation, recovery before any successful Club SS, bounded copies, transactional metadata failure, and collapsed/expanded console. Full ACR telemetry behaviour still requires in-game testing.

## ACR Rally Club 0.2.12

- Remove periodic RAM diagnostics from the participant log/window.
- Replace manual Save works confirmation with automatic Master.sav creation and refresh only on a fresh, advancing SS timer, for private and Club weekends. Stable bounded reads and save validation still apply. No writes to the game save while it runs.
- First RUN checks a configured private Rally Weekend before preparing Club settings. Missing weekends display setup instructions; existing weekends with no current stage proof open ACR for a private SS, without consuming a Club attempt. Keep the launcher open, start SS, exit ACR and RUN again.
- Restore retains quarantine and RUN lock, requests launcher/game restart, and requires automatic SS proof before another RUN. Preserve the first protected copy plus 20 recent snapshots; reported-bad hashes stay excluded. Existing 0.2.11 confirmed copies remain usable.
- Update the PL/EN website guide and Windows packaging tests. Synthetic tests cover fresh SS starts, menu/mid-stage/repeated timer rejection, corrupt or changing file reads, pending-write confirmation, protected retention and restart requirements. Actual game telemetry must still be verified in ACR.

## ACR Rally Club 0.2.11

- Fix the actual save-corruption bug: parse mode/context/component lengths to park only the Rally Weekend state. Never scan to the next Default key. Preserve every byte outside Rally Weekend, except the required enclosing payload length.
- Bounded GVAS/settings/selection validation before writes and validation of calendar, rules and progress in uploaded/downloaded checkpoints. Invalid replacements leave the prior server copy intact; invalid legacy copies are quarantined on access.
- A separate protected copy requires explicit user confirmation after a successful game launch and normal exit. Before the first RUN: launch via Steam without RUN, enter the menu, close ACR, then press Zapis działa — zachowaj kopię. Prepared/restored saves require confirmation before another RUN.
- EXE installation opens save tools without a RUN ticket. Restore keeps a recovery lock, preserves the affected file separately, and never auto-launches a rally. Reported-bad digests cannot be reused; an earlier confirmed copy is available when the newest one was reported bad. Working/quarantine copies retain the last 15 each; protected copies are not removed by RUN.
- Server quarantine blocks repeated checkpoint restores without resetting accepted times or idle attempts. Website displays a blocked-copy warning; the PL/EN guide explains recovery and possible local progress rollback. Existing damaged copies may require administrator review instead of automatic resume.
- RUN redemption requires 0.2.11 or newer, including legacy rallies. No automatic claim that structural validity proves the game can load a file. Native Windows EXE self-test exercises atomic save writes and the recovery lock in an isolated temporary directory.
- Regression fixtures are fully synthetic. No user save, profile, device configuration or personal telemetry is included in repository/test/release files. Full in-game round-trip validation still requires an ACR test.

## ACR Rally Club 0.2.10

- RUN opens a compact dialog on the rally page. CSRF-protected single-use tickets expire after 60 seconds; no launch ticket is added to the rally URL.
- Fix pre-existing partial shared-memory open leaks. Telemetry views use existing mappings with FILE_MAP_READ, bounded sizes, transactional cleanup, idempotent close and retry backoff. No game mappings are created, resized or written.
- Visible launcher history is limited to 1200 lines. Launcher RAM/private bytes and available system memory are logged before game launch and every 30 seconds. Full event log stays on disk.
- Stress tests cover 20,000 offline samples and thousands of failed partial opens. Windows frozen EXE tests actual disposable mapping/handle cleanup and memory-counter APIs.
- The reported UE allocation of 68,008,017,920 bytes has NOT been reproduced or established as fixed. Version 0.2.9 save-writing/restoration code is identical to 0.2.8. Affected game logs/save and real ACR testing are needed to diagnose that crash.

## ACR Rally Club 0.2.9

- Live review telemetry records world X/Z positions, speed and available control inputs at approximately 1 Hz. A separate worker sends bounded batches every 3 seconds during the SS. Timing and attempt monitoring do not wait for trace delivery. Short final batches may flush after the finish.
- The collapsed Telemetry section loads driver summaries and recorded paths on demand, refreshing open views every 5 seconds. Review colours distinguish no detected signals, incomplete/questionable data, and significant signals/DNF. These are not cheating verdicts or client authenticity proofs. Maps are world-coordinate projections without an official road baseline.
- Review includes coverage, discontinuities, gaps, unusually high speed, distance, gas/brake averages where available, and RAW versus finish-telemetry differences over 250 ms. The existing 5-second rejection tolerance and observed-positive-penalty floor are preserved. No unverified penalty source was added.
- Traces and trace summaries expire 30 days after the rally closes and are deleted immediately when an administrator deletes the rally. Storage is bounded (16,000 samples per SS, 200,000 per rally, 1,000,000 total; client buffer 90 samples). Limits and outages affect telemetry completeness, not racing validity.
- Administrators can add reasoned time penalties per finished SS and revoke mistakes. Game-official rows stay immutable. Rally order, season/division/team and Power Stage points use effective times; additions appear in small text beneath the time. The actions remain in the admin audit.
- Confirmed zero penalties are green; positive penalties are red. Unknown provisional penalties remain visibly unknown. Links use compact backgrounds/outlines and hover highlighting without underlining.
- Regression checks include live submission before finish, non-blocking sender retries, immutable/idempotent batches, finite inputs, quotas, review colours, expiry/deletion, authenticated penalty controls, rally/season/Power Stage reordering and live path rendering in the browser. Actual shared-memory behaviour requires ACR game testing.

## ACR Rally Club 0.2.8

- Save copies are stored only after a confirmed non-final stage. Before SS1, RUN rebuilds the canonical event configuration without uploading a save. The final stage removes the previous resume copy.
- Copies for closed rallies expire automatically while the service runs (30-second sweep), on wake/listing requests and before checkpoint access. Results and standings remain. Free-host sleeping services perform cleanup when they wake.
- Each copy is bound to an event-specific participant ID, event ID and next-stage index. Identity mismatch triggers a second authenticated fetch before any local replacement. Tests cover overlapping rally A → B → A with independent damage/progress.
- RUN can contact an already running Windows EXE through an authenticated local named pipe and ask for confirmation before restarting it. No pickle payloads, no arbitrary commands. Active stages, open ACR and one-sitting continuation block the restart. Older EXEs must be closed manually.
- Wrong-class or changed cars before an allowed next-stage start trigger yellow recovery instead of consuming a stage. A correctly started stage still has one attempt. During-stage tampering and restart/quit rules remain enforced.
- DNF includes the affected stage number. Link text is underlined, expandable sections have visible outlines, and the orange accent is now #ff7038.
- Regression tests cover expiry, no first/final-stage saves, multi-rally restore, identity retry, wrong-class warning, DNF stage and bounded local RUN messages. The frozen Windows EXE self-test exercises the actual authenticated named pipe. Actual ACR behavior still requires game testing.

## ACR Rally Club 0.2.7

- Settings mistakes outside an active stage in a continuation rally preserve the attempt and trigger a persistent yellow restore-with-RUN warning. New starts, official submissions and checkpoint replacement are blocked until a verified restore.
- Valid personal save copies are uploaded before OS1 and after confirmed stage results while ACR is still open. Restoring after OS1 keeps stage progress, accepted penalties and damage; an accepted stage cannot be restarted.
- The launcher restores the latest server copy before local-save prerequisites. A first-stage configuration can be rebuilt before any attempt, while missing historical post-stage copies fail safely without inventing progress.
- Active-stage changes still mean DNF. Normal service breaks and one-sitting rules remain enforced. Existing DNF attempts are not automatically reset.
- Recovery warnings refresh with the standings without replacing CSRF forms. Additive database tables preserve existing results.
- Regression coverage includes first-stage recovery, live post-stage snapshots, restore acknowledgement, protected checkpoints, no results while blocked and unchanged active-stage penalties. Actual ACR persistence requires Windows game validation.

## ACR Rally Club 0.2.6

- Authenticated personal Club checkpoints take priority over unrelated local Rally Weekends and stale/missing local launcher session files. Validate owner, rally, stage, settings, checksum and in-progress save position before replacing any local data.
- Upload service checkpoints for legacy rallies too; those events previously skipped the server-backup path. Missing historical copies cannot be reconstructed from stage times. Existing legacy local continuation outside service remains unchanged.
- First RUN can prepare a Club calendar over an unrelated in-progress private weekend, retaining the full original save in the regular game backup. Resume never creates a new Club calendar or resets completed stages.
- Failed preparation at service releases the RUN lease without resetting OS results or progress. New protocol rallies require launcher 0.2.6 at stage start.
- Updated participant instructions for a Club SS, confirmed checkpoint, private weekend, and subsequent Club resume.

### Verification and limits

Regression tests simulate replacing an unrelated private save with the authenticated personal checkpoint, preserving damage and completed stages, missing local files, bad owner/rally/progress/checksum, legacy checkpoint uploads and prestart/service lease cleanup. CI validates PostgreSQL, browsers, Docker and the compiled Windows launcher. Actual Windows/ACR save persistence and Steam Cloud interaction still require a game test. No player attempts were reset to work around missing historic saves.

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
