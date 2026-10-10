"""Deterministically acquire the ACR Daily client modules used by ACR Rally Club.

The web SERVER does not need these modules; it is fully included in this ZIP.
GitHub Actions/Windows builder fetches only the pinned, SHA-verified upstream
client code to compile the downloadable launcher. Never pulls 'main' implicitly.

Source: https://github.com/khanhonthetrack/acr-daily
MIT License, Copyright (c) 2026 Ngoc Khanh Nguyen.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = 'khanhonthetrack/acr-daily'
REVISION = '135466d177e47039e0a8b6a6af2716379554c9e9'
# Upstream git blob SHA-1s, independently checked against GitHub repository.
BLOBS = {
    '__init__.py': '5a4517873c2131cda2fe2ba871b57e617eaae8e6',
    'names.py': '1fd9c95e1218e0b98f2f487c08bcbbf4ececb16a',
    'settings.py': '43190f45f508ad2375879667b1de81ae510d403a',
    'rallyweekend.py': '7f8d851d4230d51c7e00d30da51e258bed1fc10e',
    'saveslot.py': '81f56e700f2d05df1646b193026d628be1777169',
    'telemetry.py': 'afbc753310875a412786d0006ff7d5a165949868',
}
PATH = ROOT / 'client' / 'acr_daily'
MAX_BYTES = 1024 * 1024


def git_blob_hash(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\x00' + data).hexdigest()


def verified(data: bytes, sha: str) -> bool:
    return bool(data and len(data) < MAX_BYTES and git_blob_hash(data) == sha)


def download(name: str) -> bytes:
    url = f'https://raw.githubusercontent.com/{UPSTREAM}/{REVISION}/client/acr_daily/{name}'
    req = Request(url, headers={'User-Agent': 'ACR-Rally-Club-Upstream-Vendor/0.2'})
    with urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise OSError(f'GitHub returned HTTP {response.status}: {url}')
        data = response.read(MAX_BYTES + 1)
    return data


def install(name: str, data: bytes, target: Path) -> None:
    if not verified(data, BLOBS[name]):
        raise ValueError(f'BŁĄD: ACR Daily {name} nie zgadza się z SHA (przerwano instalację).')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Existing Rally Club modules are NOT touched. Only these upstream paths.
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=name+'.', suffix='.tmp', delete=False) as out:
        temp = Path(out.name)
        out.write(data)
    try:
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true', help='Sprawdź lokalne moduły, bez pobierania')
    ap.add_argument('--download', action='store_true', help='Pobierz brakujące moduły z przypiętej rewizji GitHub')
    args = ap.parse_args(argv)
    if args.check == args.download:
        ap.error('Wybierz dokładnie jedno: --check albo --download')
    failed = []
    for name, sha in BLOBS.items():
        target = PATH / name
        existing = target.read_bytes() if target.is_file() else b''
        if verified(existing, sha):
            print(f'OK   {name}')
            continue
        if args.check:
            print(f'BRAK/NIEZGODNY  {name}')
            failed.append(name)
            continue
        if existing:
            print(f'UWAGA: poprzedni {name} nie zgadza się z oryginalną rewizją. Zostanie zastąpiony.')
        try:
            data = download(name)
            install(name, data, target)
        except (OSError, ValueError, URLError) as exc:
            print(f'BŁĄD pobierania {name}: {exc}', file=sys.stderr)
            failed.append(name)
            continue
        print(f'POBRANO {name} (zgodność Git SHA sprawdzona)')
    if failed:
        print('BRAKUJE: ' + ', '.join(failed), file=sys.stderr)
        print('Serwer WWW działa samodzielnie; do budowy Windows EXE wymagany jest dostęp do GitHub.', file=sys.stderr)
        return 1
    print(f'Gotowe. Wersja źródłowa ACR Daily: {REVISION}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
