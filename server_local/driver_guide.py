"""Public driver-facing, read-only handbook. Works without JS frameworks."""
from site_theme import shell


def page():
    main=r"""
<section class="hero"><span class="eyebrow">Poradnik kierowcy / Start online</span>
<h1>Jak wystartować w ACR Rally Club?</h1>
<p>Instalujesz launcher tylko raz. Potem rajdy uruchamiasz przyciskiem RUN na stronie klubu. Wszystkie ustawienia Rally Weekend przygotowuje aplikacja.</p>
<p><a class="btn-link" href="/download">⬇ POBIERZ LAUNCHER DLA WINDOWS (.EXE)</a>　 <a class="btn-link" href="/club">Załóż konto klubowe →</a></p>
</section>
<section class="card"><span class="section-kicker">Przed pierwszym startem</span><h2>Co jest potrzebne?</h2>
<p>Komputer Windows 10/11, Assetto Corsa Rally zainstalowane przez Steam, działające połączenie z Internetem i launcher klubu. Do korzystania ze strony nie musisz instalować Pythona, Gita ani uruchamiać plików .bat.</p>
<p>Launcher pracuje lokalnie, ponieważ tylko program uruchomiony na Twoim komputerze może przygotować zapis gry, uruchomić Steam i odczytać telemetrię.</p></section>
<section class="card"><span class="section-kicker">Krok po kroku</span><h2>6 kroków do startu</h2>
<ol>
<li><strong>Zainstaluj launcher:</strong> kliknij <a href="/download">Pobierz EXE</a>, uruchom instalator i potwierdź instalację protokołu <code>acrclub://</code>. Instalator nie wymaga ręcznego budowania programu.</li>
<li><strong>Utwórz konto klubowe:</strong> przejdź do <a href="/club">Mój profil</a>, wybierz nick i bezpiecznie zapisz kod odzyskiwania. Ten nick zostanie zapamiętany przez przeglądarkę.</li>
<li><strong>Sprawdź dywizję:</strong> jeśli sezon ma dywizje, poczekaj na przydzielenie przez administratora. Bez przydziału nie można wystartować.</li>
<li><strong>Zapisz się do rajdu (możesz wcześniej, przed jego startem):</strong> otwórz <a href="/">Rajdy</a>, wybierz rundę i kliknij <strong>ZAPISZ SIĘ</strong>. Sprawdź datę, samochody, OS-y, pogodę i regulamin.</li>
<li><strong>Po otwarciu rajdu (UTC+2) kliknij RUN RALLY:</strong> przeglądarka poprosi o otwarcie ACR Club Launcher — zaakceptuj. Zamknij wcześniej grę, żeby launcher mógł bezpiecznie przygotować zapis i utworzyć jego kopię.</li>
<li><strong>Przejdź do START STAGE:</strong> launcher uruchomi ACR przez Steam. Samodzielnie wybierz <strong>Racing → Rally → Rally Weekend → START RALLY</strong>, opony i następnie <strong>START STAGE</strong> i jedziesz. Launcher zostaw uruchomiony do końca rajdu.</li>
</ol></section>
<section class="card"><span class="section-kicker">W trakcie rajdu</span><h2>Jak działa Rally Weekend?</h2>
<p>Konfiguracja rajdu obejmuje wszystkie OS-y, warunki i zasady uszkodzeń. Możesz wybierać samochód z listy dopuszczonej przez organizatora zgodnie z zasadami wydarzenia. Uruchomiony launcher monitoruje rozpoczęcie i zakończenie OS-u, kontrole ustawień oraz utratę połączenia.</p>
<p><strong>Każdy OS ma jedną próbę.</strong> Restart, wycofanie się lub zamknięcie gry podczas aktywnego przejazdu powoduje DNF całego rajdu. DNF daje 0 punktów generalnych, dywizyjnych i Power Stage. Po ostatnim OS-ie pozwól grze zapisać oficjalne czasy i kary.</p>
<p>Wyniki każdego OS-u: RAW, kary i oficjalny czas, znajdują się na stronie rajdu. Klasyfikacje sezonowe, dywizji i teamów: <a href="/seasons">Wyniki i klasyfikacje</a>. Punkty zostaną przyznane po zamknięciu rundy. Power Stage: najszybsi ukończyciele ostatniego OS-u zdobywają domyślnie 5,4,3,2,1 pkt. Liczy się oficjalny czas z karami.</p></section>
<section class="card"><span class="section-kicker">Ważne uwagi</span><h2>Ręczne menu i bezpieczeństwo zapisu</h2>
<p>Wersja V6.3 nie wykonuje żadnych automatycznych naciśnięć klawiszy ani kliknięć w menu ACR. Kierowca ręcznie przechodzi do Rally Weekend. Konfiguracja rajdu jest wcześniej zapisywana w .sav przez launcher przy zamkniętej grze.</p>
<p>W takim przypadku przejdź ręcznie: <strong>Racing → Rally → Rally Weekend → START RALLY → automatyczny dobór opon (J) → CONFIRM AND START RALLY → START STAGE</strong>.</p>
<p>Launcher wykonuje kopię zapisu <code>PlayerDataSaveSlot.sav</code> przed modyfikacją. Nie modyfikuj zapisu ręcznie podczas rajdu; nie udostępniaj nikomu swojego kodu odzyskiwania.</p></section>
<section class="card"><span class="section-kicker">Pytania i problemy</span><h2>Co zrobić, gdy coś nie działa?</h2>
<details class="round"><summary>Przycisk RUN niczego nie otwiera</summary><p>Sprawdź, czy instalator EXE został uruchomiony, czy protokół <code>acrclub://</code> jest zarejestrowany oraz czy przeglądarka nie zablokowała otwarcia aplikacji. Spróbuj ponownie z poziomu strony rajdu.</p></details>
<details class="round"><summary>Gra nie otwiera odpowiedniego menu</summary><p>Sprawdź, czy gra jest na pierwszym planie. Nie klikaj w menu podczas automatycznej nawigacji. Jeśli zostanie przerwana — przejdź ręcznie trasą wskazaną powyżej. Automatyczna nawigacja nie jest gwarantowana po każdej aktualizacji gry.</p></details>
<details class="round"><summary>Nie pamiętam nicku lub zmieniłem komputer</summary><p>Otwórz <a href="/club">Mój profil</a> i użyj nicku oraz kodu odzyskiwania otrzymanego przy rejestracji.</p></details>
<details class="round"><summary>Rajd zakończony, ale brak wyniku</summary><p>Wróć do strony rajdu i sprawdź status. Poczekaj, aż ACR zapisze wyniki wszystkich OS-ów, a launcher je odczyta. Przy zgłaszaniu problemu podaj administratorowi log z <code>%LOCALAPPDATA%\ACR Rally Club\player-events.log</code> (przejrzyj go pod kątem danych prywatnych).</p></details>
<details class="round"><summary>Czy można wyjść z gry między OS-ami?</summary><p>Launcher kontroluje postęp i status sesji. Najbezpieczniej pozostać w grze i kontynuować po serwisie. Nie zamykaj launchera podczas rajdu; wyjście podczas aktywnego OS-u oznacza DNF.</p></details>
</section>
"""
    return shell('Poradnik kierowcy — ACR Rally Club',main,active='guide')
