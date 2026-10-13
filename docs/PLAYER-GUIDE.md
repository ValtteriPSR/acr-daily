# Automatic Master backup in 0.2.12

Keep the launcher open during any private or Club Rally Weekend SS. On a fresh, advancing stage timer it automatically creates or refreshes `%LOCALAPPDATA%\ACR Rally Club\save-safety\Master.sav` with current settings. No manual Save works confirmation is needed. Before the first Club RUN, create any Rally Weekend and start its first SS (no finish required) with the launcher open; exit ACR and RUN again. A configured private weekend is opened automatically when stage proof is needed. No Club attempt is consumed during setup.

After a load crash, close ACR, report the crash and use **Przywróć potwierdzoną kopię**. Restart the launcher and game, start a private SS with the launcher open for automatic confirmation, then exit ACR and RUN. Restore does not start a Club attempt or reset server results. Earlier local progress may be rolled back. The first protected snapshot and 20 recent confirmed snapshots are retained separately from working/quarantine copies. Quarantined server saves still require administrator review.

# Player guide

Open https://acr-rally-club.onrender.com/ and select **PL / EN**.

1. Download and install [ACR-Rally-Club-Setup.exe](https://github.com/ValtteriPSR/acr-daily/releases/latest/download/ACR-Rally-Club-Setup.exe). Allow the installer to register launcher links.
2. Sign in through Steam under **My profile** and choose your club nickname. You can change it later on the same Steam account.
3. Read the rally schedule and **Conditions**, then register. Divisions are optional; assignment is required only in a season configured with divisions.
4. Close the game, then click **RUN RALLY** during the rally's opening window. Keep the launcher open.
5. Follow **Racing → Rally → Rally Weekend → CHOOSE YOUR CAR AND DO NOT CHANGE ANY SETTINGS → START RALLY → tires → START STAGE**.
6. After the final stage, allow the game to save official results and wait for the launcher to confirm submission.

The download comes straight from the latest GitHub release asset. Whether the browser asks where to save it or saves automatically depends on your browser download settings.

## Missing or invalid save

If RUN cannot prepare the Rally Weekend save, first create any Rally Weekend in the game, launch an SS (you do not have to finish), exit the game and click RUN again. The launcher needs a compatible game-created save; it does not guess an unknown save structure.

**After RUN, choose only your car. Do not change any Rally Weekend settings**, including stages, damage, starting position, weather or rules. In a rally with breaks, a mismatch outside an active SS pauses the attempt and requires restoring with RUN. A mismatch during an active SS still means DNF. Avoid opening the weekend settings tab.

## Breaks and results

Check the policy in **Conditions**:

- **Breaks allowed:** exit only at service before the next SS. Wait for the launcher to confirm that your personal save copy reached the server; then close the launcher. Use RUN again to restore that copy and resume. A break is not confirmed until official results, including penalties, for every completed stage are stored on the server. Leave the results screen/service open to allow the game to save, and keep the launcher open until confirmation. If confirmation is missing, do not edit the save or assume that you can resume.
- **One sitting:** keep both game and launcher open throughout the rally. Closing either between stages prevents continuation and results in DNF.
- In both modes, pausing an SS or staying at service for hours is allowed while the game and launcher remain open and connected. Leaving during an active stage, restarting or retiring means DNF.

Each stage has one attempt. Times appear after every SS; telemetry times are clearly provisional. Positive penalties read from supported telemetry appear immediately with the provisional stage time. Zero/unsupported telemetry is not proof of no penalties. Official save-confirmed times appear as soon as ACR persists them, without waiting for the next stage. Final points require FINISH and are calculated after the rally closes. The page refreshes results every five seconds and preserves opened stage details.

Dates use fixed UTC+2. If RUN opens nothing, rerun the installer and allow external application links. To recover your account, sign in with the same Steam account. Logs are at `%LOCALAPPDATA%\ACR Rally Club\player-events.log`; review them before sharing.

## Private Rally Weekends between Club stages

With launcher 0.2.8, wait for a confirmed server checkpoint after an allowed exit at service, then close the launcher. You can play an unrelated private weekend. Close ACR before RUN; the Club checkpoint takes priority and restores your progress, including damage, before the next SS. The current local save is backed up before replacement. Server restoration does not depend on your old local session file. Older rallies also upload checkpoints at service using the updated launcher; copies that were never uploaded cannot be recovered from stage times. First RUN can prepare a new Club calendar over a private in-progress weekend after backing up the full original save.

## Yellow settings warning (0.2.7)

In a rally that allows continuation, changing the weekend settings before OS1 or between completed stages displays a yellow warning in the launcher and on the rally page. No new starts or times are accepted until recovery. Close the game and launcher, then click RUN. Before OS1 the canonical event settings are restored; after OS1 the latest confirmed personal Club copy restores the next stage, damage and accepted times including penalties. This does not grant a second attempt at an accepted stage.

The launcher uploads a valid recovery copy while the game is open after the save contains correct progress and all completed stage results are confirmed. Wait for **KOPIA CLUB** before leaving the results screen to change any settings. If no valid copy was ever uploaded after OS1, progress cannot be reconstructed from times; contact the administrator. Normal private-game breaks still follow the event's service policy. Changes during an active stage and one-sitting restrictions remain DNF.

## RUN restart, overlapping rallies and save expiry (0.2.8)

A yellow warning means: close ACR **and the launcher EXE**, then click RUN. If the current 0.2.8 EXE is still open, RUN forwards the request to its window and asks you to confirm a launcher restart. Close the game first. An active SS or one-sitting continuation cannot be restarted this way. Old EXEs require manual closure.

A car outside the allowed list/class does not start an official attempt; follow the yellow recovery instructions. After a correct start, a restart, quitting or returning to the menu before a verified finish still means DNF. A changed car after SS1 must be restored to the original car, preserving accepted results. In a one-sitting rally, correct the car in the still-open game instead of restarting between stages.

For overlapping rounds, finish a stage in rally A, wait for its copy confirmation at allowed service, close the game and launcher, and RUN rally B. After a valid break in B, close both and RUN A again to restore A's next stage. Copies are isolated by event and participant IDs.

The server stores saves only after confirmed stages that have a following stage. Before SS1 the canonical configuration is rebuilt without storing a save; the last stage removes the previous copy. Copies for closed rallies are removed within the running service's cleanup cycle or at its next wake. Stage results remain.

## Recorded telemetry and time penalties (0.2.9)

Install the latest launcher to record telemetry. During a valid SS, position, speed and available gas/brake/gear inputs are sampled about once per second and sent in small live batches about every 3 seconds. Open **Telemetry** at the bottom of the rally page, then your name and the SS to view the recorded path and speed chart. Open telemetry views refresh every 5 seconds. Green/orange dots show the first/last sample; hover over the path for speed and inputs. The path is a world-coordinate projection, not an official road map.

Green means no signal was detected in retained data; yellow means missing data or a review signal; red means a significant signal or DNF. These colours do not prove or disprove cheating. Shared-memory data comes from the participant's computer and can be forged. Restarts/attempt rules still apply independently. No data is fabricated for older launches.

Trace delivery runs separately from timing checks. Network outages or quotas can leave an incomplete trace without causing DNF. The server limits samples to 16,000 per SS, 200,000 per rally and 1,000,000 overall. The client retains at most 90 queued samples. Telemetry is removed 30 days after the event closes (on the active cleanup cycle or next server wake), or immediately when the rally is deleted. Results remain after telemetry expiry.

Administrator-added time penalties appear beneath stage/rally times with a reason and affect standings and season points. They are separate from game-official penalties. Confirmed zero penalties are green, positive penalties red; missing provisional penalties are shown as unknown.
