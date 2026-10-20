"""Start a launcher instance that must survive the current process exiting."""
import os
from pathlib import Path
import subprocess
import sys


def start_independent(arguments):
    """Use a fresh onefile extraction; never inherit a dying parent's runtime."""
    command = [sys.executable]
    if not getattr(sys, 'frozen', False):
        command.append(str(Path(__file__).resolve().parents[1] / 'run_web_launcher.py'))
    environment = os.environ.copy()
    if getattr(sys, 'frozen', False):
        # Supported PyInstaller restart API (6.9+). Do not edit private _PYI_* vars.
        environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return subprocess.Popen(command + list(arguments), env=environment)
