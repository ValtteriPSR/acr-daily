# ACR Rally Club V6.3.1 — naprawa EXE i importu settings

Problem: wersja V6.3.0 potrafiła zbudować launcher bez pliku `acr_daily/settings.py`.
U kierowcy powodowało to błąd: `cannot import name 'settings' from 'acr_daily'`,
już po pobraniu biletu RUN, ale **przed rozpoczęciem OS-u**.

## Co zmieniono
- Dodano oryginalny moduł `client/acr_daily/settings.py` z ACR Daily (MIT).
- Skrypt vendorowania sprawdza hash pliku z przypiętej rewizji.
- Dodano jawny import `acr_daily.settings` i flagi PyInstaller wymuszające umieszczenie go w EXE.
- Nowy `tools/verify_launcher_modules.py` sprawdza import modułów przed kompilacją.
- Gotowy EXE przechodzi dodatkowo autotest `--self-test` po zbudowaniu, przed instalacją lub publikacją. Nie korzysta z gry, serwera ani biletów RUN.
- Podniesiono wersję launchera i wymaganie serwera do 6.3.1.
- Web Launcher nie importuje całego `club_local.app` tylko po to, aby pobrać ścieżkę do sesji.

## Instalacja lokalna
1. Zamknij serwer i launcher. Zrób kopię `server_local/club.sqlite3`, `server_local/admin_key.txt`, `server_local/admin_route.txt` i `.sav`.
2. Rozpakuj V6.3.1 do NOWEGO folderu, bez nakładania na stary.
3. Przenieś tylko własne pliki bazy oraz klucze (po zatrzymaniu serwera).
4. Uruchom `start_local_server.bat`.
5. Uruchom `build_web_launcher_exe.bat`, poczekaj na `GOTOWE` i uruchom `install_web_launcher.bat`.
6. Po kliknięciu RUN sprawdź, czy launcher pokazuje wersję **6.3.1**.

**Ważne:** sam ZIP serwera nie zastępuje EXE już zainstalowanego w Windows.
Wyniki istniejących rajdów i punktacja Power Stage nie są zmieniane.
Błąd formatu `.sav` (`unexpected zone ... at 401`) jest osobnym problemem: poprawka importu go nie rozwiązuje.
