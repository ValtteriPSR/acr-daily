"""Live traces, retention, administrative sanctions and derived rankings."""
import copy,json,sys,time,threading,unittest,math
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'client'),str(ROOT/'server_local'),str(ROOT/'tests')]
import test_update024 as fixtures
import attempt_updates,admin_penalties,telemetry_audit as audit
from server import Fault,site
from integrity_rules import expected_settings
from club_local.trace_sender import TraceSender
from i18n import _language


import timing_guard  # testy symulują OS natychmiast; zegar serwera sprawdza test_projectsimracing.py
timing_guard.HARD_LIMIT_MS = timing_guard.REVIEW_LIMIT_MS = float('inf')

def point(t,x=0,z=0,speed=50):return [t,x,z,speed,.5,.1,0,2,4000,False]

class Update029Tests(unittest.TestCase):
    setUp=fixtures.UpdateStoreTests.setUp;tearDown=fixtures.UpdateStoreTests.tearDown
    finish=fixtures.UpdateStoreTests.finish;record=fixtures.UpdateStoreTests.record;payload=fixtures.UpdateStoreTests.payload
    def batch(self,points=None,seq=0,idx=0):return {'eventId':self.ev['id'],'stageIndex':idx,'seq':seq,'points':points or [point(1000),point(2000,10)],'dropped':0}
    def start(self):self.s.start(self.token,self.ev['id'],0,self.car,self.report)
    def finish_driver(self,token,raw=60000):
        records=[]
        for idx in range(2):
            self.s.start(token,self.ev['id'],idx,self.car,self.report);self.s.stage_end(token,self.ev['id'],idx,raw,self.report)
            rec={**self.record(idx),'rawMs':raw,'penaltyMs':0,'totalMs':raw};records.append(rec)
            attempt_updates.stage_result(self.s,token,rec)
        self.s.finalize(token,{'stages':records,'settings':self.report})
    def test_trace_is_persisted_while_driver_is_still_on_stage(self):
        self.start();audit.submit(self.s,self.token,self.batch())
        self.assertEqual(self.s.state(self.token)['status'],'active');self.assertFalse(self.s.state(self.token)['results'])
        self.assertEqual(self.s.db.execute('SELECT point_count FROM telemetry_runs').fetchone()[0],2)
        self.assertIn('polyline',audit.driver(self.s,self.ev['id'],self.s._auth(self.token)['id']))
    def test_registration_and_run_without_stage_start_are_hidden(self):
        pid=self.s._auth(self.token)['id']
        text=audit.summaries(self.s,self.ev['id'])
        self.assertNotIn('trace-driver',text)
        self.assertEqual(audit.driver(self.s,self.ev['id'],pid),'')
        self.s.db.execute("UPDATE players SET status='ready' WHERE id=?",(pid,))
        self.assertNotIn('trace-driver',audit.summaries(self.s,self.ev['id']))
        self.assertEqual(audit.driver(self.s,self.ev['id'],pid),'')
        self.start()
        for page in (audit.summaries(self.s,self.ev['id']),audit.driver(self.s,self.ev['id'],pid)):
            self.assertIn('Zawodnik nie ukończył jeszcze wszystkich OS.',page)
        self.assertIn('trace-driver',audit.summaries(self.s,self.ev['id']))

    def test_progress_survives_service_and_dnf_without_samples(self):
        pid=self.s._auth(self.token)['id']
        self.start();self.s.stage_end(self.token,self.ev['id'],0,60000,self.report)
        self.assertIsNone(self.s._auth(self.token)['started'])
        self.assertIn('Zawodnik nie ukończył jeszcze wszystkich OS.',audit.summaries(self.s,self.ev['id']))
        self.s.start(self.token,self.ev['id'],1,self.car,self.report)
        self.s.dnf(self.token,'Driver retired during the next stage')
        for page in (audit.summaries(self.s,self.ev['id']),audit.driver(self.s,self.ev['id'],pid)):
            self.assertIn('DNF — zawodnik nie ukończył rajdu.',page)
            self.assertNotIn('Zawodnik nie ukończył jeszcze wszystkich OS.',page)

    def test_confirmation_pending_and_completed_statuses_in_both_languages(self):
        self.finish(0);self.finish(1)
        pid=self.s._auth(self.token)['id']
        self.assertEqual(self.s.state(self.token)['status'],'awaiting_results')
        self.assertIn('oczekiwanie na potwierdzenie',audit.summaries(self.s,self.ev['id']))
        self.s.finalize(self.token,{'stages':[self.record(0),self.record(1)],'settings':self.report})
        for lang,text in [('pl','Rajd ukończony.'),('en','Rally completed.')]:
            context=_language.set(lang)
            try:
                self.assertIn(text,audit.summaries(self.s,self.ev['id']))
                self.assertIn(text,audit.driver(self.s,self.ev['id'],pid))
            finally:_language.reset(context)
    def test_busy_timing_lock_defers_trace_without_waiting_or_dnf(self):
        self.start();held=threading.Event();release=threading.Event()
        def busy():
            with self.s.lock:held.set();release.wait(2)
        thread=threading.Thread(target=busy);thread.start();self.assertTrue(held.wait(1))
        try:
            start=time.monotonic()
            with self.assertRaises(Fault) as caught:audit.submit(self.s,self.token,self.batch())
            self.assertEqual(caught.exception.code,429);self.assertLess(time.monotonic()-start,.5)
        finally:release.set();thread.join(timeout=2)
        self.assertEqual(self.s.state(self.token)['status'],'active')

    def test_duplicate_ack_does_not_duplicate_points_and_changed_batch_is_rejected(self):
        self.start();data=self.batch();audit.submit(self.s,self.token,data);self.assertTrue(audit.submit(self.s,self.token,data)['duplicate'])
        with self.assertRaises(Fault):audit.submit(self.s,self.token,{**data,'points':[point(3000)]})
        self.assertEqual(self.s.db.execute('SELECT point_count FROM telemetry_runs').fetchone()[0],2)
    def test_bad_identity_nonfinite_order_and_oversized_inputs_do_not_change_attempt(self):
        self.start()
        for change in [{'eventId':'other'},{'stageIndex':1},{'seq':2},{'points':[point(1000)]*13},{'points':[point(1000,float('nan'))]},{'points':[point(2000),point(1000)]}]:
            with self.subTest(change=change),self.assertRaises(Fault):audit.submit(self.s,self.token,{**self.batch(),**change})
            self.assertEqual(self.s.state(self.token)['status'],'active')
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM telemetry_runs').fetchone()[0],0)
    def test_old_or_unstarted_stage_cannot_upload_and_recent_finish_can_flush(self):
        with self.assertRaises(Fault):audit.submit(self.s,self.token,self.batch())
        self.start();self.s.stage_end(self.token,self.ev['id'],0,60000,self.report)
        audit.submit(self.s,self.token,self.batch())
        self.s.db.execute('UPDATE provisional SET finished=?',(time.time()-61,))
        with self.assertRaises(Fault):audit.submit(self.s,self.token,self.batch([point(3000)],1))
    def test_retention_deletes_trace_and_summary_but_preserves_results(self):
        self.start();audit.submit(self.s,self.token,self.batch());self.s.stage_end(self.token,self.ev['id'],0,60000,self.report)
        attempt_updates.stage_result(self.s,self.token,self.record(0))
        self.s.db.execute('UPDATE events SET closes=? WHERE id=?',(time.time()-audit.RETENTION-1,self.ev['id']))
        self.s._trace_cleanup_at=0;self.s._sweep()
        for table in ('telemetry_runs','telemetry_chunks'):self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
        self.assertEqual(len(self.s.state(self.token)['results']),1)
        with self.assertRaises(Fault):audit.submit(self.s,self.token,self.batch([point(3000)],1))
    def test_storage_failure_is_not_dnf(self):
        self.start()
        with mock.patch.object(audit,'MAX_STAGE_POINTS',1),self.assertRaises(Fault):audit.submit(self.s,self.token,self.batch())
        self.assertEqual(self.s.state(self.token)['status'],'active')
    def test_review_green_yellow_red_and_timer_delta(self):
        self.start();audit.submit(self.s,self.token,self.batch([point(i*1000,i*10) for i in range(1,11)]))
        run=self.s.db.execute('SELECT * FROM telemetry_runs').fetchone()
        self.assertEqual(audit.evaluate(run,10000,10000)[0],0)
        self.assertEqual(audit.evaluate(run,10000,9500)[0],1)
        self.assertEqual(audit.evaluate(run,16000,10000)[0],2)
        self.assertEqual(audit.evaluate(None)[0],1)
        audit.submit(self.s,self.token,self.batch([point(11000,5000)],1))
        self.assertEqual(audit.evaluate(self.s.db.execute('SELECT * FROM telemetry_runs').fetchone(),11000,11000)[0],2)
    def test_missing_whole_stage_is_not_green_and_maps_escape_driver_text(self):
        self.start();audit.submit(self.s,self.token,self.batch());self.s.stage_end(self.token,self.ev['id'],0,60000,self.report)
        attempt_updates.stage_result(self.s,self.token,self.record(0));self.s.start(self.token,self.ev['id'],1,self.car,self.report)
        self.s.db.execute('UPDATE players SET nickname=? WHERE token_hash=?',('<script>bad</script>',self.s._auth(self.token)['token_hash']))
        text=audit.summaries(self.s,self.ev['id']);self.assertIn('trace-warn',text);self.assertNotIn('<script>bad</script>',text)
        with self.assertRaises(Fault):audit.driver(self.s,'other-rally',self.s._auth(self.token)['id'])
    def test_admin_penalty_reorders_scores_without_mutating_game_result_and_revoke_restores(self):
        self.finish_driver(self.token,60000);other=self.s.join(self.ev['id'],'BB')['token'];self.finish_driver(other,62000)
        p=self.s._auth(self.token)['id'];before=self.s.state(self.token)['results']
        penalty=admin_penalties.add(self.s,{'eventId':self.ev['id'],'playerId':p,'stageIndex':0,'amountMs':10000,'reason':'Missed control'})
        board=self.s.board(self.ev['id']);self.assertEqual(board['players'][0]['nickname'],'BB');self.assertEqual(board['players'][1]['total'],130000)
        self.assertEqual(self.s.state(self.token)['results'],before)
        text=site(self.s,self.ev['id']);self.assertIn('admin-penalty-note',text);self.assertIn('+00:10.000',text);self.assertIn('mono good',text)
        admin_penalties.revoke(self.s,{'eventId':self.ev['id'],'id':penalty['id']})
        self.assertEqual(self.s.board(self.ev['id'])['players'][0]['nickname'],'AA')
    def test_admin_penalty_rejects_wrong_event_and_unfinished_stage(self):
        p=self.s._auth(self.token)['id']
        data={'eventId':self.ev['id'],'playerId':p,'stageIndex':0,'amountMs':1000,'reason':'Reason'}
        with self.assertRaises(Fault):admin_penalties.add(self.s,data)
        self.finish(0)
        for change in [{'stageIndex':1},{'playerId':999},{'amountMs':-1},{'amountMs':True},{'reason':''},{'reason':'x'*161}]:
            with self.subTest(change=change),self.assertRaises(Fault):admin_penalties.add(self.s,{**data,**change})
    def test_rally_delete_purges_trace_and_admin_penalties_immediately(self):
        self.start();audit.submit(self.s,self.token,self.batch());self.s.stage_end(self.token,self.ev['id'],0,60000,self.report)
        admin_penalties.add(self.s,{'eventId':self.ev['id'],'playerId':self.s._auth(self.token)['id'],'stageIndex':0,'amountMs':1000,'reason':'Reason'})
        with self.s.lock:attempt_updates.purge_event_rows(self.s,self.ev['id'])
        for table in ('telemetry_runs','telemetry_chunks','admin_time_penalties'):self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
        with self.assertRaises(Fault):audit.submit(self.s,self.token,self.batch([point(3000)],1))
    def test_penalty_colours_zero_positive_unknown(self):
        self.finish_driver(self.token);text=site(self.s,self.ev['id']);self.assertIn('class="mono good">+00:00.000',text)
        admin_penalties.add(self.s,{'eventId':self.ev['id'],'playerId':self.s._auth(self.token)['id'],'stageIndex':0,'amountMs':1000,'reason':'Reason'})
        self.assertIn('class="mono bad">+00:01.000',site(self.s,self.ev['id']))

    def test_admin_penalty_updates_season_and_power_stage_rankings(self):
        from seasons import save_season,set_rallies,assign_member,scoring,member_by_cookie
        from identity_helpers import register_member
        from test_seasons import new_season
        other=self.s.join(self.ev['id'],'BB')['token'];mids=[]
        sid=save_season(self.s,new_season())['id'];set_rallies(self.s,sid,[self.ev['id']])
        for token,nick in [(self.token,'Season AA'),(other,'Season BB')]:
            account=register_member(self.s,nick);mid=member_by_cookie(self.s,account['token'])['id'];mids.append(mid)
            self.s.db.execute('UPDATE players SET club_member_id=? WHERE id=?',(mid,self.s._auth(token)['id']))
            assign_member(self.s,sid,mid,None,None)
        self.finish_driver(self.token,60000);self.finish_driver(other,62000)
        before=scoring(self.s,sid,now=time.time()+3*86400)
        self.assertEqual(before['drivers'][0]['memberId'],mids[0])
        admin_penalties.add(self.s,{'eventId':self.ev['id'],'playerId':self.s._auth(self.token)['id'],'stageIndex':1,'amountMs':10000,'reason':'Season review'})
        after=scoring(self.s,sid,now=time.time()+3*86400)
        self.assertEqual(after['drivers'][0]['memberId'],mids[1])
        self.assertGreater(after['drivers'][0]['powerStage'],after['drivers'][1]['powerStage'])

class SenderTests(unittest.TestCase):
    def test_actual_worker_uploads_before_any_finish(self):
        arrived=threading.Event();api=SimpleNamespace(call=mock.Mock(side_effect=lambda *a:arrived.set()))
        sender=TraceSender(api,'event',lambda m:None)
        try:
            sender.observe(0,SimpleNamespace(clock_ms=1000,x=0,z=0,speed=30),0)
            self.assertTrue(arrived.wait(5));self.assertEqual(api.call.call_args.args[0],'/api/live-telemetry')
        finally:sender.close();sender.thread.join(timeout=2)
    def test_expired_pending_stage_does_not_block_next_stage(self):
        api=SimpleNamespace(call=mock.Mock(side_effect=RuntimeError('HTTP 409: old stage expired')))
        with mock.patch('club_local.trace_sender.threading.Thread'):
            sender=TraceSender(api,'event',lambda m:None)
            sender.observe(0,SimpleNamespace(clock_ms=1000,x=0,z=0,speed=30),0)
            sender.observe(1,SimpleNamespace(clock_ms=1000,x=0,z=0,speed=30),2)
        sender.send_once();self.assertIn(0,sender.disabled)
        api.call.side_effect=None;sender.send_once()
        self.assertEqual(api.call.call_args.args[1]['stageIndex'],1);sender.close()

    def test_slow_network_is_bounded_and_retry_keeps_same_sequence(self):
        api=SimpleNamespace(call=mock.Mock(side_effect=RuntimeError('offline')));logs=[]
        with mock.patch('club_local.trace_sender.threading.Thread'):
            sender=TraceSender(api,'event',logs.append)
            for i in range(150):sender.observe(0,SimpleNamespace(clock_ms=i*1000,x=i,z=0,speed=30),i)
        self.assertEqual(len(sender.buffer),90);self.assertEqual(sender.dropped[0],60)
        sender.send_once();first=copy.deepcopy(sender.pending);sender.send_once();self.assertEqual(sender.pending,first)
        api.call.side_effect=None;sender.send_once();self.assertIsNone(sender.pending);self.assertEqual(sender.sequences[0],1)
        self.assertTrue(any(x.startswith('OSTRZEŻENIE:') for x in logs));sender.close()
