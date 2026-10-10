# GitHub — krok po kroku dla pierwszej publikacji ACR Rally Club V6.3

## Co publikujemy?

**Wyłącznie zawartość jednego ZIP `ACR-Rally-Club-V6.3-Pelna-Instalacja.zip`.** Nie trzeba forkować ACR Daily ani kopiować oryginalnego repozytorium. W kodzie są snapshoty katalogów gry, a workflow podczas kompilacji automatycznie pobiera 5 sprawdzanych plików z oryginalnego ACR Daily.

**UWAGA:** Nie publikuj `server_local/club.sqlite3`, `server_local/admin_key.txt`, `deploy/.env`, zapisów `.sav`, tokenów, logów ani plików z danymi prywatnymi. ZIP ich nie zawiera; `.gitignore` blokuje przypadkowe dodanie.

## 1. Utwórz repozytorium przez GitHub Desktop (najprostszy wariant)

1. Załóż konto na https://github.com i zainstaluj [GitHub Desktop](https://desktop.github.com/). Zaloguj się.
2. Rozpakuj cały ZIP do **osobnego, pustego folderu** `ACR-Rally-Club-V6.3`.
3. W GitHub Desktop wybierz **File → Add Local Repository → Choose** i wskaż rozpakowany folder. Jeśli zobaczysz komunikat o braku repozytorium, wybierz **create a repository here**.
4. Sprawdź listę plików: muszą być `server/src/cars.js`, `server/src/stages.js`, `server_local/`, `client/`, `deploy/`, `.github/workflows/launcher-release.yml`, `LICENSE`. Plików `club.sqlite3`, `admin_key.txt`, `deploy/.env` NIE WOLNO publikować.
5. Wpisz komentarz, np. `ACR Rally Club V6.3 standalone`, i wybierz **Commit to main**.
6. Kliknij **Publish repository**, podaj nazwę `acr-rally-club`, zdejmij zaznaczenie `Keep this code private` i potwierdź. Dopiero teraz GitHub Desktop utworzy publiczne repozytorium i wyśle pliki.

**Nie twórz wcześniej osobnego pustego repozytorium na stronie GitHuba**, jeśli używasz tych kroków — unikniesz konfliktu dwóch repozytoriów o tej samej nazwie.

### Alternatywa: terminal Git + repozytorium stworzone w przeglądarce

Jeśli wolisz terminal, najpierw na github.com kliknij **New repository**, nazwij `acr-rally-club`, ustaw `Public`, nie dodawaj README/licencji (są w ZIP). Potem:

```bash
cd /sciezka/do/ACR-Rally-Club-V6.3
git init
git branch -M main
git add .
git status
git commit -m "ACR Rally Club V6.3 standalone"
git remote add origin https://github.com/TWOJ_LOGIN/acr-rally-club.git
git push -u origin main
```

Przed wypchnięciem sprawdź `git status` i zachowaj lokalnie pliki z danymi, których `.gitignore` ma zabronić.

## 3. Wpisz adres publicznej ligi

Repozytorium GitHub → **Settings → Secrets and variables → Actions → Variables → New repository variable**:

| Name | Value |
|---|---|
| `ACR_CLUB_PUBLIC_URL` | `https://liga.twoja-domena.pl` |

Użyj dokładnej domeny z HTTPS, na której działa Docker. Bez ścieżki `/`, bez portu, bez `http://`. W skompilowanym launcherze ta domena zostaje zapisana przy wydaniu EXE.

## 4. Włącz Actions i wydaj EXE

1. GitHub → zakładka **Actions** i włącz workflows dla repozytorium, jeśli trzeba.
2. Sprawdź, czy `.github/workflows/launcher-release.yml` jest obecny na gałęzi głównej.
3. Wejdź w **Releases → Draft a new release**, wybierz utworzenie nowego tagu `v6.3.0` z gałęzi `main`, opisz wydanie i opublikuj.
4. GitHub Actions uruchomi testy na Linuxie, następnie Windows. Przed kompilacją na Windowsie `tools/vendor_acr_daily.py --download` pobiera 7 oryginalnych modułów ACR Daily **z przypiętego commita** i sprawdza ich SHA.
5. Po poprawnym buildzie w release pojawią się `ACR-Rally-Club-Setup.exe` i `ACR-Rally-Club-Setup.exe.sha256`.
6. Otwórz `https://github.com/TWOJ_LOGIN/acr-rally-club/releases/latest/download/ACR-Rally-Club-Setup.exe` — powinno pobrać EXE.
7. Pod adresem `https://liga.twoja-domena.pl/download` strona powinna przekierowywać do tego samego pliku. Zainstaluj EXE na **testowym Windows**, sprawdź rejestrację `acrclub://` i przejedź testowy rajd przed udostępnieniem go kierowcom.

Jeśli build nie przejdzie: Actions → uruchomiony workflow → zakładka `windows-installer` → krok, który zgłosił błąd. Nie podszywaj się pod gotowy instalator; **źródłowy ZIP nie zawiera EXE**. Do ręcznego wyzwalania działa także `Run workflow` w Actions, ale wtedy wynikiem może być tylko *artifact*, dopóki nie powstanie Release z tagiem `v*`.

## 5. Jak publikować kolejne wersje?

Po zmianie kodu zrób commit na `main`, a następnie nowy tag, np. `v6.3.1`. `releases/latest` automatycznie przekierowuje do najnowszej wersji. Przed wydaniem nowego EXE przetestuj zgodność z serwerem i ewentualne ustawienie `ACR_MIN_LAUNCHER_VERSION`.

## Autorstwo

ACR Rally Club wykorzystuje oryginalne moduły ACR Daily (Ngoc Khanh Nguyen, MIT License). **Nie usuwaj pliku `LICENSE`, informacji o autorze ani linku do repozytorium**: https://github.com/khanhonthetrack/acr-daily.
