# ACR Rally Club — hosting w internecie

Wersja klubowa oparta na [ACR Daily](https://github.com/khanhonthetrack/acr-daily).
Serwer i panel działają w chmurze. Gracz potrzebuje Assetto Corsa Rally na Windows
oraz gotowego klienta EXE pobranego ze strony klubu. Administrator obsługuje klub
w przeglądarce, bez instalowania serwera, Pythona, Dockera ani narzędzi Git.

## Wdrożenie darmowe

- **Render Free**: aplikacja Python i chroniący ją Caddy, publiczny HTTPS.
- **Neon Free**: trwała baza PostgreSQL z kontami, rajdami, sezonami i wynikami.
- **GitHub Actions**: testy serwera, kompilacja klienta na Windows i publikacja EXE.

Instrukcja użytkowania i wdrożenia: [PORADNIK-INTERNET-PL.md](PORADNIK-INTERNET-PL.md).

Render usypia bezczynny serwis po około 15 minutach; pierwsze wejście po przerwie
może wymagać około minuty oczekiwania. Dane pozostają w Neon. Darmowe plany mają
limity i nie zapewniają gwarantowanej dostępności. Baza SQLite na lokalnym dysku
Render nie służy do przechowywania danych klubu.

## Pliki wdrożenia

- `render.yaml`: konfiguracja usługi Free we Frankfurcie.
- `deploy/Dockerfile.render`, `deploy/Caddyfile.render`, `deploy/run_render.py`:
  aplikacja i jej brama z dodatkowym hasłem administratora.
- `server_local/database.py`: obsługa PostgreSQL i zgodność dotychczasowej SQLite.
- `.github/workflows/server-checks.yml`: testy SQLite i PostgreSQL.
- `.github/workflows/launcher-release.yml`: budowanie i wydawanie Windows EXE.

## Autorstwo

Oryginalny ACR Daily: copyright 2026 Ngoc Khanh Nguyen, licencja MIT.
Zachowano plik [LICENSE](LICENSE). Moduły gry do launchera pobierane są podczas
budowania z przypiętej rewizji i sprawdzane względem ich oczekiwanych sum.
