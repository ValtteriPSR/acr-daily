> **Instrukcja historyczna.** Dla pełnej instalacji V6.2 i prywatnego panelu administratora korzystaj z `START-TUTAJ.md`.

# ACR Rally Club V5 — sezon, dywizje, zespoły i wyniki OS-ów

To aktualizacja działającego **ACR Rally Club V4 Web Launcher**, nie osobny program.

## Instalacja

1. **Zatrzymaj** `start_local_server.bat` (`Ctrl+C`), zamknij launcher i ACR.
2. Skopiuj w bezpieczne miejsce:
   - `server_local\club.sqlite3` (razem z `club.sqlite3-wal` i `club.sqlite3-shm`, jeśli występują; najlepiej przy wyłączonym serwerze);
   - `server_local\admin_key.txt`;
   - `%LOCALAPPDATA%\acr\Saved\SaveGames\PlayerDataSaveSlot.sav`.
3. Rozpakuj paczkę V5 **osobno**. Skopiuj pliki znajdujące się *wewnątrz* paczki do folderu `acr-daily-main`, w którym masz oryginalny ACR Daily i V4. Potwierdź podmianę plików kodu.
4. **Nie usuwaj `server_local\club.sqlite3` ani `admin_key.txt`!** Paczka V5 celowo nie zawiera tych plików.
5. Uruchom `start_local_server.bat`. Tabele i kolumny V5 zostaną dodane automatycznie.
6. Otwórz `open_admin_seasons.bat` albo http://127.0.0.1:8790/admin/seasons.
7. `run_builder.bat` i `build_web_launcher_exe.bat` nie są potrzebne do aktualizacji V5. Obecny launcher EXE działa tak jak przedtem.

Dodatkowo w pakiecie: `test_v5.bat` uruchamia testy automatyczne Pythona.

## Adresy WWW

- `http://127.0.0.1:8790/` — lista rajdów;
- `http://127.0.0.1:8790/club` — rejestracja nicku do klubu i odzyskanie dostępu;
- `http://127.0.0.1:8790/seasons` — lista sezonów;
- `http://127.0.0.1:8790/season/<id>` — klasyfikacja sezonowa, dywizje i teamy;
- `http://127.0.0.1:8790/admin` — dotychczasowy edytor rajdów;
- `http://127.0.0.1:8790/admin/seasons` — **nowy panel sezonów**.

## Tworzenie sezonu — przykład

1. Utwórz zwykłe rajdy przez `/admin` (np. Grecja, Walia, Alzacja). Każdy rajd nadal ma własną datę, klasę aut i listę OS-ów.
2. W `/admin/seasons` kliknij **+ Nowy sezon**.
3. Ustaw nazwę, początek i koniec sezonu (muszą obejmować daty wszystkich jego rajdów).
4. Ustaw punktację ogólną, np. `35,25,20,16,13,11,9,7,5,3,2`.
5. Ustaw punktację dywizyjną, np. `30,20,15,12,10,8,6,4,3,2`.
6. Wybierz, czy punkty teamów mają być sumą generalka+dywizja (domyślnie), tylko generalką, czy tylko dywizją.
7. Zapisz sezon; otrzyma automatyczne ID `season-YYYY-xxxxxxxx`.
8. Zaznacz rajdy w sekcji „Rajdy w sezonie”, ustaw ich kolejność strzałkami i zapisz kalendarz. Maksymalnie **100** różnych rajdów na sezon.
9. **Opcjonalnie** kliknij „Punkty rajdu” przy konkretnej rundzie i wpisz inną tabelę punktów dla tego jednego rajdu. Puste pole oznacza domyślną punktację sezonu.
10. Utwórz dywizje (maksymalnie **10**), np. Division 1, Division 2, Division 3.
11. Utwórz teamy; dla każdego określ oddzielnie limit **1–10 zawodników**.
12. Gdy kierowcy zarejestrują się w `/club`, przydziel im dywizje i teamy w sekcji „Przydziały kierowców”. Przy każdej osobie kliknij „Przypisz”.

**WAŻNE:** Przy sezonie, który ma dywizje, kierowca **nie może uruchomić RUN**, dopóki administrator nie przydzieli mu jednej z nich. Po pierwszym rozpoczęciu przez niego OS-u przydział dywizji i teamu staje się stały. Punkty nie mogą zostać zmienione po rozpoczęciu pierwszego przejazdu w sezonie; punktacja konkretnego rajdu jest blokowana po pierwszym starcie w tym rajdzie.

## Jak działa punktacja

Każdy ukończony rajd jest rozliczany **po zamknięciu okna czasowego rajdu**. Wcześniej czasy na stronie są prowizoryczne, a punkty wynoszą 0.

- Generalka: miejsce wśród kierowców klubowych, którzy ukończyli rajd w całości (wszystkie OS-y, status `completed`).
- Dywizja: oddzielne miejsce wśród kierowców **tej samej dywizji**.
- Kierowca dostaje punkty za oba miejsca. Na liście sezonowej pokazywane są oddzielnie i łącznie.
- Jeśli punktacja to `35,25,20`, miejsca 1–3 dostają odpowiednio 35,25,20; od miejsca **4 każde ukończenie daje 1 punkt**.
- DNF daje **0** zarówno za generalkę, jak i za dywizję, bez względu na przejechane wcześniej OS-y.
- Remis czasowy: np. dwa identyczne czasy na pierwszym miejscu ⇒ miejsca `1, 1, 3`, identyczne punkty za tę samą pozycję.
- Domyślnie punktacja teamu = **suma punktów generalnych i dywizyjnych wszystkich przypisanych kierowców**. W panelu sezonu można wybrać tylko jedną z kategorii punktów. Team nie może mieć więcej zawodników niż skonfigurowany limit (1–10).
- Dywizję i team przydziela administrator, a nie sam zawodnik.

Przykład: pierwszy zawodnik generalki i swojej dywizji zdobywa `35 + 30 = 65 pkt` dla siebie i (w trybie łącznym) swojego teamu.

## Rejestracja gracza — jeden nick na wszystkie rajdy

1. Kierowca otwiera `/club`, podaje wybrany nick i wybiera **ZAREJESTRUJ SIĘ**.
2. Na stronie otrzyma losowy **kod odzyskiwania konta**. Powinien skopiować go i przechowywać prywatnie — zostanie pokazany tylko raz.
3. Przeglądarka zapisze trwałe cookie `HttpOnly` na **365 dni**. Przy następnych rajdach nick będzie pobierany automatycznie z konta klubowego. Nie trzeba wpisywać go w launcherze.
4. Na stronie rajdu kierowca klika **ZAPISZ SIĘ**, potem **RUN RALLY**. Pozostaje dotychczasowy jednorazowy bilet do launchera, który pobiera konfigurację i uruchamia ACR.
5. Gdy gracz straci dane przeglądarki / zmieni komputer, może odzyskać dostęp na `/club` przy użyciu nicku i kodu odzyskiwania.

**Uwaga:** To nadal system nick+token, **bez zweryfikowanej tożsamości Steam**. Można utworzyć wiele odrębnych kont klubowych. System ogranicza dublowanie prób dla **tego samego konta**, ale nie może rozpoznać, że dwie różne nazwy należą do jednej osoby. W publicznym sezonie potrzebna będzie mocniejsza identyfikacja i kontrola telemetrii.

**Kompatybilność:** Wcześniejsze zgłoszenia V4 pozostają w bazie i na stronie wyników. Nie są jednak automatycznie łączone z nowymi kontami klubowymi po samym podobieństwie nicku, aby nikt nie mógł przejąć historii innego uczestnika. Do sezonowych rajdów nowe zgłoszenia wymagają konta klubowego.

## Szczegółowe wyniki OS-ów

Strona każdego rajdu `/rally/<id>` pokazuje, oprócz dotychczasowej klasyfikacji generalnej, tabelę każdego OS-u:

`OS / kierowca / RAW / kary / oficjalny czas`.

Dane pochodzą z istniejącej tabeli `results` i z oficjalnego odczytu `.sav`. W obecnej implementacji launchera szczegóły są publikowane **po zatwierdzeniu całego Rally Weekend**, nie bezpośrednio po każdym OS-ie. To chroni przed zamieszczeniem nieważnego wyniku, kiedy gracz nie ukończył kolejnych odcinków.

## Test bez zużywania podejścia

Możesz stworzyć sezon i przydziały, a następnie obejrzeć `/season/<id>` i `/rally/<id>` bez uruchamiania gry. Samo tworzenie sezonu, dywizji lub oglądanie tabel nie zużywa podejścia. Dopiero działanie launchera po START wykorzystuje jednorazową próbę.

## Kopie i bezpieczeństwo

- V5 nie zmienia parsera Rally Weekend ani mechanizmu odczytu kar i DNF z V4.
- Zmiany dotyczą przede wszystkim SQLite, serwera i stron WWW. Dotychczasowy EXE **nie wymaga ponownej kompilacji**.
- Istniejący panel nadal dostępny wyłącznie lokalnie (`127.0.0.1`) po zalogowaniu kluczem.
- Nie wystawiaj portu `8790` bezpośrednio w Internecie. Publiczny serwer wymaga HTTPS, kont graczy i administratorów oraz dodatkowych zabezpieczeń.
- Odczyt punktów jest **obliczany na serwerze** z ukończonych wyników, więc klient nie podaje swoich punktów.
- Nie ma gwarancji odporności na zmodyfikowanego klienta — potrzebna jest docelowo niezależna weryfikacja telemetrii.

## Testy

Na Linux sprawdzono syntaktykę Pythona, JavaScript panelu oraz integrację lokalnego HTTP, SQLite, rejestrację, odzyskiwanie nicku, bilety RUN, blokadę DNF, remisy, limity grup, oddzielną punktację rajdów i migrację starej bazy V4. **Nie wykonywano jeszcze testu gry na Windows**, więc pierwszy rajd sezonowy wykonaj na kontach testowych.
