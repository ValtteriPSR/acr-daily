"""Recover idle settings mistakes without granting a second stage attempt."""
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'client'),str(ROOT/'server_local'),str(ROOT/'tests')]
import test_update024 as fixtures
import attempt_updates as updates
from club_local import checkpoint_restore
from server import Fault,site

class RecoveryTests(unittest.TestCase):
    setUp=fixtures.UpdateStoreTests.setUp
    tearDown=fixtures.UpdateStoreTests.tearDown
    finish=fixtures.UpdateStoreTests.finish
    record=fixtures.UpdateStoreTests.record
    payload=fixtures.UpdateStoreTests.payload

    def test_before_os1_keeps_attempt_and_requires_confirmed_restore(self):
        bad=copy.deepcopy(self.report);bad['rules']['damage']=1-bad['rules']['damage']
        with self.assertRaises(Fault):self.s.start(self.token,self.ev['id'],0,self.car,bad)
        state=self.s.state(self.token)
        self.assertEqual(state['status'],'registered');self.assertTrue(state['recoveryRequired'])
        self.assertFalse(state['results'])
        with self.assertRaises(Fault):self.s.start(self.token,self.ev['id'],0,self.car,self.report)
        data={**self.payload(b'canonical-first-start'),'stageIndex':0}
        updates.checkpoint(self.s,self.token,data,recovery=True)
        with self.assertRaises(Fault):updates.recovery_ack(self.s,self.token,{'digest':'wrong','settings':self.report})
        updates.recovery_ack(self.s,self.token,{'digest':data['digest'],'settings':self.report})
        self.assertEqual(self.s.start(self.token,self.ev['id'],0,self.car,self.report)['status'],'active')

    def test_after_os1_restore_preserves_results_penalties_and_progress(self):
        self.finish(0);rec=self.record(0);updates.stage_result(self.s,self.token,rec)
        raw=json.dumps({'done':1,'settings':self.report,'damage':37}).encode()
        data=self.payload(raw);updates.checkpoint(self.s,self.token,data,recovery=True)
        self.s.integrity_violation(self.token,'Changed damage and stages in menu')
        state=self.s.state(self.token)
        self.assertEqual((state['status'],state['stage_index']),('ready',1));self.assertTrue(state['recoveryRequired'])
        with self.assertRaises(Fault):self.s.start(self.token,self.ev['id'],1,self.car,self.report)
        with self.assertRaises(Fault):updates.stage_result(self.s,self.token,rec)
        with self.assertRaises(Fault):updates.checkpoint(self.s,self.token,self.payload(b'new-invalid-copy'),recovery=True)
        save=Path(self.tmp.name)/'local.sav';save.write_bytes(b'CHANGED PRIVATE CALENDAR')
        def call(path,payload=None):
            if path=='/api/recovery-checkpoint':return updates.checkpoint(self.s,self.token,payload,recovery=True)
            if path=='/api/recovery-ack':return updates.recovery_ack(self.s,self.token,payload)
            raise AssertionError(path)
        modules=(SimpleNamespace(progress=lambda b:{'done':json.loads(b)['done']}),SimpleNamespace(SAVE=str(save),game_running=lambda:False,replace=save.write_bytes))
        with mock.patch.object(checkpoint_restore,'_game_modules',return_value=modules),mock.patch.object(checkpoint_restore,'_report',side_effect=lambda b:json.loads(b)['settings']):
            checkpoint_restore.restore(SimpleNamespace(call=call),self.ev,self.s._auth(self.token)['id'],state,lambda m:None)
        self.assertEqual(save.read_bytes(),raw)
        current=self.s.state(self.token);self.assertFalse(current['recoveryRequired']);self.assertEqual(current['results'][0]['penalty_ms'],1000)
        self.assertEqual(self.s.start(self.token,self.ev['id'],1,self.car,self.report)['status'],'active')
        with self.assertRaises(Fault):self.s.start(self.token,self.ev['id'],0,self.car,self.report)

    def test_missing_os1_copy_never_reconstructs_or_restarts_stage(self):
        self.finish(0);updates.stage_result(self.s,self.token,self.record(0))
        self.s.integrity_violation(self.token,'Changed calendar')
        api=SimpleNamespace(call=lambda p:updates.checkpoint(self.s,self.token,recovery=True))
        with self.assertRaisesRegex(RuntimeError,'Brak zatwierdzonej kopii'):
            checkpoint_restore.restore(api,self.ev,self.s._auth(self.token)['id'],self.s.state(self.token),lambda m:None)
        self.assertEqual(self.s.state(self.token)['stage_index'],1)

    def test_all_idle_setting_mismatches_warn_without_accepting_times(self):
        for mutate in (lambda x:x['rules'].update(damage=9),lambda x:x['stages'][0].update(weather=99),lambda x:x['stages'][0].update(stage='Wrong')):
            bad=copy.deepcopy(self.report);mutate(bad)
            with self.assertRaises(Fault):self.s.start(self.token,self.ev['id'],0,self.car,bad)
            self.assertEqual(self.s.state(self.token)['status'],'registered')
            self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM provisional').fetchone()[0],0)

    def test_active_stage_and_one_sitting_mismatches_still_dnf(self):
        self.s.start(self.token,self.ev['id'],0,self.car,self.report)
        self.s.integrity_violation(self.token,'Settings changed during SS')
        self.assertEqual(self.s.state(self.token)['status'],'dnf')
        token=self.s.join(self.ev['id'],'Second')['token']
        cfg={**self.ev,'allowBreaks':False};self.s.db.execute('UPDATE events SET config=? WHERE id=?',(json.dumps(cfg),self.ev['id']))
        self.s.integrity_violation(token,'Settings changed')
        self.assertEqual(self.s.state(token)['status'],'dnf')

    def test_live_page_warns_in_yellow_without_dnf_or_unsafe_reason(self):
        self.s.integrity_violation(self.token,'<script>bad</script>')
        html=site(self.s,self.ev['id'])
        self.assertIn('PRZYWRÓĆ PRZEZ RUN',html);self.assertIn('rally-recovery-warning',html)
        self.assertIn('#ffd166',html);self.assertNotIn('<script>bad</script>',html)
        self.assertEqual(self.s.board(self.ev['id'])['players'][0]['status'],'registered')
