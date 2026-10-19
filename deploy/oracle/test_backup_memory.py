#!/usr/bin/env python3
"""Prove maintenance cgroup caps contain oversized jobs on a disposable CI host."""
import os
from pathlib import Path
import subprocess
import sys
import uuid


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=90)


def exercise_limits(path):
    source = path.read_text()
    limits = dict(line.split('=', 1) for line in source.splitlines()
                  if line.startswith(('MemoryHigh=', 'MemoryMax=', 'MemorySwapMax=')))
    if set(limits) != {'MemoryHigh', 'MemoryMax', 'MemorySwapMax'}:
        raise AssertionError('Memory limits are incomplete: ' + path.name)
    # Exercise the hard cap promptly. The production soft threshold deliberately
    # throttles allocations and can prevent a test from reaching the OOM limit.
    # Only this disposable probe omits that throttle; RAM/swap caps are unchanged.
    limits['MemoryHigh'] = 'infinity'
    unit = 'acr-backup-memory-probe-' + uuid.uuid4().hex[:12]
    try:
        # Twice the hard limit, including touched pages; a healthy exit is a failure.
        result = run('systemd-run', '--unit=' + unit, '--wait',
                     '--property=Type=oneshot', '--property=TimeoutStartSec=60',
                     '--property=OOMPolicy=kill',
                     *('--property=' + k + '=' + v for k, v in limits.items()),
                     sys.executable, '-c',
                     'x=bytearray(1024*1024*1024)\n'
                     'for i in range(0,len(x),4096): x[i]=1')
        reason = run('systemctl', 'show', unit, '-p', 'Result', '--value').stdout.strip()
        if result.returncode == 0 or reason != 'oom-kill':
            raise AssertionError('Expected a contained OOM kill, got ' + reason + ': ' + result.stderr)
        print(path.name + ': oversized job was killed within its own cgroup')
    finally:
        run('systemctl', 'stop', unit)
        run('systemctl', 'reset-failed', unit)


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run as root on a disposable systemd host')
    root = Path(__file__).parent
    for name in ('scheduled/acr-backup@.service', 'dnf-makecache-memory.conf'):
        exercise_limits(root / name)


if __name__ == '__main__':
    main()
