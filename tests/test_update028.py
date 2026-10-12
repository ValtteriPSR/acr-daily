"""Closed-rally expiry, independent A/B save restoration and safe idle RUN."""
import base64,copy,gzip,hashlib,json,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'client'),str(ROOT/'server_local'),str(ROOT/'tests')]
import test_update024 as fixtures
import attempt_updates as updates
from server import Fault,site
from integrity_rules import expected_settings
from club_local import checkpoint_restore,launcher_control
from web_launcher import enroll,mint_ticket,redeem_ticket

class Update028Tests(unittest.TestCase):
    setUp=fixtures.UpdateStoreTests.setUp;tearDown=fixtures.UpdateStoreTests.tearDown
    finish=fixtures.UpdateStoreTests.finish;record=fixtures.UpdateStoreTests.record;payload=fixtures.UpdateStoreTests.payload
    def confirmed_copy(self):
        self.finish(0);updates.stage_result(self.s,self.token,self.record(0))
        raw=json.dumps({'done':1,'settings':self.report,'rally':self.ev['id'],'damage':37}).encode()
        updates.checkpoint(self.s,self.token,self.payload(raw),recovery=True)
        return raw
    def test_expired_rally_deletes_saves_but_preserves_results(self):
        self.confirmed_copy();self.s.db.execute('UPDATE events SET closes=? WHERE id=?',(time.time()-1,self.ev['id']))
        self.s.listing()
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM rally_checkpoints').fetchone()[0],0)
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM results').fetchone()[0],1)
        with self.assertRaises(Fault):updates.checkpoint(self.s,self.token,recovery=True)
    def test_no_save_before_first_or_after_last_stage(self):
        with self.assertRaises(Fault):updates.checkpoint(self.s,self.token,{**self.payload(),'stageIndex':0},recovery=True)
        self.confirmed_copy();self.finish(1)
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM rally_checkpoints').fetchone()[0],0)
        with self.assertRaises(Fault):updates.checkpoint(self.s,self.token,{**self.payload(),'stageIndex':2},recovery=True)
    def test_wrong_car_warns_without_start_and_canonical_reset_needs_no_sav(self):
        with self.assertRaises(Fault):self.s.start(self.token,self.ev['id'],0,'CAR-OUTSIDE-CLASS',self.report)
        self.assertEqual(self.s.state(self.token)['status'],'registered');self.assertTrue(self.s.state(self.token)['recoveryRequired'])
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM provisional').fetchone()[0],0)
        updates.recovery_ack(self.s,self.token,{'settings':self.report})
        self.assertEqual(self.s.start(self.token,self.ev['id'],0,self.car,self.report)['status'],'active')
    def test_two_overlapping_rallies_restore_a_b_a_independently(self):
        a=self.confirmed_copy();evb=copy.deepcopy(self.ev);evb['id']='other-overlapping-rally';evb['name']='Rally B'
        self.s.import_event(evb);tokenb=self.s.join(evb['id'],'AA')['token'];reportb=expected_settings(evb)
        self.s.start(tokenb,evb['id'],0,self.car,reportb);self.s.stage_end(tokenb,evb['id'],0,60000,reportb)
        updates.stage_result(self.s,tokenb,{**self.record(0),'settings':reportb})
        b=json.dumps({'done':1,'settings':reportb,'rally':evb['id'],'damage':62}).encode()
        updates.checkpoint(self.s,tokenb,{**self.payload(b),'settings':reportb},recovery=True)
        save=Path(self.tmp.name)/'current.sav';save.write_bytes(b'OTHER LOCAL SAVE')
        modules=(SimpleNamespace(progress=lambda raw:{'done':json.loads(raw)['done']}),SimpleNamespace(SAVE=str(save),replace=save.write_bytes,game_running=lambda:False))
        for token,ev,raw in [(self.token,self.ev,a),(tokenb,evb,b),(self.token,self.ev,a)]:
            api=SimpleNamespace(call=lambda path,t=token:updates.checkpoint(self.s,t))
            with mock.patch.object(checkpoint_restore,'_game_modules',return_value=modules),mock.patch.object(checkpoint_restore,'_report',side_effect=lambda x:json.loads(x)['settings']):
                checkpoint_restore.restore(api,ev,self.s._auth(token)['id'],self.s.state(token),lambda m:None)
            self.assertEqual(save.read_bytes(),raw)
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM rally_checkpoints').fetchone()[0],2)
    def test_identity_mismatch_is_rechecked_before_replacing_local_save(self):
        raw=self.confirmed_copy();cp=updates.checkpoint(self.s,self.token);save=Path(self.tmp.name)/'current.sav';save.write_bytes(b'PRIVATE')
        api=SimpleNamespace(call=mock.Mock(side_effect=[{**cp,'eventId':'wrong'},cp]))
        modules=(SimpleNamespace(progress=lambda b:{'done':1}),SimpleNamespace(SAVE=str(save),replace=save.write_bytes,game_running=lambda:False));logs=[]
        with mock.patch.object(checkpoint_restore,'_game_modules',return_value=modules),mock.patch.object(checkpoint_restore,'_report',return_value=self.report):
            checkpoint_restore.restore(api,self.ev,self.s._auth(self.token)['id'],self.s.state(self.token),logs.append)
        self.assertEqual(api.call.call_count,2);self.assertEqual(save.read_bytes(),raw);self.assertTrue(logs[0].startswith('OSTRZEŻENIE:'))
    def test_dnf_identifies_second_stage(self):
        self.finish(0);self.s.start(self.token,self.ev['id'],1,self.car,self.report);self.s.dnf(self.token,'Restart')
        self.assertEqual(self.s.state(self.token)['dnfStage'],2);self.assertEqual(self.s.board(self.ev['id'])['players'][0]['dnfStage'],2)
        self.assertIn('DNF · OS 2',site(self.s,self.ev['id']))
    def test_idle_existing_launcher_can_receive_run_but_active_cannot(self):
        cookie=enroll(self.s,self.ev['id'],'New driver');ticket=mint_ticket(self.s,cookie,self.ev['id']);launch=redeem_ticket(self.s,ticket)
        ticket2=mint_ticket(self.s,cookie,self.ev['id']);self.assertTrue(ticket2)
        self.s.start(launch['token'],self.ev['id'],0,self.car,self.report)
        with self.assertRaises(Fault):mint_ticket(self.s,cookie,self.ev['id'])

class LauncherControlTests(unittest.TestCase):
    def test_restart_guard_blocks_active_game_and_unconfirmed_progress(self):
        mon=SimpleNamespace(status='active');self.assertIn('aktywny',launcher_control.restart_problem(mon,False))
        self.assertIn('zamknij grę',launcher_control.restart_problem(None,True))
        mon=SimpleNamespace(status='ready',event={'allowBreaks':True},recovery_required=False,checkpoint_sent=False,snapshot_digest=None)
        self.assertIn('Brak potwierdzonej',launcher_control.restart_problem(mon,False))
        mon.snapshot_digest='confirmed';self.assertIsNone(launcher_control.restart_problem(mon,False))
        mon.event['allowBreaks']=False;self.assertIn('na raz',launcher_control.restart_problem(mon,False))
    def test_handoff_uses_bounded_json_and_validates_before_queueing(self):
        calls=[];conn=mock.Mock();conn.recv_bytes.return_value=json.dumps({'link':'valid'}).encode()
        launcher_control.serve_connection(conn,calls.append,lambda x:None)
        self.assertEqual(calls,['valid']);conn.recv_bytes.assert_called_once_with(4096);conn.close.assert_called_once()
        conn=mock.Mock();conn.recv_bytes.return_value=b'{"link":"bad","execute":"forbidden"}'
        with self.assertRaises(ValueError):launcher_control.serve_connection(conn,calls.append,lambda x:None)
        self.assertEqual(calls,['valid'])
