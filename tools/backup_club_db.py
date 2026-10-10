"""SQLite-safe online backup. Schedule via cron and copy backups OFF the VPS."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import os
from pathlib import Path
import sqlite3


def backup(src,dst):
    src=Path(src)
    if not src.exists():
        raise FileNotFoundError(f'Database not found: {src}')
    dst=Path(dst)
    dst.mkdir(parents=True,exist_ok=True)
    target=dst/f'club-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.sqlite3'
    with sqlite3.connect(src) as db, sqlite3.connect(target) as out:
        db.backup(out)
        status=out.execute('PRAGMA integrity_check').fetchone()[0]
        if status!='ok':
            target.unlink(missing_ok=True)
            raise RuntimeError('Backup integrity check failed')
    target.chmod(0o600)
    return target

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--db',default=os.environ.get('ACR_DB_PATH','server_local/club.sqlite3'))
    ap.add_argument('--output',default='deploy/backups')
    args=ap.parse_args()
    print(backup(args.db,args.output))
