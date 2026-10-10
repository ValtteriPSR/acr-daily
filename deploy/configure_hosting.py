"""Create private Compose settings on the destination host, never in GitHub."""
from __future__ import annotations
import argparse
import getpass
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit


def validate_domain(value):
    value = value.strip().lower()
    if len(value) > 253 or '.' not in value:
        raise ValueError('Use a DNS hostname such as league.example.com')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
           for label in value.split('.')):
        raise ValueError('Use a DNS hostname without a scheme, path or port')
    return value


def dotenv_value(value):
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Environment values must not contain control characters')
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


def make_configuration(domain, download_url, database_url=''):
    import bcrypt
    domain = validate_domain(domain)
    download = urlsplit(download_url)
    if (download.scheme != 'https' or download.netloc != 'github.com'
            or download.query or download.fragment or not re.fullmatch(
                r'/[^/]+/[^/]+/releases/(?:tag/[^/]+|download/[^/]+/[^/]+|latest(?:/download/[^/]+)?)', download.path)):
        raise ValueError('Use a public GitHub release page or asset URL')
    if database_url:
        database = urlsplit(database_url)
        if database.scheme not in ('postgres', 'postgresql') or not database.hostname:
            raise ValueError('DATABASE_URL must be a PostgreSQL connection URL')
    password = secrets.token_urlsafe(24)
    values = {
        'CLUB_DOMAIN': domain,
        'DATABASE_URL': database_url,
        'ACR_MIN_LAUNCHER_VERSION': '0.2.0',
        'ADMIN_PANEL_PATH': '/panel-' + secrets.token_hex(16),
        'ACR_ADMIN_KEY': secrets.token_urlsafe(40),
        'ACR_GATEWAY_SECRET': secrets.token_hex(32),
        'ADMIN_PASSWORD_HASH': bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        'ACR_LAUNCHER_DOWNLOAD_URL': download_url,
    }
    content = '# Private hosting configuration. Never upload or commit this file.\n'
    content += ''.join(key + '=' + dotenv_value(value) + '\n' for key, value in values.items())
    return content, {'url': 'https://' + domain + values['ADMIN_PANEL_PATH'],
                     'username': 'admin', 'password': password,
                     'key': values['ACR_ADMIN_KEY']}


def write_configuration(output, content):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite credentials, including symlinks to an existing file.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--download-url', required=True,
                        help='GitHub release containing an EXE compiled for this domain')
    parser.add_argument('--postgres', action='store_true',
                        help='Prompt privately for an existing PostgreSQL URL')
    parser.add_argument('--output', default='deploy/.env')
    args = parser.parse_args()
    database_url = getpass.getpass('PostgreSQL DATABASE_URL (hidden): ') if args.postgres else ''
    content, access = make_configuration(args.domain, args.download_url, database_url)
    write_configuration(args.output, content)
    print('Configuration saved:', args.output)
    print('Save the following private access details in your password manager:')
    print('Administrator URL:', access['url'])
    print('Browser username:', access['username'])
    print('Browser password:', access['password'])
    print('Application administrator key:', access['key'])
    print('Existing club credentials have not been changed.')


if __name__ == '__main__':
    main()
