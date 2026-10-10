# ACR Rally Club V3.1 — automatyczne ID, ochrona panelu i synchronizacja katalogów

Ta paczka jest aktualizacją V3. Zawiera **wszystkie pliki V3 + poprawki**;
rozpakuj jej zawartość do głównego folderu `acr-daily-main`, nadpisując pliki.

**Przed aktualizacją:** zamknij serwer i klienta. Skopiuj `server_local/club.sqlite3`
oraz `server_local/admin_key.txt` w bezpieczne miejsce, nie wysyłaj ich nikomu.

## 1. Automatyczne ID

W panelu `/admin` przy tworzeniu nowego rajdu **nie wpisujesz już ID**.
Serwer nada unikalny ID, np. `rally-20261009-a5d48c2e`, i zapisze go w bazie.
Istniejące rajdy oraz ich ID pozostają bez zmian. Przy edycji ID jest tylko do odczytu.
Import JSON ze starszym ID nadal działa przez `import_event.bat`.

## 2. Bezpieczeństwo lokalnego panelu

- Panel i `/api/admin/...` są dostępne wyłącznie przez **lokalne połączenie TCP**,
  także gdy port 8790 zostanie omyłkowo otwarty w LAN. To zabezpieczenie połączenia
  bezpośredniego; reverse proxy na tym samym komputerze wymaga osobnej konfiguracji.
- Pięć nieudanych logowań z tego samego adresu blokuje dalsze próby na 15 minut.
- Sesja administratora wygasa po 2 godzinach zamiast po 8.
- Operacje tworzenia, edycji, usuwania i logowania dopisywane są do tabeli SQLite
  `admin_audit`, a edycje zawierają stan `before` i `after` do audytu i przywracania.
- Klucz w `admin_key.txt` jest nadal losowy i ma wysoki poziom entropii.
- `rotate_admin_key.bat` wymienia klucz. **Najpierw zamknij serwer**; po rotacji
  uruchom go ponownie, żeby stare sesje przestały działać.

Jeśli ktoś przejmie klucz na działającej publicznej instancji, sam klucz nie daje
wystarczającego bezpieczeństwa. Przed wystawieniem Internetowi potrzebujemy osobnego
panelu za HTTPS, 2FA/passkey, autoryzacji administratorów, kopii poza serwerem
oraz nieedytowalnego dziennika zmian. Nie wystawiaj portu 8790 publicznie.

## 3. Skąd samochody i OS-y?

Panel korzysta ze **statycznych katalogów ACR Daily**:

- `server/src/cars.js` — ID samochodu, nazwa, telemetria, klasa,
- `server/src/stages.js` — ID OS-u i nazwa w menu.

Oryginalny autor projektu odtworzył je z tabel gry ACR. Nie są one automatycznie
zaktualizowane w chwili wydania łatki do gry. Dopiero aktualizacja ACR Daily lub
osobny odczyt danych instalacji ACR dostarczy nowe ID.

Nowe skrypty:

- `check_catalog_updates.bat` — porównuje lokalne pliki z aktualnymi katalogami
  ACR Daily na GitHubie, **NICZEGO NIE ZMIENIA**.
- `update_acr_catalogs.bat` — po Twojej zgodzie wykonuje aktualizację; robi kopie
  starych katalogów w `server/src/.catalog-backups/`.

Mechanizm odrzuca podejrzane aktualizacje usuwające znane ID. Istniejące rajdy
pozostają nienaruszone, ponieważ ich konfiguracja jest zapisana osobno w bazie.

Po aktualizacji dodającej nowe samochody koniecznie przebuduj klienta przez
`build_player_exe.bat`. Rozpoczętych rajdów nie modyfikuj.

Możesz uruchamiać `check_catalog_updates.bat` okresowo przez Harmonogram zadań
Windows (np. co tydzień), ale **nie automatyzuj bez nadzoru kroku --apply**.

## 4. Uczciwość wyników / antycheat

Klient EXE pod kontrolą użytkownika nigdy nie będzie niezawodnym źródłem prawdy.
Może zostać zmodyfikowany tak, aby raportował nieprawdziwe ustawienia, czas lub
brak restartu. Sam hash EXE albo podpis konfiguracji nie rozwiązuje tego problemu.

Proponowane etapy przed publicznymi zawodami:

1. Serwerowy protokół każdego START-u i heartbeat z rosnącym licznikiem i
   krótkotrwałymi wyzwaniami (nonce); DNF po przerwaniu kontaktu.
2. Wysyłanie surowych próbek telemetrii w trakcie OS-u i kontrola spójności
   czasu, kolejności, trasy i prędkości; przy odchyleniach `review`, nie od razu DNF.
3. Serwerowe wyliczanie sumy i kar na podstawie danych ACR wraz z dowodami
   pochodzenia / spójności (same raporty klienta mogą być fałszowane).
4. Ścisłe związanie jednej rejestracji z trwałą tożsamością (unikalny nick NIE
   rozwiązuje problemu wielu kont; Steam login lub inne sprawdzone konto).
5. Opcjonalnie weryfikacja kodu podpisem wydawcy, zabezpieczenie przed
   nieautoryzowaną modyfikacją procesu oraz raporty do analizy — tylko jako
   utrudnienie, nie główne źródło prawdy.

Wykrywanie modyfikacji klienta nigdy nie będzie w 100% pewne, gdy gracz ma
pełną kontrolę nad własnym komputerem.
