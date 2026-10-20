"""Isolated frozen-runtime regression probe; never touches game or user data."""
import json
from pathlib import Path
import sys
import time


def parent(directory):
    from .launcher_process import start_independent
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    process = start_independent(['--self-test-restart-child', str(root)])
    (root / 'parent.json').write_text(json.dumps({
        'runtime': sys._MEIPASS, 'childPid': process.pid,
    }), encoding='utf-8')
    return 0


def child(directory):
    root = Path(directory)
    (root / 'child-start.json').write_text(json.dumps({
        'runtime': sys._MEIPASS,
    }), encoding='utf-8')
    deadline = time.monotonic() + 90
    while not (root / 'parent-exited').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Controller did not confirm parent bootloader cleanup')
        time.sleep(0.05)
    # The controller confirms the original extraction is gone before releasing us.
    # Exercise real delayed stdlib/HTTPS imports, not only the environment flag.
    import http.client
    import ssl
    import urllib.request
    import zipfile
    archive = Path(sys._MEIPASS) / 'base_library.zip'
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist(), 'Bundled standard library is empty'
    context = ssl.create_default_context()
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    (root / 'child-result.json').write_text(json.dumps({
        'ok': True, 'runtime': sys._MEIPASS, 'httpsImports': True,
    }), encoding='utf-8')
    return 0
