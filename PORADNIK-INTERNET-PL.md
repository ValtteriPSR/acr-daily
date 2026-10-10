# ACR Rally Club — poradnik uruchomienia i użytkowania

## Stan tej paczki

To wersja przygotowana do wdrożenia na Render + Neon. Samo pobranie archiwum nie
publikuje strony. Gotowy EXE powstanie dopiero po poprawnym zakończeniu wydania
na GitHub Actions. Po wdrożeniu tę instrukcję należy uzupełnić rzeczywistym
adresem strony i prywatnego panelu.

Repozytorium: https://github.com/ValtteriPSR/acr-daily
Gałąź aplikacji i wdrożenia: `rally-club`. To prawdziwy fork ACR Daily.

## Co uruchamia administrator

Otwiera stronę klubu albo prywatny adres panelu w przeglądarce. Nie uruchamia
żadnego serwera na swoim komputerze. Usługa Render i baza Neon pracują w chmurze.

Panel ma dwa zabezpieczenia:

1. Okno logowania przeglądarki: użytkownik `admin` oraz hasło przechowywane
   w zmiennej `ADMIN_HTTP_PASSWORD` w ustawieniach usługi Render.
2. Ekran logowania panelu: klucz przechowywany w zmiennej `ACR_ADMIN_KEY`.

Prywatna ścieżka panelu znajduje się w zmiennej `ACR_ADMIN_PATH`. Zmienne można
odczytać po zalogowaniu do Render w zakładce Environment usługi. Nie umieszczaj
ich w repozytorium, wiadomościach publicznych ani plikach klienta.

Po wejściu do panelu administrator tworzy sezon i rajd, ustawia samochody,
odcinki, warunki oraz termin rozpoczęcia i zakończenia. Następnie publikuje rajd.
Kierowcy mogą zapisać się przed startem; przycisk RUN jest dostępny w oknie rajdu.

Terminy tej wersji są pokazywane w stałym UTC+2. Zimą różni się ono od czasu
polskiego o godzinę. Sprawdź podany czas przed ogłoszeniem wydarzenia.

## Co uruchamia gracz

1. Otwiera stronę klubu i wybiera pobranie klienta.
2. Pobiera już skompilowany `ACR-Rally-Club-Setup.exe` — nie potrzebuje Pythona.
3. Uruchamia EXE, aby zarejestrować obsługę linków `acrclub://`.
4. Rejestruje swój nick na stronie. Zachowuje prywatny kod odzyskiwania konta.
5. Zapisuje się na rajd. Zamyka Assetto Corsa Rally przed kliknięciem RUN.
6. W oknie rajdu klika RUN i potwierdza uruchomienie klienta przez przeglądarkę.
7. Klient przygotowuje Rally Weekend i uruchamia grę przez Steam.
8. W grze wybiera Racing → Rally → Rally Weekend → START RALLY → START STAGE.
9. Pozostawia klienta otwartego przez cały przejazd i zapis wyników w grze.

Klient odczytuje telemetrię i lokalny zapis gry. Dlatego do samej jazdy potrzebne
są lokalna gra i ten EXE. Panel, zapisy, sezony i wyniki obsługiwane są przez WWW.
Przeglądarka nie zastępuje programu odczytującego dane z gry.

## Jak agent wdraża projekt

1. Tworzy prawdziwy fork `khanhonthetrack/acr-daily` na koncie właściciela,
   zachowując powiązanie z oryginałem i licencję MIT.
2. Umieszcza tę wersję klubową w oddzielnej gałęzi forka. Render korzysta właśnie
   z tej gałęzi; oryginalny kod pozostaje dostępny w historii Git.
3. Tworzy projekt Neon w planie Free i pobiera połączenie do bazy.
4. Uruchamia testy SQLite i PostgreSQL na GitHub Actions.
5. Tworzy usługę Render w planie Free, we wskazanym przez właściciela workspace,
   z plikiem `deploy/Dockerfile.render` i kontekstem repozytorium `.`.
6. Ustawia `DATABASE_URL`, `ACR_ADMIN_KEY`, `ACR_ADMIN_PATH`,
   `ACR_GATEWAY_SECRET`, `ADMIN_HTTP_PASSWORD`, `ACR_LAUNCHER_DOWNLOAD_URL`
   oraz `ACR_MIN_LAUNCHER_VERSION=6.3.1` jako zmienne usługi.
7. Render nadaje adres HTTPS; `RENDER_EXTERNAL_URL` jest wykorzystany przez
   aplikację automatycznie. Agent sprawdza stronę i `/healthz`.
8. Uruchamia workflow Publish Windows launcher, podając rzeczywisty adres HTTPS
   jako `public_url` i nowy tag wydania jako `release_tag`.
9. Sprawdza zakończenie budowania, test zamrożonego EXE i pliki Release:
   `ACR-Rally-Club-Setup.exe` oraz jego sumę SHA256.
10. Ustawia pobieranie klienta na stronie i sprawdza rejestrację gracza oraz panel.

Właściciel wykonuje wyłącznie wymagane logowanie, zgodę na połączenie kont
i wskazanie workspace. Nie należy udostępniać agentowi haseł ani kodów 2FA w czacie.

## Codzienne działanie

Po przerwie strona może budzić usługę Render przez około minutę. Poczekaj,
następnie odśwież stronę. Wyniki i konta są zapisane w Neon i nie znikają po
uśpieniu serwera. Ponowne logowanie administratora po restarcie jest normalne.
Nie uruchamiaj dodatkowego serwera na komputerze ani równoległej instancji
klubu z tą samą bazą.

Aktualizacja kodu na gałęzi wdrożenia uruchamia automatyczne wdrożenie Render.
Nie publikuj aktualizacji w trakcie rajdu: restart może przerwać aktywne próby.
Zmiana klienta wymaga osobnego wydania EXE i sprawdzenia na Windows.

Pilnuj limitów obu planów Free. Nie włączaj płatnych planów bez świadomej
decyzji. Do ligi wymagającej stałej dostępności potrzebny może być później
płatny serwer. Okno przywracania Neon Free jest krótkie; zachowuj prywatne kopie
bazy przed ważnymi zmianami i aktualizacjami.
