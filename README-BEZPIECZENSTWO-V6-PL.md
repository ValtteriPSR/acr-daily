# Bezpieczeństwo V6 — wdrożone środki i ograniczenia

## Nowe środki techniczne

1. Serwer w trybie publicznym (`ACR_PUBLIC_BASE_URL`) wymaga domeny HTTPS, ustalonego `Host` i nagłówka `X-ACR-Gateway` z losowym sekretem. Reverse proxy (Caddy) dodaje nagłówek i **nie udostępnia portu 8790**. To ochrona warstwy wdrożeniowej, nie zamiennik fizycznego zabezpieczenia VPS.
2. Caddy wymaga hasła HTTP Basic dla prywatnego `ADMIN_PANEL_PATH`, jego podstron, `/api/admin` i `/api/admin/*`. Następnie sam ACR Rally Club wymaga swojego klucza administratora i sesji. To dwie niezależne bariery dostępu, ale nie 2FA. Ważniejsza od drugiego hasła jest jeszcze ochrona konta VPS/GitHub MFA i zabezpieczone kopie bazy.
3. Formularze sprawdzają CSRF oraz `Origin` dla publicznej domeny; odrzucone są żądania `cross-site`. Przeglądarkowy `Origin: null` jest dopuszczony tylko po pozytywnej kontroli CSRF i bez znacznika `Sec-Fetch-Site: cross-site` (zgodność z przeglądarkami prywatnościowymi). Cookie klubowe, administratora i CSRF ma flagę `Secure` w trybie publicznym; `HttpOnly` i `SameSite` były już w V5.
4. Bramka ogranicza liczbę prób rejestracji/recovery, RUN, redeem, logowania admina i zapisów nicków na minutę, reagując HTTP 429. To limity procesowe w pamięci — resetują się przy restarcie i nie zastępują zewnętrznego rate limitera/WAF.
5. Publiczny serwer wymaga konta klubowego dla zapisu do rajdu. Stare API anonimowego `/api/join` jest wyłączone w trybie publicznym. Nie uniemożliwia to zakładania kilku różnych kont przez tę samą osobę; nadal brakuje zweryfikowanej tożsamości.
6. Publiczne API startów wymaga minimalnej wersji launchera z nagłówka `X-ACR-Launcher-Version` (domyślnie `6.0.0`). Odrzuca starsze wersje kodem 426. **Nagłówek nie poświadcza autentyczności EXE** i może zostać sfałszowany.
7. Pozostały dotychczasowe zabezpieczenia: krótko ważny bilet RUN, jednorazowe użycie, zmiana tokenu przy redeem, pierwsza próba, heartbeat, trwałe DNF i porównanie konfiguracji Rally Weekend; oficjalny czas z `.sav` jest dodatkowo porównywany z timerem telemetrii. Dla niezaufanego klienta te dowody wciąż da się sfałszować.
8. `.gitignore` oraz `.dockerignore` zapobiegają *przypadkowemu* opublikowaniu kluczy, bazy SQLite i zapisów gry; nie cofają wycieku, jeśli plik był wcześniej śledzony i wypchnięty do repo.

## Czego nie ma — nie obiecuj pełnego antycheata

- EXE na komputerze gracza jest modyfikowalny; nagłówek wersji, hash, log i własna telemetria nie są kryptograficznym dowodem uczciwej gry. Nie ma tu poświadczenia sprzętowego ani serwerowej symulacji przejazdu.
- Serwer nie weryfikuje w sposób odporny na fałszowanie każdej próbki pozycji ani nie ma mechanizmu automatycznego zgłaszania wyniku do ręcznej weryfikacji. Przed sezonem z nagrodami zalecane są: podpisywanie EXE, serwerowe próbkowanie i spójność trajektorii, konta z MFA, ręczny audyt nierealistycznych czasów.
- `AdminAuth` przechowuje sesje w pamięci procesu. Restart serwera wyloguje administratorów (bez utraty bazy). Limit prób również resetuje się po restarcie.
- Baza SQLite jest przeznaczona do jednego procesu aplikacji i trwałego dysku. Nie uruchamiaj wielu instancji serwera bez projektu migracji i centralnego magazynu transakcyjnego.
- Auto-nawigacja ACR Daily opiera się na rozpoznawaniu ekranu i klawiszach z lokalnego zapisu gry; po zmianie UI/bindów może zatrzymać się lub wymagać ręcznego startu. Nie klika START STAGE i nie omija antycheata.

## Minimalna lista kontrolna organizatora przed otwarciem publicznej ligi

- [ ] Repozytorium wolne od danych prywatnych i z zachowaną licencją MIT.
- [ ] HTTPS działa, port 8790 niedostępny publicznie.
- [ ] prywatny `ADMIN_PANEL_PATH` i `/api/admin/*` chronione dwoma niezależnymi hasłami; MFA na GitHub/VPS.
- [ ] Backup bazy wykonał się i został odtworzony na maszynie testowej.
- [ ] GitHub Actions opublikował prawdziwy, dostępny EXE wraz z SHA256.
- [ ] Dwóch niezależnych kierowców przetestowało instalator, przycisk RUN, dwie próby na różnych OS-ach i wyniki z karami.
- [ ] Sprawdzono reakcję na DNF, utratę połączenia, restart i zmianę ustawień.
- [ ] Organizator ma plan ręcznej weryfikacji oszustw i zgłaszania błędów.
