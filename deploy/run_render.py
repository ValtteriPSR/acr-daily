"""Run the protected club backend behind Caddy; Render supplies public TLS."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit


def main():
    import bcrypt
    env = os.environ.copy()
    env['PORT'] = env.get('PORT', '10000')
    env['ACR_PUBLIC_BASE_URL'] = env.get('ACR_PUBLIC_BASE_URL') or env.get('RENDER_EXTERNAL_URL', '')
    public = urlsplit(env['ACR_PUBLIC_BASE_URL'])
    if public.scheme != 'https' or not public.hostname or public.path not in ('', '/'):
        raise RuntimeError('An HTTPS public origin is required')
    env['ACR_PUBLIC_BASE_URL'] = env['ACR_PUBLIC_BASE_URL'].rstrip('/')
    env['ACR_PUBLIC_HOST'] = public.netloc
    for key in ('DATABASE_URL', 'ACR_ADMIN_KEY', 'ACR_ADMIN_PATH', 'ACR_GATEWAY_SECRET',
                'ADMIN_HTTP_PASSWORD', 'ACR_LAUNCHER_DOWNLOAD_URL'):
        if not env.get(key):
            raise RuntimeError('Missing environment variable: ' + key)
    if len(env['ADMIN_HTTP_PASSWORD']) < 16 or len(env['ACR_ADMIN_KEY']) < 32:
        raise RuntimeError('Administrator credentials are too short')
    env['ADMIN_PASSWORD_HASH'] = bcrypt.hashpw(
        env.pop('ADMIN_HTTP_PASSWORD').encode(), bcrypt.gensalt()).decode()
    root = Path(__file__).resolve().parent.parent
    processes = []
    stopping = False

    def stop(*_args):
        nonlocal stopping
        stopping = True
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        processes.append(subprocess.Popen(
            [sys.executable, '-u', 'server_local/server.py', '--host', '127.0.0.1', '--port', '8790'],
            cwd=root, env=env))
        processes.append(subprocess.Popen(
            ['caddy', 'run', '--config', 'deploy/Caddyfile.render', '--adapter', 'caddyfile'],
            cwd=root, env=env))
        while not stopping and all(p.poll() is None for p in processes):
            time.sleep(.25)
        return 0 if stopping else 1
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
