"""Private administrator URL, distinct from API authorization."""
import os
import re
import secrets
from pathlib import Path


def admin_path(key_path):
    custom = os.environ.get('ACR_ADMIN_PATH', '').strip()
    path_file = Path(key_path).parent / 'admin_route.txt'
    if custom:
        if not re.fullmatch(r'/panel-[a-z0-9-]{12,80}', custom):
            raise RuntimeError('ACR_ADMIN_PATH must be /panel- followed by 12-80 lowercase letters, digits or hyphens')
        return custom
    path_file.parent.mkdir(parents=True, exist_ok=True)
    if not path_file.exists():
        generated='/panel-'+secrets.token_hex(16)
        try:
            fd=os.open(path_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w',encoding='ascii') as out: out.write(generated+'\n')
        except FileExistsError:
            pass
    path=path_file.read_text(encoding='ascii').strip()
    if not re.fullmatch(r'/panel-[a-z0-9-]{12,80}',path):
        raise RuntimeError('Invalid administrator route in admin_route.txt')
    return path
