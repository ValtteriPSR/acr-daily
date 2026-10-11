"""Public driver-facing, read-only handbook. Works without JS frameworks."""
from i18n import tr
from site_theme import shell


def page():
    main=tr(r"""
<section class="hero"><span class="eyebrow">Driver guide / Online start</span>
<h1>How to start in ACR Rally Club?</h1>
<p>Install the launcher once. Then start rallies using the RUN button on the club website. The application prepares all Rally Weekend settings.</p>
<p><a class="btn-link" href="/download">⬇ DOWNLOAD WINDOWS LAUNCHER</a>　 <a class="btn-link" href="/club">Sign in through Steam →</a></p>
</section>
<section class="card"><span class="section-kicker">Before your first rally</span><h2>What do you need?</h2>
<p>A Windows 10/11 computer, Assetto Corsa Rally installed through Steam, an internet connection and the club launcher.</p>
<p>The launcher runs locally because an application on your computer is needed to prepare the game save, start Steam and read telemetry.</p></section>
<section class="card"><span class="section-kicker">Step by step</span><h2>6 steps to start</h2>
<ol>
<li><strong>Install the launcher:</strong> click <a href="/download">Download launcher</a> to download the latest ACR-Rally-Club-Setup.exe, then run the installer and confirm registration of the protocol <code>acrclub://</code>. The installer does not require you to compile the application.</li>
<li><strong>Sign in through Steam:</strong> go to <a href="/club">My profile</a>, sign in on Steam and choose your club nickname. You can change it later while signed in; your entries and results remain on the same account.</li>
<li><strong>Divisions are optional:</strong> only if the season uses divisions, wait for the administrator to assign yours before starting. A season without divisions does not require an assignment.</li>
<li><strong>Enter the rally (you can register before it opens):</strong> open <a href="/">Rallies</a>, choose a round and click <strong>REGISTER FOR RALLY</strong>. Check the dates, cars, stages, weather and rules.</li>
<li><strong>Once the rally opens (UTC+2), click RUN RALLY:</strong> allow the browser to open ACR Club Launcher. Close the game first so the launcher can safely prepare and back up the save.</li>
<li><strong>Continue to START STAGE:</strong> the launcher will start ACR through Steam. Manually select <strong>Racing → Rally → Rally Weekend → CHOOSE YOUR CAR AND DO NOT CHANGE ANY SETTINGS → START RALLY</strong>, tires and then <strong>START STAGE</strong> and start driving. Keep the launcher running until the rally ends.</li>
</ol></section>
<section class="card"><h2>First save and unchanged settings</h2><p>If RUN reports a missing or invalid Rally Weekend save: create any Rally Weekend in the game, launch its first stage (finishing is not required), exit the game and click RUN again. The launcher will use the verified save format; it will not fabricate an unknown save.</p><p><strong>After RUN, choose your car only. Do not change any Rally Weekend settings: stages, damage, starting position or conditions. Changing them results in DNF. Avoid opening the Rally Weekend settings tab.</strong></p></section>
<section class="card"><span class="section-kicker">During the rally</span><h2>How does Rally Weekend work?</h2>
<p>The rally configuration includes all stages, conditions and damage rules. Choose a car permitted by the organizer under the event rules. The launcher monitors stage starts and finishes, settings checks and connection loss.</p>
<p><strong>Every stage has one attempt.</strong> Restarting, retiring or closing the game during an active attempt results in DNF for the whole rally. DNF gives zero overall, division and Power Stage points. After the last stage, allow the game to save official times and penalties.</p>
<p>Times appear on the rally page after each stage. Telemetry times are provisional; penalties and save-confirmed times appear when the game writes its save. Season, division and team standings: <a href="/seasons">Results and standings</a>. Points are awarded after the round closes. Power Stage: the fastest finishers on the last stage receive 5, 4, 3, 2, 1 points by default. Official time including penalties counts.</p></section>
<section class="card"><span class="section-kicker">Important notes</span><h2>Manual menus and save safety</h2>
<p>The launcher does not press keys or click ACR menus automatically. The driver navigates to Rally Weekend manually. The launcher writes the rally configuration to the .sav file while the game is closed.</p>
<p>Navigate manually: <strong>Racing → Rally → Rally Weekend → CHOOSE YOUR CAR AND DO NOT CHANGE ANY SETTINGS → START RALLY → automatic tire selection (J) → CONFIRM AND START RALLY → START STAGE</strong>.</p>
<p>The launcher backs up <code>PlayerDataSaveSlot.sav</code> before making changes. Do not edit the save manually during a rally or share your account access.</p></section>
<section class="card"><span class="section-kicker">Questions and troubleshooting</span><h2>What if something does not work?</h2>
<details class="round"><summary>RUN does not open anything</summary><p>Check that the EXE installer has run, that the protocol <code>acrclub://</code> is registered, and that your browser has not blocked the application. Try again from the rally page.</p></details>
<details class="round"><summary>The game opens the wrong menu</summary><p>The launcher does not navigate menus automatically. Follow the manual route above to Rally Weekend and START STAGE.</p></details>
<details class="round"><summary>I forgot my nickname or changed computers</summary><p>Open <a href="/club">My profile</a> and sign in with the same Steam account. Your club nickname and history will return.</p></details>
<details class="round"><summary>The rally is finished but no result appears</summary><p>Return to the rally page and check your status. Wait for ACR to save all stage results and for the launcher to read them. When reporting a problem, give the administrator the log at <code>%LOCALAPPDATA%\ACR Rally Club\player-events.log</code> (review it for private data first).</p></details>
<details class="round"><summary>Can I leave the game between stages?</summary><p>Check Conditions on the rally page. If breaks are allowed, close the game only at service before the next stage and wait until the launcher confirms that your save copy reached the server. Then you may close the launcher; use RUN to restore the copy and resume. In one-sitting mode, closing the game or launcher means DNF. Pausing the game or staying at service for hours is allowed while both remain open and connected. Leaving during an active stage always means DNF.</p></details>
</section>
""")
    main+=tr('<section class="card"><h2>Result confirmation before a break</h2><p>After each SS, leave the results screen or service open while the launcher reads the official result. Positive penalties available from telemetry are sent with the provisional finish time; zero or unavailable telemetry does not prove that there were no penalties. Official save results are sent as soon as the game writes them. A break requires server-confirmed times and penalties for all completed stages. Keep the launcher open after game exit and wait for confirmation that the server checkpoint was saved. If it reports an unconfirmed break, do not edit the save or assume that you can resume; contact the administrator if results never appear.</p></section>')
    main+='<section class="card"><p>'+tr('Club backup takes priority over private rallies. After an allowed service exit, wait for the launcher to confirm the server copy, close the launcher, and then you may play a private Rally Weekend. Close the game and click RUN in Club to restore your personal Club progress before the next SS. A copy that was never uploaded cannot be reconstructed from stage times.')+'</p></section>'
    return shell(tr('Driver guide — ACR Rally Club'),main,active='guide')
