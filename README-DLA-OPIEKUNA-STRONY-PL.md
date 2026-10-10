# Dla opiekuna strony — wdrożenie ACR Rally Club V6.3 z JEDNEGO ZIP

## Cel i wymagania

Działa na osobnym Linux VPS (zalecane Ubuntu LTS, Docker Engine + Compose, publiczne IP, DNS i otwarte porty 80/443). Hosting statycznego HTML/PHP bez procesów backendowych nie wystarcza: aplikacja potrzebuje Pythona, bazy SQLite i połączeń z launcherami kierowców. Dotychczasowa strona klubu może pozostać bez zmian; wystarczy link do subdomeny, np. `liga.mojklub.pl`.

**Nie pobieraj oryginalnego ACR Daily.** Wszystkie pliki WWW, moduły serwera i katalogi (18 aut / 44 OS-y) są już dołączone. Przy wydawaniu EXE GitHub Actions samo pobierze sprawdzone wersje modułów klienta z publicznego ACR Daily.

## A. Rozpakowanie i konfiguracja

1. Skopiuj **jeden** ZIP `ACR-Rally-Club-V6.3-Pelna-Instalacja.zip` na VPS i rozpakuj do `~/acr-rally-club` — bez katalogu `acr-daily-main`.
2. Uruchom `python3 tools/preflight.py --server`. Oczekuj 18 aut, 44 OS-ów i `PREFLIGHT OK`.
3. W panelu DNS ustaw rekord A/AAAA np. `liga.mojklub.pl` → adres VPS.
4. Na VPS włącz firewall: TCP 80, TCP 443 i SSH (najlepiej ograniczony); **nie** publikuj portu 8790.

```bash
cd ~/acr-rally-club/deploy
cp .env.example .env
mkdir -p data
chmod 700 data
```

Edytuj `deploy/.env` (nie dodawaj do publicznego GitHuba):

```dotenv
CLUB_DOMAIN=liga.mojklub.pl
GITHUB_REPOSITORY=LOGIN_GITHUB/acr-rally-club
ACR_GATEWAY_SECRET=TU_64_LOSOWE_ZNAKI_HEX
ADMIN_PASSWORD_HASH='TU_HASH_BCRYPT_CADDY'
ADMIN_PANEL_PATH=/panel-LOSOWY_PRYWATNY_ADRES_MIN_24_ZNAKI
```

Wygeneruj sekret bramy: `python3 -c 'import secrets; print(secrets.token_hex(32))'`.

Wygeneruj hash osobnego hasła administratora poleceniem: `docker run --rm -it caddy:2.9 caddy hash-password` i wklej cały hash do `.env`, **w pojedynczym apostrofie** (ochrona znaków `$` w Docker Compose). Nie używaj swojego hasła w komendzie widocznej w historii powłoki.

## B. Start Docker i HTTPS

```bash
cd ~/acr-rally-club/deploy
docker compose config -q
docker compose up -d --build
docker compose ps
docker compose logs --tail=80 app caddy
```

Caddy sam wystawi HTTPS. Sprawdź:

| Adres | Funkcja |
|---|---|
| `https://liga.mojklub.pl/` | Strona ligi |
| `https://liga.mojklub.pl/guide` | Dokładny poradnik kierowcy |
| `https://liga.mojklub.pl/club` | Rejestracja klubowa |
| `https://liga.mojklub.pl/seasons` | Klasyfikacje |
| `https://liga.mojklub.pl` + `ADMIN_PANEL_PATH` | Rajdy: hasło HTTP Basic, potem klucz ACR |
| `https://liga.mojklub.pl` + `ADMIN_PANEL_PATH` + `/seasons` | Sezony, punktacja, dywizje i teamy |
| `https://liga.mojklub.pl/download` | Instalator po opublikowaniu GitHub Release |

Pobierz *prywatnie* klucz administracyjny serwera: `docker compose exec -T app cat /data/admin_key.txt`. Nie przesyłaj klucza przez Discord ani nie publikuj w repozytorium. Przy pierwszym starcie serwer sam wytworzy klucz i plik SQLite na zamontowanym dysku `deploy/data/`.

Serwer Python **nie ma** opublikowanego portu: Caddy prowadzi ruch przez wewnętrzną sieć Compose i dodaje sekret bramy. Oba hasła administratora muszą zostać zachowane i zabezpieczone. Panel nie zapewnia jeszcze MFA.

## C. EXE i GitHub

Publikację omówiono szczegółowo w `README-GITHUB-DLA-POCZATKUJACYCH-PL.md`. Do repozytorium trafia **zawartość tego samego ZIP**, a nie inny fork. Po ustawieniu zmiennej `ACR_CLUB_PUBLIC_URL=https://liga.mojklub.pl` w repozytorium i utworzeniu tagu `v6.3.0`, GitHub Actions:

- pobierze automatycznie pięć brakujących modułów ACR Daily (pinned Git commit; walidacja Git SHA),
- wygeneruje katalog `client/club_local/catalog.json`,
- zbuduje Windows instalator EXE,
- opublikuje plik w Releases z sumą SHA256.

Link do pobrania ze strony będzie aktywny **dopiero po pomyślnym Release**. Wcześniej serwer i panel mogą już działać, ale nie ogłaszaj kierowcom startu.

## D. Migracja poprzednich sezonów i wyników

1. Zatrzymaj stary serwer lokalny (`Ctrl+C`) i nowy Docker (`docker compose down` jeśli już uruchomiony).
2. Wykonaj kopię obu katalogów danych.
3. Przenieś **po SFTP/SSH**, poza repozytorium, `server_local/club.sqlite3` ze starego Windows do `~/acr-rally-club/deploy/data/club.sqlite3` na VPS. Przy otwartej bazie z WAL użyj `sqlite3.Connection.backup()` zamiast kopiowania otwartego pliku.
4. Opcjonalnie skopiuj `admin_key.txt` do `deploy/data/`, albo wykorzystaj nowy klucz z VPS.
5. `docker compose up -d --build`; zweryfikuj rajdy, sezony, konto i wyniki. Nie uruchamiaj dwóch serwerów jednocześnie na tej samej bazie.

Nie zamieszczaj `.sav`, bazy ani plików administracyjnych w żadnym publicznym ZIP.

## E. Aktualizacje i utrzymanie

- Codziennie rób spójny backup SQLite przez `docker compose exec -T app python tools/backup_club_db.py --db /data/club.sqlite3 --output /data/backups` i **kopiuj go poza VPS**; okresowo testuj przywracanie.
- Aktualizuj kontenery po wykonaniu kopii bazy. Nie nadpisuj `deploy/data` ani `deploy/.env` nowymi plikami kodu.
- Aktualizacje katalogów ACR Daily nie są automatycznie publikowane, aby nowe ID nie zmieniły niejawnie otwartych rajdów. `python3 tools/update_acr_catalogs.py --check` pokaże propozycje, `--apply` wymaga decyzji organizatora.
- W razie zmian w grze przetestuj od nowa oryginalne moduły ACR Daily, nawigację menu i parser zapisu z rzeczywistym ACR.
- EXE nie jest podpisany certyfikatem; Windows może pokazać SmartScreen. Nie zalecaj wyłączania antywirusa.
- Zabezpieczenia nie gwarantują odporności na zaawansowaną modyfikację klienta; przed ligą z nagrodami wprowadź dodatkową weryfikację wyników.

## F. Jak testować instalację na pustym katalogu

```bash
python3 tools/preflight.py --server
python3 -m unittest discover -s tests -q
python3 server_local/server.py --host 127.0.0.1 --port 8790
```

Odwiedź `http://127.0.0.1:8790/`; panel admina ma osobną ścieżkę pokazywaną w konsoli serwera i w `server_local/admin_route.txt`. Nie włączaj tego portu publicznie; na VPS korzystaj z kontenerów i HTTPS.

## Autorstwo

Katalogi i moduły klienta pochodzą z ACR Daily, copyright 2026 Ngoc Khanh Nguyen, licencja MIT (plik `LICENSE`). Źródło: https://github.com/khanhonthetrack/acr-daily, przypięty commit `135466d177e47039e0a8b6a6af2716379554c9e9`.

## V6.3 — adres panelu i czas

W `deploy/.env` dopisz `ADMIN_PANEL_PATH=/panel-` połączone z co najmniej 24 losowymi znakami `a-z0-9`. Na VPS strona panelu to `https://TWOJA-DOMENA` + `ADMIN_PANEL_PATH` (oraz `/seasons`). Caddy wymaga dodatkowego hasła przed przepuszczeniem do API. Publiczna strona nie podaje ścieżki panelu. Przekazuj ją wyłącznie organizatorom. Dodatkowo obowiązuje klucz z `/data/admin_key.txt`.

Panel przyjmuje i pokazuje terminy jako *stałe UTC+2*, bez sezonowej zmiany czasu. Dla wydarzeń z datami w październiku po zmianie czasu oznacza to inną godzinę niż aktualny czas polski (UTC+1). Warto o tym uprzedzić uczestników.
