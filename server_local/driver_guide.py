"""Public driver-facing, read-only handbook. Works without JS frameworks."""
from i18n import tr
from site_theme import shell


def page():
    main=tr(r"""
<section class="hero"><span class="eyebrow">Driver guide / Online start</span>
<h1>How to start in ACR Rally Club?</h1>
<p>Install the launcher once. Then start rallies using the RUN button on the club website. The application prepares all Rally Weekend settings.</p>
<p><a class="btn-link" href="/download" target="_blank" rel="noopener noreferrer">⬇ WINDOWS LAUNCHER ON GITHUB</a>　 <a class="btn-link" href="/club">Sign in through Steam →</a></p>
</section>
<section class="card"><span class="section-kicker">Before your first rally</span><h2>What do you need?</h2>
<p>A Windows 10/11 computer, Assetto Corsa Rally installed through Steam, an internet connection and the club launcher. You do not need Python, Git or .bat files to use the website.</p>
<p>The launcher runs locally because an application on your computer is needed to prepare the game save, start Steam and read telemetry.</p></section>
<section class="card"><span class="section-kicker">Step by step</span><h2>6 steps to start</h2>
<ol>
<li><strong>Install the launcher:</strong> open <a href="/download" target="_blank" rel="noopener noreferrer">GitHub Releases</a>, download ACR-Rally-Club-Setup.exe under Assets, then run the installer and confirm registration of the protocol <code>acrclub://</code>. The installer does not require you to compile the application.</li>
<li><strong>Sign in through Steam:</strong> go to <a href="/club">My profile</a>, sign in on Steam and choose your club nickname. You can change it later while signed in; your entries and results remain on the same account.</li>
<li><strong>Check your division:</strong> if the season uses divisions, wait for the administrator to assign yours. You cannot start without an assignment.</li>
<li><strong>Enter the rally (you can register before it opens):</strong> open <a href="/">Rallies</a>, choose a round and click <strong>REGISTER FOR RALLY</strong>. Check the dates, cars, stages, weather and rules.</li>
<li><strong>Once the rally opens (UTC+2), click RUN RALLY:</strong> allow the browser to open ACR Club Launcher. Close the game first so the launcher can safely prepare and back up the save.</li>
<li><strong>Continue to START STAGE:</strong> the launcher will start ACR through Steam. Manually select <strong>Racing → Rally → Rally Weekend → START RALLY</strong>, tires and then <strong>START STAGE</strong> and start driving. Keep the launcher running until the rally ends.</li>
</ol></section>
<section class="card"><span class="section-kicker">During the rally</span><h2>How does Rally Weekend work?</h2>
<p>The rally configuration includes all stages, conditions and damage rules. Choose a car permitted by the organizer under the event rules. The launcher monitors stage starts and finishes, settings checks and connection loss.</p>
<p><strong>Every stage has one attempt.</strong> Restarting, retiring or closing the game during an active attempt results in DNF for the whole rally. DNF gives zero overall, division and Power Stage points. After the last stage, allow the game to save official times and penalties.</p>
<p>Each stage's raw time, penalties and official time are on the rally page. Season, division and team standings: <a href="/seasons">Results and standings</a>. Points are awarded after the round closes. Power Stage: the fastest finishers on the last stage receive 5, 4, 3, 2, 1 points by default. Official time including penalties counts.</p></section>
<section class="card"><span class="section-kicker">Important notes</span><h2>Manual menus and save safety</h2>
<p>The launcher does not press keys or click ACR menus automatically. The driver navigates to Rally Weekend manually. The launcher writes the rally configuration to the .sav file while the game is closed.</p>
<p>Navigate manually: <strong>Racing → Rally → Rally Weekend → START RALLY → automatic tire selection (J) → CONFIRM AND START RALLY → START STAGE</strong>.</p>
<p>The launcher backs up <code>PlayerDataSaveSlot.sav</code> before making changes. Do not edit the save manually during a rally or share your account access.</p></section>
<section class="card"><span class="section-kicker">Questions and troubleshooting</span><h2>What if something does not work?</h2>
<details class="round"><summary>RUN does not open anything</summary><p>Check that the EXE installer has run, that the protocol <code>acrclub://</code> is registered, and that your browser has not blocked the application. Try again from the rally page.</p></details>
<details class="round"><summary>The game opens the wrong menu</summary><p>The launcher does not navigate menus automatically. Follow the manual route above to Rally Weekend and START STAGE.</p></details>
<details class="round"><summary>I forgot my nickname or changed computers</summary><p>Open <a href="/club">My profile</a> and sign in with the same Steam account. Your club nickname and history will return. If you had an account before Steam sign-in, link it using its previous nickname and recovery code.</p></details>
<details class="round"><summary>The rally is finished but no result appears</summary><p>Return to the rally page and check your status. Wait for ACR to save all stage results and for the launcher to read them. When reporting a problem, give the administrator the log at <code>%LOCALAPPDATA%\ACR Rally Club\player-events.log</code> (review it for private data first).</p></details>
<details class="round"><summary>Can I leave the game between stages?</summary><p>The launcher monitors progress and session status. It is safest to stay in the game and continue after service. Do not close the launcher during the rally; leaving during an active stage means DNF.</p></details>
</section>
""")
    return shell(tr('Driver guide — ACR Rally Club'),main,active='guide')
