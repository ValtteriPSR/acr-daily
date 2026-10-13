"""Run the existing server tests against disposable PostgreSQL schemas.

Use TEST_DATABASE_URL, or pass {"url": "..."} through stdin with --stdin.
Never prints credentials. The test role must be able to create schemas.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'server_local'), str(ROOT / 'tests')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stdin', action='store_true')
    args = parser.parse_args()
    if args.stdin:
        import termios
        attributes = termios.tcgetattr(sys.stdin)
        hidden = attributes.copy()
        hidden[3] &= ~termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSANOW, hidden)
        try:
            print('Ready for validation config on stdin (hidden)', flush=True)
            url = json.loads(sys.stdin.readline())['url']
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSANOW, attributes)
    else:
        url = os.environ['TEST_DATABASE_URL']
    import psycopg
    from psycopg import sql
    from urllib.parse import urlsplit, urlunsplit
    # Schema-scoped tests need a direct endpoint, rather than transaction pooling.
    parsed = urlsplit(url)
    url = urlunsplit(parsed._replace(netloc=parsed.netloc.replace('-pooler.', '.')))
    try:
        with psycopg.connect(url, autocommit=True, connect_timeout=15) as probe:
            probe.execute('SELECT 1')
    except psycopg.OperationalError:
        print('PostgreSQL is unreachable from this test environment.', file=sys.stderr)
        return 2
    import server
    from database import PostgresDatabase
    prefix = 'acr_test_' + secrets.token_hex(6) + '_'
    schemas = set()
    databases = []
    original_connect = server.connect_database

    def connect(path):
        schema = prefix + hashlib.sha256(str(path).encode()).hexdigest()[:12]
        if schema not in schemas:
            with psycopg.connect(url, autocommit=True, connect_timeout=15) as connection:
                connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            schemas.add(schema)
        database = PostgresDatabase(url, schema=schema)
        databases.append(database)
        return database

    server.connect_database = connect
    modules = ['test_server', 'test_seasons', 'test_admin', 'test_http',
               'test_season_http', 'test_web_launcher', 'test_v6_public', 'test_steam_auth', 'test_discord_notifications', 'test_rally_details', 'test_update024', 'test_update025', 'test_update026', 'test_update027', 'test_update028', 'test_update029']
    try:
        suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    finally:
        server.connect_database = original_connect
        for database in databases:
            database.close()
        # Only schemas created by this invocation are disposable test data.
        if schemas:
            with psycopg.connect(url, autocommit=True, connect_timeout=15) as connection:
                for schema in schemas:
                    connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__':
    raise SystemExit(main())
