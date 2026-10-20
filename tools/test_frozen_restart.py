"""Controller for the actual Windows onefile restart regression (no GUI/game)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def wait_file(path, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8'))
        time.sleep(0.05)
    raise TimeoutError('Frozen restart probe did not create ' + path.name)


def check(executable):
    executable = Path(executable).resolve()
    if os.name != 'nt' or not executable.is_file():
        raise RuntimeError('Requires the built Windows launcher executable')
    with tempfile.TemporaryDirectory(prefix='acr-restart-probe-') as directory:
        root = Path(directory)
        child_pid = None
        success = False
        process = subprocess.Popen([str(executable), '--self-test-restart-parent', directory])
        try:
            info = wait_file(root / 'parent.json')
            child_pid = int(info['childPid'])
            child = wait_file(root / 'child-start.json')
            if Path(info['runtime']).resolve() == Path(child['runtime']).resolve():
                raise AssertionError('Restart reused the previous onefile extraction')
            if process.wait(timeout=60) != 0:
                raise AssertionError('Parent launcher failed')
            deadline = time.monotonic() + 15
            while Path(info['runtime']).exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            if Path(info['runtime']).exists():
                raise AssertionError('Parent bootloader did not clean up its extraction')
            (root / 'parent-exited').touch()
            result = wait_file(root / 'child-result.json')
            if result.get('ok') is not True or result.get('httpsImports') is not True:
                raise AssertionError('Delayed HTTPS/stdlib imports failed after restart')
            success = True
            print('Frozen restart passed: independent extraction, parent cleanup, delayed HTTPS imports')
        finally:
            # Release a waiting probe even when an assertion fails.
            (root / 'parent-exited').touch()
            if not success:
                for pid in (process.pid, child_pid):
                    if pid:
                        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=15, check=False)


if __name__ == '__main__':
    check(sys.argv[1])
