"""Self-contained server preflight, does NOT create accounts or change the DB."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def check_server(*, distribution=False) -> list[str]:
    sys.path.insert(0, str(ROOT / 'server_local'))
    from admin_panel import load_catalog
    errors = []
    try:
        catalog = load_catalog(ROOT)
        cars = catalog['cars']
        stages = catalog['stages']
        assert len(cars) >= 15 and len(stages) >= 20
        ids = [x['id'] for x in stages]
        assert len(ids) == len(set(ids)), 'Duplicate stage ID'
        ids = [x['id'] for x in cars]
        assert len(ids) == len(set(ids)), 'Duplicate car ID'
        classes = sorted(set(c['cls'] for c in cars))
        print(f'OK katalog ACR Daily: {len(cars)} samochodów, {len(stages)} OS-ów, {len(classes)} klas')
        print('   ' + ', '.join(classes))
    except Exception as exc:
        errors.append(f'Katalogi: {exc}')
    required = [
        'server_local/server.py', 'server_local/admin_panel.py', 'server_local/seasons.py',
        'server_local/web_launcher.py', 'server_local/admin_access.py', 'server_local/public_security.py',
        'server_local/driver_guide.py', 'server_local/club_settings.py', 'server_local/attempt_updates.py', 'server_local/admin_customization.py', 'server_local/live_results.py', 'server_local/rally_details.py', 'deploy/compose.yaml',
        'server_local/i18n.py', 'server_local/translations/pl.json',
        'deploy/Caddyfile', 'deploy/Dockerfile', '.github/workflows/launcher-release.yml',
        'tools/vendor_acr_daily.py', 'tools/export_club_catalog.py', 'LICENSE',
        'VERSION', 'deploy/configure_hosting.py', 'docs/HOSTING.md',
        'server_local/steam_auth.py', 'server_local/discord_notifications.py',
    ]
    missing = [p for p in required if not (ROOT / p).is_file()]
    if missing:
        errors.append('Brakujące pliki pakietu: ' + ', '.join(missing))
    else:
        print('OK wymagane pliki serwera, panelu, poradnika, Dockera i release workflow')
    if distribution:
        for path in ('server_local/club.sqlite3', 'server_local/admin_key.txt', 'server_local/admin_route.txt', 'deploy/.env'):
            if (ROOT/path).exists():
                errors.append(f'Prywatny plik w paczce dystrybucyjnej: {path}. Nie publikuj ZIP!')
    return errors


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--server',action='store_true', help='Sprawdź gotowość serwera, także po uruchomieniu')
    parser.add_argument('--distribution',action='store_true', help='Sprawdź także brak sekretów w ZIP przed dystrybucją')
    args=parser.parse_args(argv)
    errors=check_server(distribution=args.distribution)
    if errors:
        for error in errors: print('BŁĄD:',error,file=sys.stderr)
        return 1
    print('PREFLIGHT OK — serwer może działać z tej paczki, bez folderu acr-daily-main')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
