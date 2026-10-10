# ACR Rally Club V4 — RUN ze strony WWW (prototyp lokalny)

Ta paczka jest **nakładką na istniejący folder `acr-daily-main`** z ACR Daily,
na którym działają już nasze wcześniejsze wersje ACR Rally Club.
Nie zawiera całego oryginalnego repozytorium ACR Daily ani skompilowanego EXE.

## Co zostało dodane

- Rejestracja nicku bez Steam bezpośrednio na stronie rajdu.
- Przycisk `RUN RALLY` na `/rally/<id>`.
- Jednorazowe bilety startowe ważne 60 s, bez długotrwałego tokenu w linku.
- Rejestracja launchera w Windows jako handler `acrclub://`.
- Nowy `ACR-Club-Launcher.exe` otwierany ze strony.
- Zachowany monitoring przejazdu V3.1: START, restart, wyjście, pauza, kontrola ustawień,
  wyniki i kary z `PlayerDataSaveSlot.sav`, blokada DNF po stronie serwera.
- Nadal działa panel administratora i istniejąca baza SQLite.

## Instalacja (na komputerze organizatora / pierwszy test)

**Zamknij grę, serwer i klienta przed aktualizacją.**

1. Zrób kopię:
   - `server_local\club.sqlite3` (jeśli jest);
   - `%LOCALAPPDATA%\acr\Saved\SaveGames\PlayerDataSaveSlot.sav`.
2. Rozpakuj tę paczkę osobno, a jej **zawartość** skopiuj do `acr-daily-main`.
   Połącz foldery i zastąp pliki, ale **nie usuwaj** dotychczasowej bazy.
3. Na Windows uruchom `build_web_launcher_exe.bat`. Trwa chwilę i wymaga
   zainstalowanego Pythona oraz PyInstaller. Automatycznie powstanie:

       dist\ACR-Club-Launcher.exe

4. Uruchom `install_web_launcher.bat`. Instaluje launcher dla **bieżącego użytkownika**
   i rejestruje protokół `acrclub://` bez uprawnień administratora.
5. Uruchom `start_local_server.bat`. Serwer domyślnie nasłuchuje na 127.0.0.1:8790.
6. W przeglądarce otwórz: `http://127.0.0.1:8790/`.
7. Wybierz nowy rajd z panelu `/admin` lub istniejący, **na który nie wykorzystano próby**.
8. Otwórz stronę tego rajdu, wpisz nowy nick i kliknij `ZAPISZ SIĘ`.
9. Kliknij `RUN RALLY`. Jeśli przeglądarka pyta, zaakceptuj otwarcie
   `ACR Club Launcher`. Jeśli automatyczny start zostanie zablokowany,
   kliknij **OTWÓRZ LAUNCHER** na stronie potwierdzenia.
10. Launcher sprawdzi `.sav`, zrobi kopię bezpieczeństwa, zapisze kalendarz,
    uruchomi Steam i będzie nadzorował wszystkie OS-y aż do wyniku/DNF.
11. W grze otwórz `Rally Weekend`, wybierz dozwolony samochód i jedź.
12. Odśwież stronę rajdu, aby obejrzeć wynik.

## Instalacja u gracza po zbudowaniu EXE

Docelowy kierowca nie musi instalować Pythona. Możesz przekazać mu zbudowany
`ACR-Club-Launcher.exe`; po jednorazowym uruchomieniu go z parametrem `--install`
przez odpowiedni instalator Windows otrzyma obsługę `acrclub://`.
Dla lokalnego testu użyj `install_web_launcher.bat` — nie potrzebuje Pythona,
o ile EXE zostało już zbudowane.

Plik launchera zostanie skopiowany do:

    %LOCALAPPDATA%\Programs\ACR Rally Club\ACR-Club-Launcher.exe

A jego konfiguracja serwera do:

    %LOCALAPPDATA%\ACR Rally Club\launcher-config.json

Domyślnie:

    {"server": "http://127.0.0.1:8790"}

**W tej wersji RUN działa tylko wtedy, gdy serwer i launcher są na tym samym
komputerze.** Rozgrywki między komputerami wymagają konfiguracji publicznego
serwera HTTPS (oraz osobnego wdrożenia), nie wystarczy skopiować lokalnej strony.

## Bezpieczeństwo i zachowanie jednej próby

- Strona przechowuje identyfikator przeglądarki w `HttpOnly; SameSite=Lax` cookie.
- Token API uczestnika nigdy nie trafia do URL `acrclub://`.
- Każdy `ticket` można odebrać tylko raz. Po wydaniu blokujemy równoległe
  bilety; po odebraniu blokujemy powtórny RUN na 5 minut lub do potwierdzonego START.
- Serwer blokuje dodatkową próbę po rozpoczęciu OS; restart/wyjście = DNF.
- Dotychczasowe kontrole ustawień `.sav` i odczyt oficjalnych czasów pozostają.
- Jeśli launcher zostanie zamknięty podczas jazdy: DNF.
- Nick **nie jest tożsamością odporną na oszustwa**: inny nick to nowe zgłoszenie.
- Lokalne modyfikacje klienta i fałszowanie raportów pozostają możliwe.
  To nie jest jeszcze produkcyjny antycheat.

## Ograniczenia pierwszego testu

- Strona uruchamia **lokalny** program raz zainstalowany przez gracza;
  sama przeglądarka nie może zapisywać `.sav` ani sterować grą.
- W Chrome/Edge może pojawić się pytanie o zgodę na otwarcie protokołu.
- Jeśli nie działa automatyczne przejście, na stronie po RUN jest
  dodatkowy link do ręcznego otwarcia launchera (przez maksymalnie 60 sekund).
- Jeśli zamkniesz launcher **przed** startem OS, serwer może przez maksymalnie
  5 minut blokować kolejne RUN, aby uniknąć dublowania instancji.
- Po utracie przeglądarkowych cookies nie odzyskasz automatycznie przypisanego
  nicku na innym komputerze. Wprowadzenie kont będzie osobnym etapem.
- Program nie jest przetestowany w rzeczywistym środowisku Windows/ACR
  podczas pisania tej wersji; jest przeznaczony na pierwszy test integracyjny.

## Gdzie są logi?

    %LOCALAPPDATA%\ACR Rally Club\player-events.log

Jeżeli RUN nie otwiera launchera, sprawdź czy protokół zarejestrowano:
Win+R i wpisz `acrclub://start?ticket=invalid` — powinno otworzyć launcher
z komunikatem o nieprawidłowym bilecie. Ten test **nie zużywa próby**.

## Testy kodu

W środowisku źródłowym przeszły 34 testy Python (28 wcześniej istniejących,
6 nowych dla mechanizmu WWW, CSRF i jednokrotnych ticketów).
Nie stanowi to testu z uruchomioną grą ani zbudowanym EXE na Windows.
