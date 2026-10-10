# ACR Rally Club V4 — poprawka formularza ZAPISZ SIĘ

Objaw: po kliknięciu ZAPISZ SIĘ strona `/web/enroll` zwraca
`{"error": "Niedozwolone pochodzenie żądania"}`.

Przyczyna: w V4 porównywano `Origin` z `Host` dosłownie, co nie
uwzględniało alternatywnych lokalnych nazw `localhost`, `127.0.0.1`,
`[::1]` przy tym samym porcie.

Poprawka:
- równoważne adresy loopback na tym samym porcie są akceptowane;
- obca domena i inny port nadal są odrzucane;
- token CSRF w formularzu i cookie pozostaje obowiązkowy;
- nie zmieniamy bazy, zgłoszeń, panelu, linków RUN ani launchera.

## Instalacja

1. Zatrzymaj `start_local_server.bat` (Ctrl+C w jego oknie).
2. Skopiuj `server_local/server.py` z tej paczki do istniejącego
   `acr-daily-main/server_local/server.py` i zaakceptuj zastąpienie.
3. Uruchom `start_local_server.bat` ponownie.
4. Wejdź od nowa na `http://127.0.0.1:8790/` i otwórz rajd.
5. Wpisz nick i kliknij ZAPISZ SIĘ.

Nie trzeba ponownie budować pliku EXE ani resetować bazy.

Jeżeli błąd występuje nadal, w konsoli serwera zostanie wypisane
`Rejected browser Origin: ... Host: ...` — skopiuj dokładnie ten wiersz.

Plik `tests/test_web_launcher.py` jest dołączony dla testów regresji,
ale do naprawy działającej instalacji wystarczy sam `server_local/server.py`.
