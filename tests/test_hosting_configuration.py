"""Protect generated credentials and validate destination hosting settings."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_hosting', ROOT / 'deploy/configure_hosting.py')
hosting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosting)


class HostingConfigurationTests(unittest.TestCase):
    def test_domain_rejects_configuration_injection_and_paths(self):
        self.assertEqual(hosting.validate_domain('League.Example.com'), 'league.example.com')
        for bad in ('https://example.com', 'example.com/path', 'example.com:443',
                    'example.com\nEVIL=1', '-example.com', 'example..com'):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                hosting.validate_domain(bad)

    def test_password_hash_matches_generated_password(self):
        import bcrypt
        content, access = hosting.make_configuration(
            'league.example.com', 'https://github.com/example/club/releases/download/v0.2/setup.exe')
        hash_line = next(line for line in content.splitlines() if line.startswith('ADMIN_PASSWORD_HASH='))
        password_hash = hash_line.split('=', 1)[1][1:-1]
        self.assertTrue(bcrypt.checkpw(access['password'].encode(), password_hash.encode()))
        self.assertNotIn(access['password'], content)
        self.assertTrue(access['url'].startswith('https://league.example.com/panel-'))
        self.assertGreaterEqual(len(access['key']), 32)

    def test_credentials_are_private_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            hosting.write_configuration(path, 'PRIVATE=first\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                hosting.write_configuration(path, 'PRIVATE=second\n')
            self.assertEqual(path.read_text(), 'PRIVATE=first\n')

    def test_environment_rejects_newline_injection(self):
        for bad in ('value\nEVIL=1', 'value\x00', 'value\r'):
            with self.assertRaises(ValueError):
                hosting.dotenv_value(bad)
        self.assertEqual(hosting.dotenv_value('$2b$12$example'), "'$2b$12$example'")


if __name__ == '__main__':
    unittest.main()
