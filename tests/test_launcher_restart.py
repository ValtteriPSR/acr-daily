"""A RUN restart must outlive its parent's PyInstaller extraction."""
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client'))
from club_local import launcher_process


class LauncherRestartTests(unittest.TestCase):
    def test_frozen_restart_is_independent_and_preserves_ticket_as_one_argument(self):
        link = 'acrclub://start?ticket=' + 'a' * 43
        original = dict(os.environ)
        with mock.patch.object(sys, 'frozen', True, create=True), \
             mock.patch.object(launcher_process.subprocess, 'Popen') as spawn:
            launcher_process.start_independent([link])
        args, kwargs = spawn.call_args
        self.assertEqual(args[0], [sys.executable, link])
        self.assertEqual(kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        self.assertEqual(kwargs['env'].get('PATH'), original.get('PATH'))
        self.assertEqual(dict(os.environ), original)
        self.assertNotIn('shell', kwargs)

    def test_source_restart_uses_source_entrypoint_without_changing_environment(self):
        with mock.patch.object(sys, 'frozen', False, create=True), \
             mock.patch.object(launcher_process.subprocess, 'Popen') as spawn:
            launcher_process.start_independent(['acrclub://tools'])
        args, kwargs = spawn.call_args
        self.assertEqual(args[0], [
            sys.executable, str(ROOT / 'client/run_web_launcher.py'), 'acrclub://tools'])
        self.assertEqual(kwargs['env'], dict(os.environ))


if __name__ == '__main__':
    unittest.main()
