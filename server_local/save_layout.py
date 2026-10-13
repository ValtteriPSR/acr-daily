"""Use the exact pure-stdlib validator packaged with the Windows launcher."""
import importlib.util
from pathlib import Path
_path=Path(__file__).resolve().parents[1]/'client/club_local/save_layout.py'
_spec=importlib.util.spec_from_file_location('_club_save_layout',_path)
_module=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
inspect=_module.inspect
InvalidSave=_module.InvalidSave
rally_report=_module.rally_report
