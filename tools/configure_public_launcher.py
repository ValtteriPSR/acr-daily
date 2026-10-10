"""Freeze a trusted HTTPS league server URL into the Windows EXE at release build."""
from __future__ import annotations
import argparse
from pathlib import Path
from urllib.parse import urlsplit


def validate_url(value):
    parsed=urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or
            parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment):
        raise ValueError('Launcher must use an HTTPS origin, e.g. https://liga.example.com')
    return value.rstrip('/')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--url',required=True)
    args=ap.parse_args()
    url=validate_url(args.url)
    dest=Path(__file__).resolve().parent.parent/'client'/'club_local'/'site_config.py'
    dest.write_text('# Generated during a trusted GitHub Actions Windows release build.\n'
                    +f'DEFAULT_SERVER = {url!r}\n',encoding='utf8')
    print('Launcher configured for',url)

if __name__=='__main__':main()
