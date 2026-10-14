# ACR Rally Club × Project Simracing

Gałąź `projectsimracing` w tym repozytorium to wersja 0.2.16 klubu ACR
dostosowana do ligi **projectsimracing.pl**: ten sam wygląd co strona ligi,
wyniki widoczne na `wyniki.html`, czas polski i dodatkowe zabezpieczenia
serwera. Launcher (EXE) nie był zmieniany — wszystkie zmiany są po stronie
serwera i strony WWW.

## 1. Uruchomienie lokalne (VS Code)

Wymagany Python 3.11 lub nowszy (zalecany 3.13). Dla lokalnej bazy SQLite nie
trzeba instalować żadnych pakietów.

1. Otwórz w VS Code folder `acr-daily`.
2. Zakładka **Run and Debug** (Ctrl+Shift+D) → wybierz konfigurację:
   - **ACR: demo (sezon, rajdy, wyniki)** — tworzy bazę pokazową
     `server_local/demo.sqlite3` (12 zmyślonych kierowców, 2 zakończone rajdy,
     1 trwający, 1 zapowiedziany) i uruchamia serwer na http://127.0.0.1:8790/.
     Baza demo jest tworzona od nowa przy każdym starcie tej konfiguracji.
   - **ACR: serwer (prawdziwa lokalna baza)** — `server_local/club.sqlite3`,
     zaczyna pustą.
   - **Strona ligi: podgląd z wynikami ACR** — serwuje Twój folder
     `Strona/do-wyslania` na http://localhost:8000 i *w locie* dopina ACR
     (pliki strony nie są zmieniane). Uruchom razem z serwerem ACR, potem
     otwórz http://localhost:8000/wyniki.html?champ=acr.
   - **Testy** — wszystkie testy automatyczne.
3. Panel administratora: prywatny adres wypisuje konsola serwera
   (`PRYWATNY PANEL ADMIN: ...`), klucz jest w `server_local/admin_key.txt`.

Bez VS Code, w terminalu w folderze `acr-daily`:

```sh
python3 tools/demo_ps.py                                    # baza pokazowa
python3 server_local/server.py --db server_local/demo.sqlite3
python3 tools/podglad_strony_ps.py --site ../../do-wyslania  # drugi terminal
python3 -m unittest discover -s tests -q
```

Logowanie przez Steam działa także lokalnie (serwer musi mieć internet, żeby
potwierdzić logowanie w Steam). Gry nie trzeba mieć do sprawdzania stron —
przejazd z launcherem sprawdza się dopiero na teście live.

## 2. Co zmieniono

**Wygląd (`server_local/site_theme.py`)**
- Kroje, kolory, skośne przyciski, tabele i stopka jak na projectsimracing.pl;
  pliki czcionek i logo w `server_local/static/ps/` (serwowane z tego samego
  serwera, bez Google Fonts).
- Pasek górny = menu strony ligi (Odnośniki, Wyniki, **Klub AC Rally**, Kalendarz,
  Artykuły, Regulamin, Media — „Klub AC Rally” zaznaczony), PL/EN, motyw jasny/ciemny (pamiętany tak jak na
  stronie ligi), Discord. Pod nim pasek serii ACR z nawigacją klubu.
- Menu mobilne (hamburger) z obiema grupami linków. Panel administratora
  zostaje w ciemnym motywie.

**Treść**
- Nazwy aut, odcinków i lokalizacji zamiast identyfikatorów gry
  (`HyundaiI20NRally2` → „Hyundai i20 N Rally2”, `Wales` → „Walia”).
- **Czas polski** zamiast stałego UTC+2 — także w panelu administratora przy
  wpisywaniu terminów. Od 25.10 (czas zimowy) godziny zgadzają się ze stroną
  ligi. W bazie i API czasy nadal są w UTC.
- Kolejność w trwającym rajdzie: meta → w trakcie (wg liczby OS-ów i czasu) →
  zapisani → DNF. Wcześniej kierowcy w trakcie byli ułożeni alfabetycznie.
- Strona 404 w wyglądzie ligi.

**Integracja**
- `GET /api/ps/wyniki` — klasyfikacje w formacie arkuszy, który czyta
  `wyniki.html` (zakładki: generalna, zespoły, każdy rajd). `?meta=1` dla
  odświeżania, `?season=<id>` dla innego sezonu.
- `GET /api/ps/kalendarz` — lista rajdów (runda, daty, nazwa zakładki wyników).
- Odczyt z innej domeny dozwolony tylko dla `https://projectsimracing.pl`
  (i `www.`); lokalnie także `localhost:8000`. Zmiana: `ACR_CORS_ORIGINS`.
  Adres strony ligi w menu: `ACR_PS_SITE_URL` (domyślnie projectsimracing.pl).
- `ACR_REDIRECT_HOSTS` — poprzednie adresy klubu (np. onrender.com) przekierowywane
  na nową domenę; API dla starszych launcherów działa dalej.

Krok po kroku: [WDROZENIE.md](WDROZENIE.md).

**Bezpieczeństwo (`server_local/timing_guard.py`)**
- Serwer zapisuje własny czas STARTU każdego OS-u. Czas OS-u zgłoszony przez
  launcher nie może być dłuższy od czasu, który faktycznie upłynął do METY
  (tolerancja 30 s → inaczej DNF; 10–30 s → oznaczenie „do weryfikacji”
  w sekcji Telemetria). Spreparowany przejazd wysłany bez jazdy jest teraz
  odrzucany. Pauzy w grze nadal są dozwolone.
- Oficjalny wynik z pliku `.sav` musi pochodzić z tego podejścia (znacznik
  startu nie starszy niż START OS-u na serwerze, margines 15 min na zegar
  komputera). Blokuje podstawienie wcześniejszego, treningowego przejazdu.
- Nicki tylko z liter łacińskich (z polskimi znakami), cyfr, spacji, `_`, `-`
  — blokuje podszywanie się nickiem z cyrylicą/greką. Istniejące nicki zostają.

Testy: `tests/test_projectsimracing.py` (13 nowych), wszystkie 261 przechodzą.
Pięć starszych plików testów symuluje przejazdy „natychmiastowe”, więc mają
na górze wyłączenie limitów `timing_guard` z komentarzem.

## 3. Podpięcie do projectsimracing.pl

Strona ligi nie wymaga zmian w kodzie — tylko w plikach ustawień.

**`assets/js/zrodla.js`** — adres wyników:

```js
acr: 'https://acr.projectsimracing.pl/api/ps/wyniki'
```

**`assets/js/config.js`** — proponowane wpisy (dokładnie to pokazuje podgląd):

```js
// 1. nav — po „Wyniki”:
{ label: { pl: 'Klub AC Rally', en: 'AC Rally Club' }, href: 'https://acr.projectsimracing.pl/' },

// 4. hub → „Pozostałe serie” — przed linkiem do grupy FB:
{ label: { pl: 'Klub AC Rally — rajdy i zapisy', en: 'AC Rally Club — rallies' },
  href: 'https://acr.projectsimracing.pl/', tag: 'ACR' },

// 7. championships → acr:
season: { pl: 'Sezon 1', en: 'Season 1' },
sheetUrl: 'https://acr.projectsimracing.pl/seasons',

// seriesLabel:
acr: { pl: 'Assetto Corsa Rally · Sezon 1', en: 'Assetto Corsa Rally · Season 1' }
```

Opcjonalnie:
- **Zdjęcia na podium** — `podiumPhotos.acr.auta` jak dla WRC (np.
  `'skoda fabia'`, `'hyundai i20'`, `'polo'`); pliki `acr-*-800.webp` /
  `-1400.webp` w `assets/img/podium/`. Bez tego podium ACR jest bez zdjęć.
- **Kalendarz** — sekcja `## Assetto Corsa Rally · Sezon 1 {acr}` w
  `tresci/kalendarz.md`; kolumna „Wyniki” = nazwa zakładki z API, np.
  `1. Rajd Grecji`. Te same dane podaje `/api/ps/kalendarz`, więc można je
  później pobierać automatycznie w `narzedzia/buduj.py`.
- **Slajd ACR** w `slides` z przyciskiem „Zapisz się” → subdomena.

## 4. Domena i hosting

**Nowej domeny nie trzeba kupować.** Wystarczy subdomena istniejącej, np.
`acr.projectsimracing.pl` — to jeden rekord DNS u rejestratora
projectsimracing.pl. GitHub Pages (obecna strona) nie uruchomi serwera Python,
więc subdomena musi wskazywać na serwer z aplikacją:

- **Render (obecnie `acr-rally-club.onrender.com`)** — w ustawieniach usługi
  *Custom Domains* dodać `acr.projectsimracing.pl`, u rejestratora rekord
  `CNAME acr → acr-rally-club.onrender.com` (bez rekordu AAAA). Render sam
  wystawia HTTPS. Plan Hobby obejmuje 2 domeny własne. Potem ustawić
  `ACR_PUBLIC_BASE_URL=https://acr.projectsimracing.pl`.
- **Własny VPS** — `docs/HOSTING.md`, rekord `A acr → IP serwera`.

Przy zmianie adresu ustaw też `ACR_REDIRECT_HOSTS=acr-rally-club.onrender.com`:
przeglądarki ze starego adresu trafią na nową domenę, a launchery zbudowane
dla starego adresu dalej będą działać. Mimo to trzeba zbudować
nowy launcher dla `https://acr.projectsimracing.pl` (Actions → Publish Windows
launcher, `docs/HOSTING.md` → „Build the launcher for the new domain”) i
poprosić kierowców o reinstalację — najlepiej między rajdami.

## 5. Czego kod nadal nie rozwiąże

Launcher działa na komputerze gracza, więc zmodyfikowany klient wciąż może
podać zmyślony, ale „cierpliwy” przejazd (odczekany w czasie rzeczywistym).
Serwer wyłapuje teraz przejazdy natychmiastowe i podmienione wyniki z `.sav`,
a brak śladów telemetrii widać w sekcji Telemetria. Przed sezonem z nagrodami:
przegląd telemetrii czołówki po każdym rajdzie, replay/nagranie dla podium,
kary administratora (już są w panelu) jako narzędzie sędziowskie.

## 6. Lista kontrolna testu live

- [ ] Strona i panel na `https://acr.projectsimracing.pl`, `/healthz` = ok.
- [ ] Logowanie Steam, wybór nicku, zapis na rajd testowy.
- [ ] Nowy launcher z adresem subdomeny, RUN, dwa OS-y, wynik na stronie.
- [ ] Kierowca z pauzą w trakcie OS-u — wynik przyjęty, bez DNF.
- [ ] `wyniki.html?champ=acr` na projectsimracing.pl pokazuje klasyfikację.
- [ ] Godziny rajdu po 25.10 zgadzają się z kalendarzem ligi.
