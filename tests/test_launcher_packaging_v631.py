"""Regressions: the V6.3.0 Windows EXE missed acr_daily.settings."""
import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def get_script(name):
    spec=importlib.util.spec_from_file_location('local_vendor_'+name,ROOT/'tools'/f'{name}.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LauncherPackaging631(unittest.TestCase):
    def test_original_settings_is_included_and_unmodified(self):
        vendor=get_script('vendor_acr_daily')
        path=ROOT/'client/acr_daily/settings.py'
        self.assertTrue(path.is_file())
        self.assertEqual(vendor.git_blob_hash(path.read_bytes()),vendor.BLOBS['settings.py'])
        self.assertEqual(vendor.BLOBS['settings.py'],'43190f45f508ad2375879667b1de81ae510d403a')

    def test_web_launcher_has_static_settings_import(self):
        p=ROOT/'client/club_local/web_launch.py'
        parsed=ast.parse(p.read_text(encoding='utf8'))
        imports=[(node.module,[alias.name for alias in node.names]) for node in ast.walk(parsed)
                 if isinstance(node,ast.ImportFrom)]
        self.assertTrue(any(module=='acr_daily' and 'settings' in names for module,names in imports))

    def test_build_scripts_verify_before_and_after_freezing(self):
        bat=(ROOT/'build_web_launcher_exe.bat').read_text(encoding='utf8')
        self.assertIn('vendor_acr_daily.py',bat)
        self.assertLess(bat.index('verify_launcher_modules.py'),bat.index('-m PyInstaller --noconfirm'))
        self.assertIn('--hidden-import acr_daily.settings',bat)
        self.assertIn('--collect-submodules acr_daily',bat)
        self.assertIn('ACR-Club-Launcher.exe" --self-test',bat)
        script=(ROOT/'client/run_web_launcher.py').read_text(encoding='utf8')
        self.assertIn('def self_test()',script)
        self.assertIn("sys.argv[1] == '--self-test'",script)

    def test_github_release_checks_frozen_exe_before_publishing(self):
        workflow=(ROOT/'.github/workflows/launcher-release.yml').read_text(encoding='utf8')
        self.assertIn('vendor_acr_daily.py --download',workflow)
        self.assertIn('verify_launcher_modules.py',workflow)
        self.assertIn('--hidden-import acr_daily.settings',workflow)
        self.assertIn("-ArgumentList '--self-test' -Wait -PassThru",workflow)

    def test_version_gate_blocks_old_clients(self):
        spec=importlib.util.spec_from_file_location('security631',ROOT/'server_local/public_security.py')
        sec=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sec)
        self.assertEqual(sec.MIN_LAUNCHER_VERSION,'0.2.0')
        self.assertFalse(sec.version_allowed('0.1.9'))
        self.assertTrue(sec.version_allowed('0.2.0'))
        self.assertTrue(sec.version_allowed('0.2.3'))
        self.assertFalse(sec.version_allowed('6.3.0'))
        self.assertTrue(sec.version_allowed('6.3.1'))
        for bad in ('0.2', 'v0.2.0', 'invalid', None):
            self.assertFalse(sec.version_allowed(bad))
        self.assertEqual((ROOT/'VERSION').read_text().strip(), '0.2.3')

if __name__=='__main__':unittest.main()
