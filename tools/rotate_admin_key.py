"""Offline key rotation. Stop the server first, then restart it. No network required."""
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parent.parent
keyfile = ROOT / 'server_local' / 'admin_key.txt'
if not keyfile.is_file():
    print('Brak admin_key.txt — klucz zostanie utworzony po uruchomieniu serwera')
    sys.exit(1)
key = secrets.token_urlsafe(32)
tmp = keyfile.with_name(keyfile.name + '.tmp')
with tmp.open('w', encoding='ascii') as out:
    out.write(key + '\n')
os.replace(tmp, keyfile)
print('Wygenerowano NOWY klucz admin w', keyfile)
print('URUCHOM SERWER PONOWNIE, aby stare sesje i klucz przestały działać.')
