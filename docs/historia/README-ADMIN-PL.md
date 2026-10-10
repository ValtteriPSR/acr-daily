# V5: Sezony, dywizje i teamy

Nowy panel: `http://127.0.0.1:8790/admin/seasons`. Szczegółowa instrukcja: `README-V5-SEZONY-PL.md`.

---

# ACR Rally Club — Panel administratora V3

To nakładka na działający projekt ACR Daily + ACR Rally Club V2 Integrity.
Nie zastępuje całego oryginalnego repozytorium ACR Daily.

## Aktualizacja istniejącej instalacji

1. Zamknij klienta gracza i serwer (Ctrl+C w oknie serwera).
2. Zrób kopię folderu `server_local` albo przynajmniej `server_local\club.sqlite3`.
3. Rozpakuj zawartość tej paczki bezpośrednio do folderu głównego
   `acr-daily-main`, w którym masz `start_local_server.bat`, foldery
   `client`, `server`, `server_local`, `tools` itd.
4. Zgódź się na nadpisanie plików o tych samych nazwach.
5. Uruchom `start_local_server.bat`.
6. Uruchom `open_admin.bat` lub otwórz `http://127.0.0.1:8790/admin`.
7. Przy pierwszym uruchomieniu serwer tworzy losowy klucz administratora
   w `server_local\admin_key.txt`. Otwórz ten plik Notatnikiem, skopiuj
   klucz i zaloguj się do panelu.

**Nie udostępniaj ani nie przesyłaj komuś pliku `admin_key.txt`.**
Nie ma go w tej paczce; zostanie wygenerowany dopiero na Twoim komputerze.

## Co jest w panelu?

- Lista dotychczasowych rajdów ze statusem liczby uczestników;
- tworzenie nowych rajdów i edycja/usuwanie tych bez zgłoszonych graczy;
- nazwa, identyfikator, otwarcie i zamknięcie wydarzenia;
- pojedyncza lokalizacja ACR i 2–40 OS-ów (kolejność, trasa, pogoda,
  godzina startu w grze, serwis);
- klasa aut i wybór dopuszczonych modeli z oryginalnego katalogu ACR Daily;
- poziom uszkodzeń, zużycia, awarii, tryb kar, przywracanie samochodu;
- eksport JSON, jeśli potrzebujesz zachować konfigurację również osobno.

Terminy w polach daty/godziny to czas lokalny Twojego komputera.
Serwer przechowuje je z oznaczeniem strefy (UTC) — klient gracza działa
poprawnie bez względu na jego strefę czasową.

Gdy zapiszesz rajd, klient `run_player.bat` / `ACR-Rally-Club.exe`
pobierze go z dotychczasowego endpointu `/api/events` bez żadnego importu.
Zachowujemy aktualne dane w `server_local\club.sqlite3`, nie trzeba
ponownie tworzyć rajdu demo.

## Ważne

- Rajd, do którego zapisał się choć jeden uczestnik, pozostaje niezmienny.
  Chroni to już wydane konfiguracje, wyniki oraz blokadę pojedynczej próby.
- Hasło admina jest niezależne od nicków i tokenów graczy.
- Panel korzysta z `server/src/cars.js` i `server/src/stages.js`
  oryginalnego ACR Daily. Jeżeli pliki są nieobecne, połącz nakładkę
  z pełnym repozytorium ACR Daily.
- Nadal jest to lokalna wersja testowa. Serwer domyślnie słucha na
  `127.0.0.1:8790`. **Nie publikuj portu 8790 w Internecie**; HTTP
  nie szyfruje sesji. Przy zewnętrznych graczach wymagana będzie
  bezpieczna usługa z HTTPS i silniejszymi zabezpieczeniami.
- Panel konfiguruje reguły, ale nie modyfikuje `.sav` graczy na serwerze.
  Każdy klient pobiera JSON i sam przygotowuje swój zapis gry z kopią bezpieczeństwa.
- Konto gracza to nadal nick + token, więc unikalny nick NIE oznacza
  odpornej na obejście identyfikacji jednej osoby.

## Testy

Uruchom z głównego folderu projektu:

    py -3 -m unittest discover -s tests -v

Wersja V3 zachowuje testy V2 i dodaje testy logowania, blokady edycji,
formularza oraz endpointów administracyjnych.
