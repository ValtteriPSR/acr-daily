# ACR Rally Club V6.3 — Power Stage i diagnoza SAV

## Start rajdu bez automatycznego menu

Po RUN launcher przygotowuje Rally Weekend w pliku `PlayerDataSaveSlot.sav`, wykonuje kopię przed zmianą, uruchamia ACR przez Steam i monitoruje przejazd. **Nie** wciska klawiszy ani nie steruje menu gry.

Kierowca sam otwiera w grze **Racing → Rally → Rally Weekend → START RALLY → opony → START STAGE**. Nie zmienia kalendarza, uszkodzeń ani innych reguł podanych przez organizatora.

## Jeśli nadal jest `unexpected zone in the Rally Weekend calendar at 401`

**To błąd odczytu istniejącego pliku SAV, przed jego zapisem i przed uruchomieniem gry. Nie wywołuje go automatyczna nawigacja.** Przyczyna na Twoim aktualnym komputerze nie została jeszcze rozstrzygnięta bez najnowszego rzeczywistego `.sav`. Może to być niezgodny układ pliku po aktualizacji gry, zapis po wcześniejszej błędnej modyfikacji albo wciąż zainstalowany stary EXE.

1. **Sprawdź wersję EXE:** po kliknięciu RUN pierwsza linia w oknie launchera powinna mówić `Wersja launchera: 6.3.0 · nawigacja w menu ACR: RĘCZNA`. Jeśli tak nie jest, aktualizacja serwera sama nie wystarczyła: zbuduj/ściągnij i zainstaluj **nowy** launcher V6.3.0. Serwer będzie blokował stare launchery komunikatem HTTP 426.
2. Zamknij grę ACR i launcher. Wykonaj ręczną, bezpieczną kopię `%LOCALAPPDATA%\acr\Saved\SaveGames\PlayerDataSaveSlot.sav` w innym folderze.
3. Jeżeli błąd występuje również w V6.3, nie uruchamiaj wielokrotnie starego launchera ani nie poprawiaj SAV edytorem heksadecymalnym. Nowy launcher szuka czytelnej kopii w backupach ACR Daily i podaje ścieżkę, jeśli taką znajdzie. **Nie przywraca jej automatycznie**, by nie nadpisać postępów gry.
4. Jeżeli nie ma właściwej kopii: możesz spróbować otworzyć Rally Weekend w samej grze, bez launchera, a potem wyjść z gry, żeby ACR zapisało dane. Jeśli nadal jest błąd, potrzebny jest aktualny, rzeczywisty `.sav` do ustalenia formatu. Bez niego nie mogę zagwarantować zgodności konkretnej instalacji ACR.
5. Rajd testuj na nowym nicku. Błąd **przed rozpoczęciem OS-u** nie powinien zużyć podejścia; serwer zwalnia tymczasową blokadę RUN. Zgłoszonej do DNF próby nie przywraca automatycznie.

## Power Stage

Power Stage to **ostatni OS skonfigurowanego rajdu**. Nie dodaje się dodatkowego odcinka. Po zamknięciu rajdu serwer porównuje oficjalne czasy (RAW + kary) ostatniego OS-u **wyłącznie kierowców, którzy ukończyli wszystkie OS-y**.

- Domyślna punktacja Power Stage: **5, 4, 3, 2, 1** za miejsca od pierwszego do piątego.
- Po piątym miejscu: **0 pkt Power Stage** (reguła 1 pkt za ukończenie dotyczy tylko generalnej i dywizyjnej tabeli sezonu).
- DNF = **0 pkt** Power Stage, nawet jeśli ktoś miał najszybszy czas ostatniego OS-u przed wycofaniem się.
- Remis na ostatnim OS-ie: kierowcy dzielą miejsce i dostają te same punkty, kolejne miejsce jest odpowiednio pomijane, np. 1., 1., 3.
- Panel sezonu zawiera `Power Stage — ostatni OS`; można podać dowolną tabelę np. `10,8,6,4,2,1`, wyłączyć ją pustym polem albo nadpisać niezależnie dla każdej rundy przyciskiem **Punkty rajdu**. W oknie pojedynczego rajdu puste pole oznacza dziedziczenie z sezonu; wpisanie `0` wyłącza punkty PS w tej rundzie.
- Punkty PS wliczają się do łącznego wyniku kierowcy i do teamów w trybach **combined** oraz **general**. Klasyfikacja dywizji nalicza punkty dywizyjne osobno (bez dodawania globalnych PS do dywizyjnej tabeli).
- Nie można zmieniać tabeli po rozpoczęciu jazdy przez któregokolwiek uczestnika w rajdzie.

## Instalacja kompletnego ZIP

Rozpakuj ZIP do nowego folderu, nigdy do `acr-daily-main`. Przed zastąpieniem starszego serwera zapisz kopię bazy `server_local/club.sqlite3`, klucza `server_local/admin_key.txt` i prywatnej ścieżki panelu `server_local/admin_route.txt`.

Po uruchomieniu V6.3 możesz przywrócić do tego nowego folderu starą bazę SQLite **przed pierwszym uruchomieniem**, aby automatyczna migracja dodała kolumny Power Stage. Dane rajdów i wyniki nie są czyszczone. **Istniejące sezony migrowane z V6.2 mają Power Stage domyślnie wyłączony**, aby nie zmienić wstecz opublikowanych punktów; w panelu administratora możesz świadomie ustawić dla nich `5,4,3,2,1` przed rozpoczęciem rywalizacji. Nowo tworzone sezony otrzymują domyślnie `5,4,3,2,1`. Kopie `.sav` zostają wyłącznie na komputerach kierowców, NIE w ZIP.

Uruchom `start_local_server.bat`; panel przez `open_admin.bat`. Zbudowanie instalatora Windows EXE wymaga `build_web_launcher_exe.bat` na Windows albo GitHub Actions. **Sama paczka źródeł ZIP nie zawiera gotowej binarki EXE.** Po zbudowaniu wykonaj `install_web_launcher.bat`, który nadpisuje starszą lokalną instalację (po zamknięciu starego launchera).

## Uczciwe ograniczenie

Sprawdziłem kod, testy serwera i binarny zapis na wcześniej dostarczonym `.sav`, ale nie uruchomiłem rzeczywistej gry ani nowego EXE na Twoim Windows. Jeśli wciąż pojawia się to samo `at 401` **w oknie V6.3.0**, potrzebuję bieżącego `PlayerDataSaveSlot.sav` (może zawierać dane gry i nick; dołącz go tylko prywatnie), bo dopiero ten plik rozstrzygnie faktyczny format problematycznej instalacji.
