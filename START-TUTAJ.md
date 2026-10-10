# V6.3.1 — naprawa braku `acr_daily.settings` w EXE

Przed instalacją przeczytaj `README-V6.3.1-IMPORT-SETTINGS-PL.md`.

# Nowe w V6.3

Najpierw przeczytaj `README-V6.3-POWER-STAGE-I-SAV-PL.md`. Launcher nie steruje już menu gry. Power Stage domyślnie 5,4,3,2,1 pkt. **Po aktualizacji serwera zainstaluj nowy EXE V6.3**, bo stary zachowuje dawną logikę.

---

# ACR Rally Club V6.3 — pełna instalacja, nowy katalog

Jedno archiwum do postawienia serwera od zera. Rozpakuj do pustego katalogu.

## Co naprawiono w V6.3

- Poprawiony format binarnego kalendarza Rally Weekend zgodnie z ACR Daily: dzień przed każdym OS, tylko jeden znacznik końca po całym kalendarzu, 20-bajtowy ogon.
- Zapisy na rajd możliwe od jego opublikowania do czasu zamknięcia. **RUN RALLY dostępny dopiero od początku okna rajdu**; DNF i zasady jednej próby bez zmian.
- W panelach i harmonogramach pokazywany **stały czas UTC+2**, także dla użytkowników w innej strefie. W bazie i API czasy pozostają absolutne (UTC), aby zapobiegać błędom naliczania. UTC+2 nie jest automatycznie zmieniane na UTC+1 zimą.
- Administrator ma osobny, losowy adres, generowany przy pierwszym uruchomieniu w `server_local/admin_route.txt`. Jest wyświetlany w konsoli serwera, dostępny też przez `open_admin.bat` i `open_admin_seasons.bat`. Na publicznych stronach nie ma odnośników do panelu. **To dodatek do autoryzacji, nie jej zamiennik.**
- Jeśli launcher odmówi przygotowania zapisu przed pierwszym OS-em, serwer umożliwia ponowienie RUN bez czekania 5 minut; próba nie jest oznaczana jako DNF.

## Lokalnie

1. Zainstaluj Python 3.11+ i uruchom `start_local_server.bat`.
2. Otwórz `http://127.0.0.1:8790/`.
3. Panel administracyjny: uruchom `open_admin.bat` albo skopiuj prywatny adres wypisany w oknie serwera. Klucz pojawi się w `server_local/admin_key.txt`.
4. Po konfiguracji sezonu i rajdu kierowcy mogą rejestrować nick i zapisać się na wydarzenie przed startem.
5. Kiedy nadejdzie godzina rozpoczęcia, RUN odblokuje launcher.

**Ważne:** pełna paczka zawiera serwer i katalogi ACR Daily. Do zbudowania pliku EXE nadal potrzebny jest GitHub Actions lub komputer Windows z PyInstaller; skrypt `tools/vendor_acr_daily.py` pobiera i sprawdza oryginalne moduły launchera podczas budowania. To nie jest gotowy instalator EXE.

## Dla opiekuna strony

Przeczytaj `README-DLA-OPIEKUNA-STRONY-PL.md`. Ustaw domenę, `ADMIN_PANEL_PATH=/panel-...` (losowe 32+ znaki) i inne sekrety w `deploy/.env`; włącz Docker Compose i Caddy (HTTPS + dodatkowe hasło). Caddy chroni również prywatny adres panelu oraz `/api/admin/*`. **Nie publikuj** `.env`, `admin_key.txt`, `admin_route.txt` ani `club.sqlite3`.

## Przeniesienie danych ze starszej wersji

Zatrzymaj serwer, wykonaj kopię starej `server_local/club.sqlite3` i skopiuj bazę do nowego folderu `server_local/` zanim uruchomisz nowy serwer. **Nie kopiuj** starego, potencjalnie uszkodzonego `PlayerDataSaveSlot.sav` z gry. Klucz admina możesz zachować kopiując `admin_key.txt` prywatnie.

## Gdy pojawia się `unexpected zone in the Rally Weekend calendar`

Błąd poprzedniego kodu mógł pozostawić zapis w niepoprawnym formacie. V6.3 tworzy już poprawny kalendarz, ale **nie próbuje na siłę naprawić wcześniejszych, nieczytelnych plików**. Zamknij ACR i przywróć prawidłową kopię `.sav` z backupów launchera lub pozwól grze odtworzyć ustawienia w menu Rally Weekend. Dopiero potem uruchom ponownie RUN. Nie kasuj jedynego zapisu.

Źródło: ACR Daily, MIT (licencja `LICENSE`), przypięta rewizja w `tools/vendor_acr_daily.py`.
