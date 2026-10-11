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

**After RUN, choose only your car. Do not change any Rally Weekend settings**, including stages, damage, starting position, weather or rules. A mismatch results in DNF. Avoid opening the weekend settings tab.

## Breaks and results

Check the policy in **Conditions**:

- **Breaks allowed:** exit only at service before the next SS. Wait for the launcher to confirm that your personal save copy reached the server; then close the launcher. Use RUN again to restore that copy and resume. A break is not confirmed until official results, including penalties, for every completed stage are stored on the server. Leave the results screen/service open to allow the game to save, and keep the launcher open until confirmation. If confirmation is missing, do not edit the save or assume that you can resume.
- **One sitting:** keep both game and launcher open throughout the rally. Closing either between stages prevents continuation and results in DNF.
- In both modes, pausing an SS or staying at service for hours is allowed while the game and launcher remain open and connected. Leaving during an active stage, restarting or retiring means DNF.

Each stage has one attempt. Times appear after every SS; telemetry times are clearly provisional. Positive penalties read from supported telemetry appear immediately with the provisional stage time. Zero/unsupported telemetry is not proof of no penalties. Official save-confirmed times appear as soon as ACR persists them, without waiting for the next stage. Final points require FINISH and are calculated after the rally closes. The page refreshes results every five seconds and preserves opened stage details.

Dates use fixed UTC+2. If RUN opens nothing, rerun the installer and allow external application links. To recover your account, sign in with the same Steam account. Logs are at `%LOCALAPPDATA%\ACR Rally Club\player-events.log`; review them before sharing.

## Private Rally Weekends between Club stages

With launcher 0.2.6, wait for a confirmed server checkpoint after an allowed exit at service, then close the launcher. You can play an unrelated private weekend. Close ACR before RUN; the Club checkpoint takes priority and restores your progress, including damage, before the next SS. The current local save is backed up before replacement. Server restoration does not depend on your old local session file. Older rallies also upload checkpoints at service using the updated launcher; copies that were never uploaded cannot be recovered from stage times. First RUN can prepare a new Club calendar over a private in-progress weekend after backing up the full original save.
