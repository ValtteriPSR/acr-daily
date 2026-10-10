# ACR Rally Club V5.1 — interfejs w stylu ligi simracingowej

Wizualnie inspirowany układem strony wyników Project Simracing; nie kopiuje logo, materiałów graficznych ani treści tej strony.

## Zmiany

- nowy pasek nawigacji (Rajdy, Wyniki i klasyfikacje, Mój profil, Launcher, Panel admina),
- ciemny motyw, czytelne kontrasty, akcenty w kolorach motorsportowych,
- kafelki rajdów ze statusem (trwa / wkrótce / zakończony),
- szczegóły rajdu z harmonogramem i działającym przyciskiem RUN,
- przeszukiwanie kierowców po nicku w klasyfikacjach,
- przełączanie generalka / dywizje w sezonie,
- klasyfikacja teamów i wyniki rund, rozwijane szczegóły OS-ów,
- responsywny układ dla telefonów,
- ujednolicony wygląd paneli admina bez zmian ich formularzy i API.

## Instalacja

1. Zamknij serwer (Ctrl+C).
2. Zrób kopię bazy `server_local/club.sqlite3` i klucza `server_local/admin_key.txt`.
3. Rozpakuj paczkę i skopiuj **jej zawartość** do obecnego folderu `acr-daily-main`, zamieniając pliki programu.
4. NIE nadpisuj ani nie usuwaj istniejących plików bazy/klucza. Ta paczka ich nie zawiera.
5. Uruchom `start_local_server.bat`.
6. Otwórz `http://127.0.0.1:8790/` i odśwież przez Ctrl+F5.

Zmiana dotyczy tylko serwera i HTML; EXE launchera nie wymaga przebudowania.

## Testy

Uruchom `test_v5.bat`. Interfejs obsługuje te same API jak wersja V5; nowe testy HTML są w `tests/test_ui_v51.py`.
