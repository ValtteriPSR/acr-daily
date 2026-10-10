"""Read-only preflight of local Rally Weekend settings against server event."""
import json
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'client'))
from acr_daily import saveslot
from club_local.integrity import report_from_save
from club_local.integrity_rules import compare

print('ACR RALLY CLUB - KONTROLA USTAWIEN (ODCZYT)')
print('Ta kontrola nie rozpoczyna rajdu i nie zuzywa podejscia.\n')
try:
    with urlopen('http://127.0.0.1:8790/api/events',timeout=3) as response:
        events=json.load(response)['events']
except Exception as e:
    print('Serwer lokalny niedostepny:',e)
    events=[]
if not events:
    example=ROOT/'examples'/'grecja-local-demo.json'
    if example.exists():
        events=[json.loads(example.read_text(encoding='utf-8-sig'))]
        print('Porownuje z plikiem przykladowego rajdu:',example)
    else:
        print('Brak konfiguracji rajdu. Wlacz start_local_server.bat.')
        sys.exit(2)

for i,ev in enumerate(events,1):
    print(f'  {i}. {ev["name"]} [{ev["id"]}]')
try:
    chosen=int(input('Numer rajdu [1]: ') or '1')
    ev=events[chosen-1]
except (ValueError,IndexError):
    print('Nieprawidlowy wybor')
    sys.exit(2)

path=Path(saveslot.SAVE)
print('Plik gry:',path)
try:
    actual=report_from_save(path.read_bytes())
except Exception as exc:
    print('BLAD ODCZYTU:',exc)
    sys.exit(2)
problems=compare(ev,actual)
print()
if problems:
    print('NIEZGODNE USTAWIENIA:')
    for x in problems: print(' - '+x)
    print('\nUwaga: w legalnym przejezdzie wykryte niezgodnosci moga oznaczac DNF.')
    sys.exit(1)
print('OK: ustawienia Rally Weekend zgodne z wybranym rajdem.')
print('Uszkodzenia:', 'wlaczone' if actual['rules']['damage'] else 'WYLACZONE',
      '| intensywnosc:',actual['rules']['intensity'])
print('Kary:',actual['rules']['penalty'],'| liczba OS:',len(actual['stages']))
