# Wdrożenie Klubu AC Rally — krok po kroku

Kolejność ma znaczenie: każdy etap da się sprawdzić, zanim ruszy następny, a
do etapu 3 nic nie zmienia się na działającym serwerze.

| Etap | Co | Gdzie | Zmienia działającą stronę? |
|---|---|---|---|
| 0 | Dostępy | GitHub, Render, Neon, Hostido | nie |
| 1 | Sprawdzenie lokalne | VS Code | nie |
| 2 | Wysłanie gałęzi `projectsimracing` | VS Code → GitHub | nie (tylko testy) |
| 3 | Wdrożenie na serwer klubu | GitHub (Pull Request) → Render | **tak — między rajdami** |
| 4 | Wejście do panelu administratora | Render → przeglądarka | nie |
| 5 | Subdomena `acr.projectsimracing.pl` | Render + Hostido | tak (nowy adres) |
| 6 | Nowy launcher dla nowego adresu | GitHub Actions | tak (nowy instalator) |
| 7 | Klub AC Rally na projectsimracing.pl | repozytorium strony ligi | tak |
| 8 | Test live | — | — |

---

## Etap 0 — dostępy (raz)

Potrzebne konta i kto je ma:

- **GitHub, repozytorium `ValtteriPSR/acr-daily`** — kod klubu. Do wysłania
  gałęzi potrzebne jest prawo zapisu. Jeśli go nie masz, właściciel
  (ValtteriPSR) dodaje Cię w *Settings → Collaborators → Add people*.
  Bez tego: zrób *Fork* i Pull Request z forka (etap 3 wygląda tak samo).
- **Render**, workspace „Mateusz's workspace”, usługa `acr-rally-club` — serwer
  klubu i hasła administratora. Właściciel zaprasza w *Workspace Settings →
  Members*.
- **Neon**, baza `acr_club` — wyniki i konta (kopie zapasowe).
- **Hostido** — DNS domeny projectsimracing.pl (tam, gdzie kiedyś ustawialiście
  rekordy dla GitHub Pages).
- **Repozytorium strony ligi** (GitHub Pages) — to, do którego wgrywacie
  foldery „do-wgrania-…”.

Na każdym z tych kont włącz weryfikację dwuetapową (2FA). Kto ma dostęp do
GitHuba z prawem zapisu albo do Rendera, ten może zmienić działający serwer —
to ważniejsze niż sam klucz administratora.

---

## Etap 1 — sprawdzenie lokalne (VS Code)

1. Otwórz w VS Code folder `Strona/Program/acr-daily` (dokładnie ten folder).
2. Lewy pasek → *Run and Debug* (Ctrl+Shift+D) → z listy wybierz
   **„ACR demo + strona ligi”** → zielona strzałka. Uruchamiają się dwa
   programy naraz.
3. Sprawdź w przeglądarce:
   - http://127.0.0.1:8790/ — strona klubu w wyglądzie ligi, w menu
     „Klub AC Rally”, motyw jasny/ciemny, widok na telefonie (F12 → ikona
     telefonu),
   - http://127.0.0.1:8790/seasons — klasyfikacje,
   - http://localhost:8000/wyniki.html?champ=acr — Wasza strona wyników
     z zakładką Assetto Corsa Rally,
   - panel administratora: adres z konsoli (`PRYWATNY PANEL ADMIN: …`), klucz
     w `server_local/admin_key.txt`. To tylko lokalny klucz testowy.
4. *Run and Debug* → **„Testy”** → w konsoli na końcu ma być `OK`.
5. Zatrzymaj programy (czerwony kwadrat).

Pliki `admin_key.txt`, `admin_route.txt` i bazy `*.sqlite3` są wykluczone
z gita (`.gitignore`) — nie trafią na GitHub nawet przy „zatwierdź wszystko”.

---

## Etap 2 — wysłanie gałęzi na GitHub

Na tym etapie **nic nie zmienia się na serwerze**: Render wdraża tylko gałąź
`rally-club`, a ta zostaje bez zmian.

1. VS Code → lewy pasek → *Source Control* (Ctrl+Shift+G). Na dole paska stanu
   musi być gałąź **`projectsimracing`**.
2. Sprawdź listę plików: nie może być na niej `admin_key.txt`, `admin_route.txt`,
   `.env` ani `*.sqlite3`.
3. Wpisz opis, np. `Project Simracing: wygląd, wyniki na stronie ligi, zabezpieczenia`
   → **Commit** (jeśli VS Code zapyta o „stage all changes” — *Yes*).
4. **Publish Branch** (albo *Sync Changes*). Przy pierwszym razie VS Code
   poprosi o zalogowanie do GitHuba w przeglądarce.
5. Na GitHubie: repozytorium → zakładka **Actions** → przebieg *Server checks*
   dla gałęzi `projectsimracing`. Oba zadania (*sqlite* i *postgres*) muszą być
   zielone — to sprawdza zmiany także na bazie PostgreSQL, takiej jak na serwerze.

Jeśli Publish Branch zwraca błąd 403 / „Permission denied” — wróć do etapu 0
(dostęp do repozytorium).

---

## Etap 3 — wdrożenie na serwer klubu (między rajdami)

Nie wdrażaj w trakcie rajdu: restart przerywa aktywne przejazdy.

1. **Kopia bazy.** Neon → projekt → *Branches* → *Create branch* z `main`,
   nazwa np. `przed-projectsimracing`. To natychmiastowa kopia; w razie
   problemów można do niej wrócić.
2. GitHub → repozytorium → *Pull requests* → *New pull request*:
   **base: `rally-club`** ← **compare: `projectsimracing`** → *Create pull request*.
3. Poczekaj na zielone testy w PR → **Merge pull request** → *Confirm merge*.
4. Render → usługa `acr-rally-club` → *Events/Deploys*. Wdrożenie powinno ruszyć
   samo; jeśli nie — *Manual Deploy → Deploy latest commit*. Trwa kilka minut.
5. Sprawdź https://acr-rally-club.onrender.com/ — nowy wygląd, rajdy i wyniki
   z bazy są na miejscu, https://acr-rally-club.onrender.com/api/ps/wyniki
   zwraca dane. Nowe tabele w bazie tworzą się same; nic nie jest kasowane.

Wycofanie: Render → *Deploys* → poprzednie wdrożenie → *Rollback*. Baza nie
wymaga cofania (zmiany są tylko dodatkowymi tabelami).

---

## Etap 4 — wejście do panelu administratora

Adres panelu i hasła **nie są w kodzie ani na GitHubie** — są wpisane w Renderze.

1. Render → usługa `acr-rally-club` → zakładka **Environment**.
2. Odkryj (ikona oka) trzy wartości:
   - `ACR_ADMIN_PATH` — prywatna ścieżka panelu, zaczyna się od `/panel-`,
   - `ADMIN_HTTP_PASSWORD` — hasło okienka przeglądarki,
   - `ACR_ADMIN_KEY` — klucz aplikacji.
3. Otwórz adres klubu + ścieżkę, np. `https://acr-rally-club.onrender.com/panel-…`
   (po etapie 5: `https://acr.projectsimracing.pl/panel-…`).
4. Przeglądarka pokaże okienko logowania: użytkownik **`admin`**, hasło =
   `ADMIN_HTTP_PASSWORD`.
5. Na stronie panelu wpisz `ACR_ADMIN_KEY` → zaloguj. Panel sezonów jest pod
   tym samym adresem + `/seasons`.

Zasady:
- zapisz te trzy wartości w menedżerze haseł; nie wysyłaj ich na Discordzie,
- na publicznych stronach nie ma linku do panelu — to celowe,
- przy podejrzeniu wycieku zmień wartości w *Environment* → *Save* (Render
  wdroży usługę ponownie); stare hasła przestają działać.

---

## Etap 5 — subdomena acr.projectsimracing.pl

Strona ligi na GitHub Pages **nie jest ruszana** — dochodzi jeden nowy rekord.
Obecnie DNS domeny jest w Hostido (`ns1–ns3.hostido.net.pl`), główna domena
wskazuje na GitHub Pages (4 rekordy A `185.199.108–111.153`), a `www` jest
CNAME na `projectsimracing.pl`. To wszystko zostaje.

1. **Render** → usługa → *Settings* → *Custom Domains* → *Add Custom Domain* →
   `acr.projectsimracing.pl` → *Save*. Render pokaże, na co ustawić CNAME
   (`acr-rally-club.onrender.com`).
2. **Hostido** → zarządzanie domeną projectsimracing.pl → strefa DNS (to samo
   miejsce, w którym są rekordy A dla GitHuba) → *dodaj rekord*:

   | Nazwa / Host | Typ | Wartość / Cel | TTL |
   |---|---|---|---|
   | `acr` | CNAME | `acr-rally-club.onrender.com.` | domyślny |

   Nie zmieniaj serwerów DNS domeny, rekordów A dla samej domeny ani rekordu
   `www`. Nie dodawaj rekordu AAAA dla `acr`. Jeśli panel dopisuje domenę
   automatycznie, w polu nazwy wpisz samo `acr`.
3. Render → *Custom Domains* → *Verify*. Po kilku minutach (czasem do kilku
   godzin) pojawi się „Verified” i certyfikat HTTPS.
4. Render → *Environment* → dodaj / zmień i zapisz:

   | Zmienna | Wartość |
   |---|---|
   | `ACR_PUBLIC_BASE_URL` | `https://acr.projectsimracing.pl` |
   | `ACR_REDIRECT_HOSTS` | `acr-rally-club.onrender.com` |

   Po zapisaniu Render wdroży usługę ponownie.
5. Sprawdź:
   - https://acr.projectsimracing.pl/ — strona klubu z kłódką HTTPS,
   - https://acr-rally-club.onrender.com/ — przekierowuje na nowy adres,
   - logowanie przez Steam na nowym adresie (gracze logują się raz jeszcze;
     konta i wyniki zostają),
   - panel administratora pod `https://acr.projectsimracing.pl` + `ACR_ADMIN_PATH`.

Dzięki `ACR_REDIRECT_HOSTS` zainstalowane launchery (ze starym adresem) dalej
działają — przekierowywane są tylko strony w przeglądarce.

---

## Etap 6 — nowy launcher dla nowego adresu

1. GitHub → repozytorium → *Settings* → *Secrets and variables* → *Actions* →
   *Variables* → `ACR_CLUB_PUBLIC_URL` = `https://acr.projectsimracing.pl`
   (dla przyszłych automatycznych wydań).
2. *Actions* → **Publish Windows launcher** → *Run workflow*:
   - branch: `rally-club`,
   - public_url: `https://acr.projectsimracing.pl`,
   - release_tag: nowy, np. `v0.2.16-ps1` (nigdy nie nadpisuj starego).
3. Po zielonym przebiegu nowe wydanie jest w *Releases* jako najnowsze.
   Przycisk pobierania na stronie klubu zawsze prowadzi do najnowszego wydania,
   więc w Renderze nic nie trzeba zmieniać.
4. Ogłoś kierowcom: pobrać i zainstalować launcher jeszcze raz (najlepiej przed
   kolejnym rajdem).

---

## Etap 7 — Klub AC Rally na projectsimracing.pl

Dopiero gdy działa https://acr.projectsimracing.pl/api/ps/wyniki.

**Sposób A — gotowe pliki.** Folder `Strona/do-wgrania-acr` (jak Wasze
„do-wgrania-…”): GitHub → repozytorium strony → *Add file → Upload files* →
przeciągnij **zawartość** folderu (`assets`) → *Commit changes*. Pliki
powstały z wersji w `do-wyslania` z 5 października — jeśli ktoś od tego czasu
edytował `config.js` lub `zrodla.js` na GitHubie, użyj sposobu B.

**Sposób B — ręcznie w edytorze GitHuba** (ikona ołówka przy pliku):

`assets/js/zrodla.js`, w `sources`:
```js
acr: 'https://acr.projectsimracing.pl/api/ps/wyniki'
```

`assets/js/config.js`:
```js
// nav — nowa linia zaraz po pozycji „Wyniki”:
{ label: { pl: 'Klub AC Rally', en: 'AC Rally Club' }, href: 'https://acr.projectsimracing.pl/' },

// hub → „Pozostałe serie” — nowa linia przed „Assetto Corsa Rally” (FB):
{ label: { pl: 'Klub AC Rally — rajdy i zapisy', en: 'AC Rally Club — rallies' }, href: 'https://acr.projectsimracing.pl/', tag: 'ACR' },

// seriesLabel — po linii fh6 (dodaj przecinek na końcu linii fh6):
acr: { pl: 'Assetto Corsa Rally · Sezon 1', en: 'Assetto Corsa Rally · Season 1' }

// championships → id: 'acr' — zamień dwie linie:
season: { pl: 'Sezon 1', en: 'Season 1' },
sheetUrl: 'https://acr.projectsimracing.pl/seasons',
```

Po zapisaniu GitHub Pages przebuduje stronę (zakładka *Actions*, kilka minut).
Sprawdź https://projectsimracing.pl/wyniki.html?champ=acr i pozycję
„Klub AC Rally” w menu.

---

## Etap 8 — test live

- [ ] Kierowca testowy: logowanie Steam, nick, zapis na rajd testowy.
- [ ] Nowy launcher: RUN, dwa OS-y, wynik na stronie rajdu i w klasyfikacji.
- [ ] Pauza w trakcie OS-u — wynik przyjęty bez DNF.
- [ ] Stary launcher (sprzed etapu 6) nadal startuje rajd.
- [ ] `projectsimracing.pl/wyniki.html?champ=acr` pokazuje te same punkty
      co `acr.projectsimracing.pl/seasons`.
- [ ] Godziny rajdu po 25.10 (czas zimowy) zgadzają się z kalendarzem ligi.
- [ ] Panel administratora: zakładka Telemetria przy przejeździe testowym nie
      zgłasza ostrzeżeń „do weryfikacji”.

## Gdy coś pójdzie nie tak

| Objaw | Co zrobić |
|---|---|
| Publish Branch: 403 | brak prawa zapisu — etap 0 |
| Testy na GitHubie czerwone | nie scalaj PR; prześlij treść błędu z zakładki Actions |
| Strona klubu nie działa po wdrożeniu | Render → Deploys → *Rollback* |
| `acr.projectsimracing.pl` nie działa po godzinie | sprawdź rekord CNAME w Hostido (nazwa `acr`, cel `acr-rally-club.onrender.com`) |
| Strona ligi przestała działać | rekordy A / `www` w Hostido zostały zmienione — przywróć je |
| Na wyniki.html brak danych ACR | sprawdź adres w `zrodla.js` i czy `…/api/ps/wyniki` otwiera się w przeglądarce |
| Strona klubu długo się ładuje | darmowy Render usypia usługę po 15 min — pierwsze wejście ok. minuty |
