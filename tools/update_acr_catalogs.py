"""Compare ACR Daily's curated game catalogs with upstream GitHub versions.

--check: inspect changes without writing (safe to schedule).
--apply:  backup old versions and atomically install validated upstream files.

These are CURATED ACR DAILY CATALOGS, not a direct game-file reader.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import difflib
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {
    'cars.js': 'https://raw.githubusercontent.com/khanhonthetrack/acr-daily/main/server/src/cars.js',
    'stages.js': 'https://raw.githubusercontent.com/khanhonthetrack/acr-daily/main/server/src/stages.js',
}
DEST = ROOT / 'server' / 'src'


def fetch(url):
    request = Request(url, headers={'User-Agent': 'ACR-Rally-Club-Catalog-Checker/1.0'})
    with urlopen(request, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError(f'HTTP {response.status}')
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise RuntimeError('Upstream catalog unexpectedly large')
    return body.decode('utf-8')


def parse_inventory(name, text):
    if name == 'cars.js':
        if 'export const CARS' not in text:
            raise ValueError('Nie rozpoznano tablicy CARS')
        pattern = re.compile(r"\{\s*id:\s*'([^']+)',\s*telemetry:\s*'([^']+)',\s*name:\s*'([^']+)',\s*cls:\s*'([^']+)',\s*group:\s*'([^']+)'", re.M)
        rows = {ident: (tele, display, cls, group) for ident, tele, display, cls, group in pattern.findall(text)}
        if len(rows) < 15:
            raise ValueError(f'Katalog aut zbyt mały: {len(rows)}')
    elif name == 'stages.js':
        if 'MENU_NAMES' not in text:
            raise ValueError('Nie rozpoznano MENU_NAMES')
        pattern = re.compile(r'^\s*([A-Za-z0-9]+):\s*([\'"])(.*?)\2\s*,\s*$', re.M)
        rows = {ident: display for ident, _, display in pattern.findall(text)
                if ident.startswith(('Greece', 'Alsace', 'Weles', 'MonteCarlo'))}
        if len(rows) < 20:
            raise ValueError(f'Katalog OS-ów zbyt mały: {len(rows)}')
    else:
        raise ValueError('Nieznany katalog')
    if not all(re.fullmatch(r'[A-Za-z0-9]+', key) for key in rows):
        raise ValueError('Niebezpieczny format identyfikatora')
    return rows


def compare(current, proposed):
    old = set(current)
    new = set(proposed)
    return sorted(new - old), sorted(old - new), sorted(k for k in old & new if current[k] != proposed[k])


def apply_updates(updates, base):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    backup = base / '.catalog-backups' / stamp
    backup.mkdir(parents=True, exist_ok=False)
    for name, text in updates.items():
        old_file = base / name
        if old_file.exists():
            shutil.copy2(old_file, backup / name)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=base,
                                         prefix=name+'.', suffix='.tmp', delete=False) as fp:
            fp.write(text)
            tmp = Path(fp.name)
        tmp.replace(old_file)
    return backup


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    updates = {}
    try:
        for name, url in SOURCES.items():
            target = DEST / name
            if not target.exists():
                raise FileNotFoundError(f'Brak pliku: {target}')
            old_text = target.read_text(encoding='utf-8')
            new_text = fetch(url)
            old_inventory = parse_inventory(name, old_text)
            new_inventory = parse_inventory(name, new_text)
            added, removed, changed = compare(old_inventory, new_inventory)
            print(f'{name}: obecnie {len(old_inventory)}, w upstream {len(new_inventory)}')
            print('  nowe ID:', ', '.join(added) if added else '(brak)')
            print('  usunięte ID:', ', '.join(removed) if removed else '(brak)')
            print('  zmienione:', ', '.join(changed) if changed else '(brak)')
            if removed:
                raise ValueError('Usunięto identyfikatory! Wymagana ręczna weryfikacja źródła.')
            if len(old_inventory) > len(new_inventory):
                raise ValueError('Nowy katalog ma mniej wpisów niż poprzedni')
            if new_text != old_text:
                updates[name] = new_text
        if not updates:
            print('Katalogi są aktualne; nie ma zmian.')
            return 0
        if args.check:
            print('Znaleziono zmiany. To tylko sprawdzenie; niczego nie zapisano.')
            print('Aby zastosować PO WERYFIKACJI: update_acr_catalogs.bat')
            return 0
        backup = apply_updates(updates, DEST)
        print('Zaktualizowano:', ', '.join(updates))
        print('Kopia poprzednich plików:', backup)
        print('UWAGA: po dodaniu aut zbuduj klienta EXE ponownie (build_player_exe.bat).')
        print('ZMIANY W GRZE mogą wyprzedzać katalog ACR Daily; sprawdź nowe ID w samej grze.')
        return 0
    except Exception as exc:
        print('BŁĄD:', str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
