# Player guide

Open https://acr-rally-club.onrender.com/ and select **PL / EN** for your language.

## Before your first rally

You need Windows 10/11, Assetto Corsa Rally installed through Steam, an internet
connection and the club launcher. You do not need Python, Git or a local server.

1. Download **ACR-Rally-Club-Setup.exe** from the website's launcher button or
   [GitHub Releases](https://github.com/ValtteriPSR/acr-daily/releases/tag/v0.2.3).
2. Run the installer once to register `acrclub://` links.
3. Open **My profile → Sign in through Steam**. Sign in on the official Steam
   website and confirm the return to the club. On the first visit, choose your
   club nickname. It may differ from your Steam profile name.
4. While signed in, use **My profile → Save nickname** to change the display name.
   Your account, rally entries, attempts and results stay attached to your Steam
   identity. Use the same Steam account on another browser or computer.

The website download button downloads the latest compiled installer directly from GitHub. You do not need to open GitHub or compile any files. Your browser may save the file automatically or ask where to save it, according to its download settings.

If the championship uses divisions, wait for the organizer to assign yours.

## Start a rally

1. Open the rally page, read its rules and check cars, stages and event dates.
2. Register for the rally. You may register before its opening time.
3. During the event window, close the game and click **RUN RALLY**.
4. Allow the browser to open ACR Club Launcher. The launcher backs up the save,
   prepares Rally Weekend and starts the game through Steam.
5. In the game, select **Racing → Rally → Rally Weekend → START RALLY**, choose
   tires, then select **START STAGE**. Menu navigation is manual.
6. Keep the launcher running throughout the rally. After the last stage, allow
   the game to save official times and penalties before closing it.

Every stage has one attempt. Restarting, retiring or closing the game during an
active stage results in DNF for the rally. DNF gives zero championship, division
and Power Stage points. Use only cars and settings permitted by the organizer.

## Results and troubleshooting

Stage results show raw time, penalties and official time. Season standings are
available under **Results and standings**; points are finalized after a round closes.
Event dates use fixed UTC+2, including in winter.

- If RUN opens nothing, run the installer and check whether your browser blocked
  the external application. Launch tickets expire after 60 seconds.
- If the game opens another screen, navigate manually to Rally Weekend.
- If results are missing, wait for the game to save all stage results and for the
  launcher to read them. Check the rally status page.
- For connection problems, the first visit after inactivity may take about a minute.
- To return to your account, sign in with the same Steam account under **My profile**.
  Recovery codes are used only to link accounts created before Steam sign-in.

Launcher logs are stored at `%LOCALAPPDATA%\ACR Rally Club\player-events.log`.
Review them for private data before sharing them with the organizer. Do not edit
the game save manually during a rally or share your account access.

The EXE build and import self-test have been checked on Windows in CI. A complete
in-game run still needs verification on a computer with Assetto Corsa Rally.

## Rally schedule and conditions

Open a rally to see the start/end dates and location, then the ordered special
stages with weather, in-game time and service before each stage. The first stage
always has initial service. Long stage lists scroll inside the schedule.
**Conditions** lists damage, wear, failures, penalties, respawn, starting position,
grip, wetness and time settings. Wetness is set by stage weather; snow weather
and the starting snow-cover setting are separate values. Sign in with the same
Steam account when using another browser or computer; recovery keys are removed.
