"""Fail the EXE build early if ACR Daily modules are missing/unimportable.

Run after vendor_acr_daily.py --download, before PyInstaller.
"""
import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "client"))
MODULES = (
    "acr_daily.settings",
    "acr_daily.saveslot",
    "acr_daily.rallyweekend",
    "acr_daily.telemetry",
    "acr_daily.names",
    "acr_daily.rallyclub",
    "club_local.app",
    "club_local.integrity",
    "club_local.monitor",
    "club_local.web_launch",
    "club_local.web_install",
    "club_local.version",
)

def verify():
    missing = []
    for name in MODULES:
        try:
            module = importlib.import_module(name)
            if module.__file__ is None or not Path(module.__file__).resolve().is_relative_to(ROOT / "client"):
                raise ImportError("modul pochodzi spoza katalogu projektu")
            print("OK", name)
        except Exception as exc:
            missing.append((name, exc))
            print("BRAK", name, repr(exc), file=sys.stderr)
    if missing:
        raise RuntimeError("Build EXE wstrzymany: brak zależności. Zobacz bledy BRAK powyzej.")
    return True

if __name__ == "__main__":
    try:
        verify()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
