#!/usr/bin/python3
"""Consistent backups; immutable short history and verified non-expiring latest copies."""
import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import uuid

ROOT = Path('/opt/acr')
STATE = ROOT / 'backups/scheduled'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=600, **kwargs).stdout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_dump(data):
    if not data.startswith(b'PGDMP') or len(data) < 1024:
        raise ValueError('Invalid or empty PostgreSQL custom dump')
    catalog = run('podman', 'exec', '-i', 'acr-postgres', 'pg_restore', '--list', input=data)
    if b'TABLE public results ' not in catalog:
        raise ValueError('Dump does not contain club results table')


def download(client, ns, bucket, name):
    response = client.get_object(ns, bucket, name)
    try:
        data = response.data.content
    finally:
        response.data.close()
    expected = response.headers.get('opc-meta-sha256')
    if not expected or digest(data) != expected:
        raise ValueError('Remote backup SHA256 mismatch')
    return data


def put(client, ns, bucket, name, data, **kwargs):
    client.put_object(ns, bucket, name, data,
                      content_md5=base64.b64encode(hashlib.md5(data).digest()).decode(),
                      opc_meta={'sha256': digest(data)}, **kwargs)


def publish(client, ns, bucket, mode, data):
    suffix = 'dump' if mode == 'database' else 'tar.gz'
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    history = f'scheduled/{mode}/{stamp}-{uuid.uuid4().hex}.{suffix}'
    # Never change latest unless a separate immutable remote object was verified.
    put(client, ns, bucket, history, data, if_none_match='*')
    if download(client, ns, bucket, history) != data:
        raise ValueError('Remote immutable backup differs')
    latest = f'latest/{mode}.{suffix}'
    try:
        old = client.get_object(ns, bucket, latest)
        condition = {'if_match': old.headers['etag']}
        old.data.close()
    except Exception as error:
        if getattr(error, 'status', None) != 404:
            raise
        condition = {'if_none_match': '*'}
    put(client, ns, bucket, latest, data, **condition)
    if download(client, ns, bucket, latest) != data:
        raise ValueError('Remote latest backup differs')
    return {'object': history, 'latest': latest, 'sha256': digest(data),
            'bytes': len(data), 'verifiedAt': dt.datetime.now(dt.timezone.utc).isoformat()}


def dump_database():
    data = run('podman', 'exec', 'acr-postgres', 'pg_dump', '-U', 'postgres',
               '-d', 'acr_club', '--format=custom', '--no-owner', '--no-acl')
    validate_dump(data)
    return data


def full_archive(data):
    with tempfile.TemporaryDirectory(prefix='full.', dir=STATE) as directory:
        dump = Path(directory) / 'club.dump'
        dump.write_bytes(data)
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as archive:
            archive.add(dump, arcname='club.dump')
            for name in ('production.env', 'gateway.env', 'postgres.env',
                         'local-database.env', 'Caddyfile', 'data'):
                archive.add(ROOT / name, arcname=name)
            archive.add('/etc/containers/systemd', arcname='container-units')
            for path in sorted(Path('/etc/systemd/system').glob('acr-backup*')):
                archive.add(path, arcname='backup-units/' + path.name)
            archive.add(ROOT / 'backup-scheduled.py', arcname='backup-scheduled.py')
            archive.add(ROOT / 'backup-schedule.env', arcname='backup-schedule.env')
            commit = run('git', '-C', str(ROOT / 'source'), 'rev-parse', 'HEAD')
            info = tarfile.TarInfo('source-commit.txt'); info.size = len(commit); info.mode = 0o600
            archive.addfile(info, io.BytesIO(commit))
        return out.getvalue()


def restore_test(data):
    validate_dump(data)
    # Separate disposable database; production is never a restore target.
    database = 'acr_backup_verify_' + uuid.uuid4().hex
    assert database.startswith('acr_backup_verify_') and database != 'acr_club'
    run('podman', 'exec', 'acr-postgres', 'createdb', '-U', 'postgres', '-O', 'acr_club', database)
    try:
        run('podman', 'exec', '-i', 'acr-postgres', 'pg_restore', '--exit-on-error',
            '--no-owner', '--no-acl', '--role=acr_club', '-U', 'postgres', '-d', database, input=data)
        checks = run('podman', 'exec', 'acr-postgres', 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                     '-U', 'postgres', '-d', database, '-tAc',
                     "SELECT count(*) FROM pg_tables WHERE schemaname='public'; "
                     "SELECT count(*) FROM results; SELECT count(*) FROM admin_time_penalties; "
                     "SELECT count(*) FROM telemetry_penalties;").decode().strip().splitlines()
        if int(checks[0]) < 31:
            raise ValueError('Restored database is missing club tables')
        return {'tables': int(checks[0]), 'results': int(checks[1]),
                'adminPenalties': int(checks[2]), 'telemetryPenalties': int(checks[3])}
    finally:
        run('podman', 'exec', 'acr-postgres', 'dropdb', '-U', 'postgres', database)


def save_status(mode, value):
    path = STATE / (mode + '-status.json')
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value)); tmp.chmod(0o600); tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('database', 'full', 'verify'))
    mode = parser.parse_args().mode
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # Avoid overlapping timer/manual jobs.
        import oci
        client = oci.object_storage.ObjectStorageClient(
            config={}, signer=oci.auth.signers.InstancePrincipalsSecurityTokenSigner())
        ns = os.environ['ACR_BACKUP_NAMESPACE']
        bucket = os.environ.get('ACR_BACKUP_BUCKET', 'acr-migration-backups')
        try:
            if mode == 'verify':
                data = download(client, ns, bucket, 'latest/database.dump')
                counts = restore_test(data)
                # Also verify the current full archive without extracting credentials.
                full = download(client, ns, bucket, 'latest/full.tar.gz')
                with tarfile.open(fileobj=io.BytesIO(full), mode='r:gz') as archive:
                    required = {'club.dump', 'production.env', 'gateway.env', 'postgres.env', 'Caddyfile'}
                    if not required.issubset(archive.getnames()):
                        raise ValueError('Full archive missing recovery files')
                    validate_dump(archive.extractfile('club.dump').read())
                result = {'ok': True, 'verifiedAt': dt.datetime.now(dt.timezone.utc).isoformat(), **counts}
            else:
                data = dump_database()
                if mode == 'full':
                    data = full_archive(data)
                result = {'ok': True, **publish(client, ns, bucket, mode, data)}
            save_status(mode, result)
            print(json.dumps(result), flush=True)
        except Exception as error:
            # Keep the most recent successful manifest and record a separate failure.
            save_status(mode + '-failure', {'ok': False, 'failedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
                                          'errorType': type(error).__name__})
            print('BACKUP FAILED: ' + type(error).__name__, flush=True)
            raise


if __name__ == '__main__':
    main()
