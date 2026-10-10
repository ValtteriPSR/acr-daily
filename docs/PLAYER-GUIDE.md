# Player guide

Open https://acr-rally-club.onrender.com/ and select **PL / EN** for your language.

## Before your first rally

You need Windows 10/11, Assetto Corsa Rally installed through Steam, an internet
connection and the club launcher. You do not need Python, Git or a local server.

1. Download **ACR-Rally-Club-Setup.exe** from the website's launcher button or
   [GitHub Releases](https://github.com/ValtteriPSR/acr-daily/releases/tag/v6.3.1-cloud.1).
2. Run the installer once to register `acrclub://` links.
3. Open **My profile**, choose a nickname and save the recovery code privately.
   The code is shown only once and lets you restore your account in another browser.
4. If the championship uses divisions, wait for the organizer to assign yours.

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
- For account recovery, use your nickname and recovery code under **My profile**.

Launcher logs are stored at `%LOCALAPPDATA%\ACR Rally Club\player-events.log`.
Review them for private data before sharing them with the organizer. Do not edit
the game save manually during a rally or share your recovery code.

The EXE build and import self-test have been checked on Windows in CI. A complete
in-game run still needs verification on a computer with Assetto Corsa Rally.
