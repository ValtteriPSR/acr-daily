# ACR Rally Club — V2: kontrola integralności Rally Weekend

Ta paczka jest **kompletną nakładką** na działający u Ciebie folder `acr-daily-main` (ACR Daily + nasze dotychczasowe dodatki).

## Instalacja

1. **Zamknij** Assetto Corsa Rally, klienta i okno lokalnego serwera.
2. Dla bezpieczeństwa skopiuj `server_local/club.sqlite3` oraz `PlayerDataSaveSlot.sav` do osobnego folderu.
3. Rozpakuj ZIP i **skopiuj jego zawartość** do głównego folderu `acr-daily-main`, zastępując stare pliki.
4. Uruchom `start_local_server.bat`, następnie `run_player.bat`. Nie musisz tworzyć nowej bazy ani instalować kolejnego Pythona.
5. W razie potrzeby ponownie wygeneruj EXE przez `build_player_exe.bat` — stary EXE nie zawiera kontroli.

## Test bez zużywania próby

Uruchom `check_weekend_settings.bat`. Skrypt odczytuje własny `.sav`, pobiera listę rajdów z lokalnego serwera i informuje, czy zgadzają się reguły, trasy, pogoda, czas startu i strefy serwisowe. **Nie zmienia pliku `.sav` ani statusu na serwerze**.

Gdy plik jeszcze nie jest ustawiony na aktualny rajd, tester naturalnie zgłosi NIEZGODNOŚĆ. Najpierw zastosuj konfigurację rajdu za pomocą klienta, zamknij grę (jeśli była uruchomiona), a potem ponów test.

## Zachowanie klienta w rajdzie

- Po przygotowaniu `.sav`: kontrola lokalna, jeszcze przed uruchomieniem Steam.
- Przy START OS-u: klient czyta i porównuje rzeczywiste wartości zapisane w `.sav`.
- Około raz na sekundę: kontrola lokalna. Co 3 sekundy klient przesyła raport ustawień w heartbeacie.
- Na mecie każdego OS-u i przed wysłaniem oficjalnego wyniku: kolejna kontrola.
- Dwa następujące po sobie odczyty wykazujące niezgodność przez co najmniej 1 s → DNF całego rajdu.
- Przejściowy błąd czytania `.sav` wstrzymuje próbę; jeśli utrzymuje się ponad 10 s, następuje DNF.
- Serwer **sam** porównuje przesłane pola z własną konfiguracją wydarzenia. Brak raportu przy rozpoczęciu OS-u lub niezgodność → trwale zapisany DNF.

Porównywane pola: włączone uszkodzenia, ich intensywność, zużycie, awarie, kary, respawn, liczba i kolejność OS-ów, identyfikatory tras, pogoda, pora dnia, przyczepność, strefy serwisowe, liczba i kolejność przeciwników.

## Ważne ograniczenia

1. **Nie ma jeszcze zabezpieczenia na poziomie gry**. ACR może przetrzymywać zmiany opcji w pamięci i zapisać je na dysku dopiero później. Zmiany, których NIE ma w `.sav`, są niewidoczne dla tej kontroli.
2. Serwer otrzymuje raport **od klienta**; klient zmodyfikowany przez oszusta może raport sfałszować. To przydatna kontrola zgodności do lokalnych testów, **nie pełny antycheat**.
3. Wykrywanie zmian w połowie przejazdu, zmian kalendarza w wyniku normalnych przejść Rally Weekend, musi przejść test w rzeczywistym ACR — na razie potwierdziliśmy odczyt dwóch OS-ów z ukończonego zapisu, ale nie każdą fazę zapisywania gry.
4. DNF jest permanentny dla danego nicku i identyfikatora rajdu. Testuj na odrębnym nicku/testowym rajdzie; do resetowania lokalnej bazy nie podchodź bez kopii.

Wersja zachowuje dotychczasowe wyniki i mechanizm jednego podejścia.
