"""Failure-path checks for preserving the last verified recovery point."""
import hashlib
import importlib.util
import types
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('scheduled_backup', Path(__file__).with_name('backup.py'))
backup = importlib.util.module_from_spec(spec); spec.loader.exec_module(backup)


class Store:
    def __init__(self, corrupt=False, fail=False):
        self.values = {'latest/database.dump': b'old verified backup'}
        self.corrupt = corrupt; self.fail = fail; self.writes = []
    def put_object(self, ns, bucket, name, data, **kwargs):
        self.writes.append(name)
        if self.fail:
            raise RuntimeError('upload failed')
        self.values[name] = data
    def get_object(self, ns, bucket, name):
        value = self.values[name]
        data = b'bad bytes' if self.corrupt and name.startswith('scheduled/') else value
        return types.SimpleNamespace(data=types.SimpleNamespace(content=data, close=lambda: None),
                                     headers={'etag': 'previous-etag',
                                              'opc-meta-sha256': hashlib.sha256(value).hexdigest()})


class BackupTests(unittest.TestCase):
    def test_verified_upload_replaces_latest_only_after_history(self):
        store = Store(); result = backup.publish(store, 'ns', 'bucket', 'database', b'new dump')
        self.assertTrue(store.writes[0].startswith('scheduled/database/'))
        self.assertEqual(store.writes[1], 'latest/database.dump')
        self.assertEqual(store.values[result['latest']], b'new dump')
    def test_corrupt_readback_preserves_latest(self):
        store = Store(corrupt=True)
        with self.assertRaises(ValueError): backup.publish(store, 'ns', 'bucket', 'database', b'new dump')
        self.assertEqual(store.values['latest/database.dump'], b'old verified backup')
        self.assertEqual(len(store.writes), 1)
    def test_failed_upload_preserves_latest(self):
        store = Store(fail=True)
        with self.assertRaises(RuntimeError): backup.publish(store, 'ns', 'bucket', 'database', b'new dump')
        self.assertEqual(store.values['latest/database.dump'], b'old verified backup')
    def test_history_and_latest_are_stored_in_separate_buckets(self):
        store = Store(); calls = []
        original = store.put_object
        def put(ns, bucket, name, data, **kwargs):
            calls.append((bucket, name)); original(ns, bucket, name, data, **kwargs)
        store.put_object = put
        with patch.dict(backup.os.environ, {'ACR_BACKUP_HISTORY_BUCKET': 'history-only'}):
            backup.publish(store, 'ns', 'protected-latest', 'database', b'dump')
        self.assertEqual([x[0] for x in calls], ['history-only', 'protected-latest'])
    def test_invalid_dump_is_rejected_without_postgres(self):
        with patch.object(backup, 'run') as run:
            with self.assertRaises(ValueError): backup.validate_dump(b'not a dump')
            run.assert_not_called()
    def test_restore_failure_drops_only_disposable_database(self):
        calls = []
        def run(*args, **kwargs):
            calls.append(args)
            if 'pg_restore' in args: raise RuntimeError('restore failed')
            return b''
        with patch.object(backup, 'validate_dump'), patch.object(backup, 'run', side_effect=run):
            with self.assertRaises(RuntimeError): backup.restore_test(b'dump')
        create = next(x for x in calls if 'createdb' in x)
        drop = next(x for x in calls if 'dropdb' in x)
        self.assertEqual(create[-1], drop[-1])
        self.assertTrue(drop[-1].startswith('acr_backup_verify_'))
        self.assertNotEqual(drop[-1], 'acr_club')
    def test_cleanup_does_not_target_migration_or_latest(self):
        import json
        rules = json.loads(Path(__file__).with_name('lifecycle.json').read_text())['items']
        self.assertEqual({tuple(x['objectNameFilter']['inclusionPrefixes']) for x in rules},
                         {('scheduled/database/',), ('scheduled/full/',)})
        self.assertEqual({x['timeAmount'] for x in rules}, {2, 7})


if __name__ == '__main__': unittest.main()
