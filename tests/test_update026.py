"""Restore the personal Club checkpoint over an unrelated local weekend."""
import base64
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace,ModuleType
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'client'),str(ROOT/'server_local'),str(ROOT/'tests')]
import test_update024 as fixtures
import attempt_updates
from club_local import checkpoint_restore
from web_launcher import abort_prestart,digest


class RestoreTests(unittest.TestCase):
    setUp=fixtures.UpdateStoreTests.setUp
    tearDown=fixtures.UpdateStoreTests.tearDown
    finish=fixtures.UpdateStoreTests.finish
    record=fixtures.UpdateStoreTests.record
    payload=fixtures.UpdateStoreTests.payload

    def prepare_copy(self,legacy=False):
        if legacy:
            self.ev.pop('launcherProtocol');self.ev.pop('allowBreaks')
            self.s.db.execute('UPDATE events SET config=? WHERE id=?',(json.dumps(self.ev),self.ev['id']))
        self.finish(0);attempt_updates.stage_result(self.s,self.token,self.record(0))
        raw=json.dumps({'club':self.ev['id'],'done':1,'carDamage':37,'settings':self.report}).encode()
        attempt_updates.checkpoint(self.s,self.token,self.payload(raw))
        return raw

    def restore(self,raw,override=None,missing=False):
        save=Path(self.tmp.name)/'player.sav';backup=Path(self.tmp.name)/'private-backup.sav'
        if not missing:save.write_bytes(b'UNRELATED PRIVATE RALLY IN PROGRESS')
        def replace(data):
            backup.write_bytes(save.read_bytes());save.write_bytes(data)
        modules=(SimpleNamespace(progress=lambda b:{'done':json.loads(b)['done']}),
                 SimpleNamespace(SAVE=str(save),replace=replace,game_running=lambda:False))
        response=attempt_updates.checkpoint(self.s,self.token)
        if override:response.update(override)
        api=SimpleNamespace(call=mock.Mock(return_value=response))
        with mock.patch.object(checkpoint_restore,'_game_modules',return_value=modules),mock.patch.object(checkpoint_restore,'_report',side_effect=lambda b:json.loads(b)['settings']):
            with mock.patch.object(checkpoint_restore,'_validate',return_value=None),mock.patch.object(checkpoint_restore,'_install',side_effect=replace if not missing else lambda b:save.write_bytes(b)),mock.patch('club_local.save_safety.state',return_value={}),mock.patch('club_local.save_safety.record'):
                result=checkpoint_restore.restore(api,self.ev,self.s._auth(self.token)['id'],self.s.state(self.token),lambda s:None)
        return result,save,backup

    def test_server_copy_has_priority_over_private_weekend_without_local_session(self):
        for legacy in (False,True):
            with self.subTest(legacy=legacy):
                # Independent fixtures: an old-format event must restore too.
                if legacy:
                    self.ev.pop('launcherProtocol');self.ev.pop('allowBreaks')
                    self.s.db.execute('UPDATE events SET config=? WHERE id=?',(json.dumps(self.ev),self.ev['id']))
                    raw=self.raw
                else:
                    raw=self.prepare_copy();self.raw=raw
                result,save,backup=self.restore(raw)
                self.assertEqual(save.read_bytes(),raw)
                self.assertEqual(backup.read_bytes(),b'UNRELATED PRIVATE RALLY IN PROGRESS')
                self.assertEqual(result['playerId'],self.s._auth(self.token)['id'])
                self.assertEqual(json.loads(save.read_bytes())['done'],1)
                self.assertEqual(json.loads(save.read_bytes())['carDamage'],37)

    def test_bad_owner_event_progress_or_hash_cannot_replace_private_save(self):
        raw=self.prepare_copy()
        for change in ({'playerId':999},{'eventId':'other-rally'},{'stageIndex':0},{'digest':'bad'}):
            with self.subTest(change=change),self.assertRaises(RuntimeError):self.restore(raw,change)
            self.assertEqual((Path(self.tmp.name)/'player.sav').read_bytes(),b'UNRELATED PRIVATE RALLY IN PROGRESS')

    def test_missing_local_file_is_created_from_personal_checkpoint(self):
        raw=self.prepare_copy();result,save,backup=self.restore(raw,missing=True)
        self.assertEqual(save.read_bytes(),raw);self.assertFalse(backup.exists())

    def test_same_calendar_with_wrong_saved_progress_does_not_replace_local_file(self):
        self.prepare_copy()
        wrong=json.dumps({'done':0,'settings':self.report}).encode()
        change={'save':base64.b64encode(gzip.compress(wrong)).decode(),'digest':hashlib.sha256(wrong).hexdigest()}
        with self.assertRaisesRegex(RuntimeError,'właściwym OS'):self.restore(wrong,change)
        self.assertEqual((Path(self.tmp.name)/'player.sav').read_bytes(),b'UNRELATED PRIVATE RALLY IN PROGRESS')

    def test_new_protocol_does_not_fall_back_to_unrelated_local_save(self):
        self.prepare_copy()
        with self.assertRaisesRegex(RuntimeError,'Brak zatwierdzonej kopii'):self.restore(b'',{'available':False})

    def test_resume_preparation_abort_releases_lease_without_resetting_os1(self):
        self.prepare_copy();p=self.s._auth(self.token)
        self.s.db.execute('INSERT OR REPLACE INTO launch_leases(player_id,expires) VALUES(?,?)',(p['id'],9999999999))
        self.assertEqual(abort_prestart(self.s,self.token)['status'],'ready')
        self.assertIsNone(self.s.db.execute('SELECT * FROM launch_leases WHERE player_id=?',(p['id'],)).fetchone())
        row=self.s.db.execute('SELECT stage_index,status FROM players WHERE id=?',(p['id'],)).fetchone()
        self.assertEqual(row['stage_index'],1);self.assertEqual(row['status'],'ready')
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM results WHERE player_id=?',(p['id'],)).fetchone()[0],1)


class WriterTests(unittest.TestCase):
    def test_private_weekend_is_parked_only_with_explicit_first_run_priority(self):
        # Load the actual Club writer independently of test_monitor's telemetry stubs.
        spec=importlib.util.spec_from_file_location('acr_daily.rallyclub_026test',ROOT/'client/acr_daily/rallyclub.py')
        module=importlib.util.module_from_spec(spec)
        package=ModuleType('acr_daily');package.__path__=[]
        rw=ModuleType('acr_daily.rallyweekend');sv=ModuleType('acr_daily.saveslot');sv.SaveError=ValueError
        with mock.patch.dict(sys.modules,{'acr_daily':package,'acr_daily.rallyweekend':rw,'acr_daily.saveslot':sv}):
            spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.sav';path.write_bytes(b'PRIVATE WITH PROGRESS')
            saved=[]
            def replace(b):saved.append(path.read_bytes());path.write_bytes(b)
            module.saveslot=SimpleNamespace(SAVE=str(path),game_running=lambda:False,replace=replace)
            module.rw=SimpleNamespace(read_weekend=lambda b:{'in_progress':True},park=mock.Mock(return_value=(b'PARKED CONFIGURATION',b'PRIVATE CONTEXT')))
            with mock.patch.object(module,'validate_event'),mock.patch.object(module,'apply_club_weekend',return_value=b'CLUB CALENDAR') as apply:
                with mock.patch('club_local.save_safety.preflight',return_value=b'PRIVATE WITH PROGRESS'),mock.patch('club_local.save_layout.inspect'),mock.patch('club_local.save_layout.park',return_value=b'PARKED CONFIGURATION'),mock.patch('club_local.save_layout.preserve_other_sections'),mock.patch('club_local.save_safety.replace',side_effect=lambda b,**kw:replace(b)),mock.patch('club_local.save_safety.state',return_value={}),mock.patch('club_local.save_safety.record'):
                    module.write_club_weekend({'stages':[{},{}]},'car',replace_in_progress=True)
                self.assertEqual(apply.call_args.args[0],b'PARKED CONFIGURATION')
                self.assertEqual(saved,[b'PRIVATE WITH PROGRESS'])
                self.assertEqual(path.read_bytes(),b'CLUB CALENDAR')
