"""Regression tests for the previously missing upstream catalogs & source packaging."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server_local'))
from admin_panel import load_catalog, validate_catalog_event


def load_tool(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/'tools'/f'{name}.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StandaloneTests(unittest.TestCase):
    def test_catalog_bundle_contains_exact_expected_ids(self):
        c=load_catalog(ROOT)
        self.assertEqual(len(c['cars']), 18)
        self.assertEqual(len(c['stages']), 44)
        self.assertIn('VWPoloGTIR5', {x['id'] for x in c['cars']})
        self.assertIn('GreeceS3ElatiaCut2Reverse', {x['id'] for x in c['stages']})
        self.assertIn('WelesS4HafrenSouthFullReverse', {x['id'] for x in c['stages']})

    def test_bundled_js_identical_to_pinned_acr_daily(self):
        tool=load_tool('vendor_acr_daily')
        self.assertEqual(tool.git_blob_hash((ROOT/'server/src/cars.js').read_bytes()),
                         '10356ad23f2b04b8c801c6b0098685777bcca70e')
        self.assertEqual(tool.git_blob_hash((ROOT/'server/src/stages.js').read_bytes()),
                         '5d9a45dac6cb932709d3cdbab81e61775d170715')

    def test_snapshot_has_same_ids_as_js_files(self):
        c=load_catalog(ROOT)
        snap=json.loads((ROOT/'server_local/catalog_snapshot.json').read_text(encoding='utf8'))
        self.assertEqual({x['id'] for x in c['cars']},{x['id'] for x in snap['cars']})
        self.assertEqual({x['id'] for x in c['stages']},{x['id'] for x in snap['stages']})

    def test_preflight_succeeds_on_clean_release_tree(self):
        pre=load_tool('preflight')
        self.assertEqual(pre.check_server(),[])

    def test_vendor_rejects_tampered_modules(self):
        tool=load_tool('vendor_acr_daily')
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'names.py'
            with self.assertRaises(ValueError):
                tool.install('names.py', b'print("malicious")', target)
            self.assertFalse(target.exists())

    def test_vendor_blob_sha_formula(self):
        tool=load_tool('vendor_acr_daily')
        self.assertEqual(tool.git_blob_hash(b'test\n'),'9daeafb9864cf43055ae93beb0afd6c7d144bfa4')

    def test_upstream_files_are_not_forged(self):
        # Upstream client modules are obtained with git-blob verification,
        # not silently replaced with stubs that could corrupt game save files.
        tool=load_tool('vendor_acr_daily')
        self.assertEqual(len(tool.BLOBS),6)
        self.assertIn('settings.py',tool.BLOBS)
        self.assertNotIn('autodrive.py',tool.BLOBS)
        self.assertTrue(all(len(v)==40 for v in tool.BLOBS.values()))

if __name__=='__main__':
    unittest.main()
