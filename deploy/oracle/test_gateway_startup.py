#!/usr/bin/env python3
"""Exercise the real gateway Unit dependencies with a failed disposable backend.

Run as root on a disposable systemd host. Production club services are untouched.
"""
from pathlib import Path
import os
import subprocess
import uuid


def run(*args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=30)


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run as root on a systemd host')
    source = (Path(__file__).parent / 'quadlet/acr-caddy.container').read_text()
    unit = source.split('[Unit]', 1)[1].split('[Container]', 1)[0]
    if 'acr-app.service' not in unit:
        raise SystemExit('Gateway application dependency is missing from fixture')
    suffix = uuid.uuid4().hex[:12]
    backend = 'acr-app-probe-' + suffix + '.service'
    gateway = 'acr-gateway-probe-' + suffix + '.service'
    root = Path('/run/systemd/system')
    marker = Path('/run/acr-gateway-probe-' + suffix)
    files = [root / backend, root / gateway]
    try:
        files[0].write_text('[Unit]\nDescription=Disposable failed backend\n'
                            '[Service]\nType=oneshot\nExecStart=/usr/bin/false\n')
        files[1].write_text('[Unit]' + unit.replace('acr-app.service', backend) +
                            '\n[Service]\nType=oneshot\nRemainAfterExit=yes\n'
                            'ExecStart=/usr/bin/touch ' + str(marker) + '\n')
        if run('systemctl', 'daemon-reload').returncode:
            raise RuntimeError('systemd reload failed')
        result = run('systemctl', 'start', gateway)
        if run('systemctl', 'is-failed', '--quiet', backend).returncode:
            raise AssertionError('The backend failure was not exercised')
        if result.returncode or not marker.exists():
            raise AssertionError('Gateway was blocked by the initial backend failure: ' + result.stderr)
        print('Gateway starts even when the first backend start fails')
    finally:
        run('systemctl', 'stop', gateway, backend)
        run('systemctl', 'reset-failed', gateway, backend)
        for path in files:
            path.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)
        run('systemctl', 'daemon-reload')


if __name__ == '__main__':
    main()
