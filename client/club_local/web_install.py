"""Register acrclub:// per-user; no admin rights and no global PATH changes."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import sys


def install(executable=None):
    if os.name != 'nt':
        raise RuntimeError('Instalacja protokołu acrclub:// jest obsługiwana na Windows.')
    import winreg
    exe=Path(executable or sys.executable).resolve()
    if not exe.is_file() or exe.suffix.lower() != '.exe' or exe.name.lower()=='python.exe':
        raise RuntimeError('Uruchom instalację ze skompilowanego ACR-Club-Launcher.exe.')
    base=Path(os.environ.get('LOCALAPPDATA') or Path.home())
    install_dir=base / 'Programs' / 'ACR Rally Club'
    install_dir.mkdir(parents=True,exist_ok=True)
    target=install_dir / 'ACR-Club-Launcher.exe'
    if exe != target:
        # Never overwrite a running executable; Windows will refuse if active.
        shutil.copy2(exe,target)
    key=r'Software\Classes\acrclub'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,key) as h:
        winreg.SetValueEx(h,None,0,winreg.REG_SZ,'URL:ACR Rally Club Protocol')
        winreg.SetValueEx(h,'URL Protocol',0,winreg.REG_SZ,'')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,key+r'\shell\open\command') as h:
        winreg.SetValueEx(h,None,0,winreg.REG_SZ,'"'+str(target)+'" "%1"')
    cfg_dir=base / 'ACR Rally Club'
    cfg_dir.mkdir(parents=True,exist_ok=True)
    cfg=cfg_dir/'launcher-config.json'
    from .site_config import DEFAULT_SERVER
    from .version import VERSION
    # Release install always binds launcher to this distributor's configured URL.
    # Do not accidentally leave an old localhost test URL or a prior domain.
    cfg.write_text(json.dumps({'server':DEFAULT_SERVER},indent=2)+'\n',encoding='utf-8')
    # Report version to the person testing a newly installed release.
    print('ACR Club Launcher zainstalowany: wersja', VERSION)
    return target,cfg


def installed_message(title,text):
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,text,title,0x40)
    else:
        print(title, text)
