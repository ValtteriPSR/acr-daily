"""Synthetic smoke tests for the 0->running->frozen and restart paths.
Does not replace live ACR/Windows validation.
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import TestCase, mock
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server_local'))
sys.path.insert(0, str(ROOT / 'client'))
from server import Store
from test_server import event

# Replace ACR Daily modules only for this test. The installed upstream modules
# are used in real Windows operation, never these stubs.
acr = ModuleType('acr_daily')
acr.__path__ = []
acr.rallyclub = ModuleType('acr_daily.rallyclub')
acr.rallyweekend = ModuleType('acr_daily.rallyweekend')
acr.saveslot = ModuleType('acr_daily.saveslot')
acr.telemetry = ModuleType('acr_daily.telemetry')
acr.names = ModuleType('acr_daily.names')
acr.rallyweekend.progress = lambda b: None
acr.rallyweekend.results = lambda b: json.loads(b.decode('utf-8'))
acr.rallyclub.result_fingerprint = lambda e: (e['stage'], e['started'], tuple((r['car'],r['time'],r['penalty']) for r in e['runs']))
acr.names.same_car = lambda reported, ch: str(reported).lower() in [str(ch.get('car','')).lower(), str(ch.get('carId','')).lower(), *(str(a).lower() for a in ch.get('carAliases',[]))]
for suffix in ('rallyclub','rallyweekend','saveslot','telemetry','names'):
    sys.modules['acr_daily.'+suffix] = getattr(acr,suffix)
sys.modules['acr_daily'] = acr
from club_local import monitor
from integrity_rules import expected_settings


class FakeSource:
    def __init__(self):
        self.next = None
        self.unloaded = False
    def read(self):
        return self.next
    def close(self):
        pass


class FakeApi:
    def __init__(self, store, token, ident):
        self.store,self.token,self.ident = store,token,ident
    def call(self, endpoint, data=None):
        if endpoint=='/api/me':return self.store.state(self.token)
        if endpoint=='/api/start':return self.store.start(self.token,data['eventId'],data['stageIndex'],data['carId'],data.get('settings'))
        if endpoint=='/api/heartbeat':return self.store.heartbeat(self.token,data['eventId'],data['stageIndex'],data.get('settings'),data.get('penaltyMs'))
        if endpoint=='/api/stage-end':return self.store.stage_end(self.token,data['eventId'],data['stageIndex'],data['clockMs'],data.get('settings'),data.get('penaltyMs'))
        if endpoint=='/api/telemetry-penalty':
            import attempt_updates
            return attempt_updates.late_penalty(self.store,self.token,data)
        if endpoint=='/api/stage-result':
            import attempt_updates
            return attempt_updates.stage_result(self.store,self.token,data)
        if endpoint in ('/api/checkpoint','/api/recovery-checkpoint'):
            import attempt_updates
            return attempt_updates.checkpoint(self.store,self.token,data,recovery=endpoint=='/api/recovery-checkpoint')
        if endpoint=='/api/finalize':return self.store.finalize(self.token,data)
        if endpoint=='/api/dnf':return self.store.dnf(self.token,data['reason'])
        if endpoint=='/api/integrity-violation':return self.store.integrity_violation(self.token,data['reason'])
        raise ValueError(endpoint)


def frame(clock, x=0, speed=70):
    return SimpleNamespace(clock_ms=clock,x=x,z=0,speed=speed,car='VW Polo GTI R5',track='Greece Zeli')


class MonitorTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.save=Path(self.tmp.name)/'test.sav'
        self.save.write_text('[]')
        acr.saveslot.SAVE=str(self.save)
        self.store=Store(Path(self.tmp.name)/'database.sqlite', inactive=120)
        self.ev=event()
        self.store.import_event(self.ev)
        self.token=self.store.join(self.ev['id'],'Driver')['token']
        self.src=FakeSource()
        self.log=[]
        self.api=FakeApi(self.store,self.token,self.ev['id'])
        self.catalog=[{'id':'VWPoloGTIR5','name':'VW Polo GTI R5','telemetry':'VW Polo GTI R5'}]
        self.catalog_patch=mock.patch.object(monitor,'load_catalog',return_value=self.catalog)
        self.catalog_patch.start()
        self.integrity_patch=mock.patch.object(monitor.integrity,'read_and_check',
                    side_effect=lambda event:expected_settings(event))
        self.integrity_patch.start()
        self.report_patch=mock.patch.object(monitor.integrity,'report_from_save',side_effect=lambda raw:expected_settings(self.ev))
        self.report_patch.start()
        self.mon=monitor.AttemptMonitor(self.api,self.ev,'Driver',self.log.append,source=self.src)
        self.mon.resume()
        self.clock=[0.0]
        self.clock_patch=mock.patch.object(monitor.time,'monotonic',side_effect=lambda:self.clock[0])
        self.clock_patch.start()

    def tearDown(self):
        self.clock_patch.stop()
        self.catalog_patch.stop()
        self.integrity_patch.stop()
        self.report_patch.stop()
        self.store.db.close()
        self.tmp.cleanup()

    def step(self,when,fr):
        self.clock[0]=when
        self.src.next=fr
        self.mon.poll()

    def test_restart_results_in_irreversible_dnf(self):
        self.step(0.0,frame(0))
        self.step(0.1,frame(500))
        self.assertEqual(self.store.state(self.token)['status'],'active')
        self.step(0.5,frame(2800))
        self.step(0.7,frame(200))
        self.assertEqual(self.store.state(self.token)['status'],'dnf')

    def test_damage_tampering_during_os_is_sent_as_dnf(self):
        self.step(0.0,frame(0))
        self.step(0.1,frame(500))
        self.assertEqual(self.store.state(self.token)['status'],'active')
        from club_local.integrity import IntegrityError
        monitor.integrity.read_and_check.side_effect=IntegrityError('Uszkodzenia: oczekiwano 1, otrzymano 0')
        self.step(1.2,frame(1000))
        self.assertEqual(self.store.state(self.token)['status'],'active')
        self.step(2.5,frame(2000))
        self.assertEqual(self.store.state(self.token)['status'],'dnf')
        self.assertTrue(any('ustawienia' in line.lower() for line in self.log))

    def test_two_stages_and_final_game_save(self):
        self.step(0.0,frame(0))
        self.step(0.1,frame(500))
        self.step(0.3,frame(203452))
        self.step(0.8,frame(203452,0))
        self.step(2.3,frame(203452,5))
        self.assertEqual(self.store.state(self.token)['status'],'ready')
        self.step(2.4,frame(0))
        self.step(2.5,frame(500))
        self.step(2.7,frame(212783))
        self.step(3.0,frame(212783,0))
        self.step(4.6,frame(212783,4))
        self.assertEqual(self.store.state(self.token)['status'],'awaiting_results')
        self.assertEqual(self.store.board(self.ev['id'])['players'][0]['completed_stages'],0)
        now=time.time()
        rows=[{'stage':self.ev['stages'][0]['stageId'],'started':now-10,
               'runs':[{'car':'VWPoloGTIR5','time':203.452,'penalty':34.0}]},
              {'stage':self.ev['stages'][1]['stageId'],'started':now-5,
               'runs':[{'car':'VWPoloGTIR5','time':212.783,'penalty':56.0}]}]
        self.save.write_text(json.dumps(rows))
        self.step(6.0,None)
        self.assertEqual(self.store.state(self.token)['status'],'completed')
        self.assertEqual(self.store.board(self.ev['id'])['players'][0]['total'],506235)

    def test_hours_on_pause_keep_active_and_connected(self):
        self.step(0.0,frame(0));self.step(0.1,frame(500));self.step(1.0,frame(20000))
        self.step(2.0,frame(20000));self.step(3*3600.0,frame(20000))
        self.assertEqual(self.mon.status,'active')
        self.assertEqual(self.store.state(self.token)['status'],'active')

    def test_first_stage_save_is_submitted_before_finishing_rally(self):
        self.step(0.0,frame(0));self.step(0.1,frame(500));self.step(0.3,frame(203452))
        self.step(0.8,frame(203452,0));self.step(2.3,frame(203452,5))
        self.assertEqual(self.mon.status,'ready')

        rows=[{'stage':self.ev['stages'][0]['stageId'],'started':time.time()-5,
               'runs':[{'car':'VWPoloGTIR5','time':203.452,'penalty':34.0}]}]
        self.save.write_text(json.dumps(rows));self.step(4.0,None)
        board=self.store.board(self.ev['id'])
        self.assertTrue(board['stageResults'][0]['verified'])
        self.assertEqual(board['stageResults'][0]['total_ms'],237452)
        self.assertEqual(self.mon.status,'ready')

    def test_penalties_at_finish_are_sent_without_a_game_save(self):
        start=frame(0);start.penalty_ms=0
        self.step(0,start);self.step(.1,frame(500))
        f=frame(203452);f.penalty_ms=34000
        self.step(.3,f);self.step(.8,f)
        f=frame(203452,5);f.penalty_ms=34000
        self.step(2.3,f)
        row=self.store.board(self.ev['id'])['stageResults'][0]
        self.assertFalse(row['verified']);self.assertEqual(row['penalty_ms'],34000)
        self.assertEqual(row['total_ms'],237452)
        f.penalty_ms=36000;self.step(2.9,f)
        self.assertEqual(self.store.board(self.ev['id'])['stageResults'][0]['penalty_ms'],36000)
        f.penalty_ms=0;self.step(3.5,f)
        self.assertEqual(self.store.board(self.ev['id'])['stageResults'][0]['penalty_ms'],36000)

    def test_save_available_at_finish_is_confirmed_in_same_poll(self):
        self.step(0,frame(0));self.step(.1,frame(500));self.step(.3,frame(203452));self.step(.8,frame(203452))
        self.save.write_text(json.dumps([{'stage':self.ev['stages'][0]['stageId'],'started':time.time()-5,
            'runs':[{'car':'VWPoloGTIR5','time':203.452,'penalty':34.0}]}]))
        self.step(2.3,frame(203452,5))
        self.assertTrue(self.store.board(self.ev['id'])['stageResults'][0]['verified'])

    def test_cumulative_field_counts_only_penalty_added_in_this_stage(self):
        start=frame(0);start.penalty_ms=34000
        self.step(0,start)
        running=frame(500);running.penalty_ms=34000
        self.step(.1,running)
        finish=frame(203452);finish.penalty_ms=70000
        self.step(.3,finish);self.step(.8,finish)
        finish.x=5;self.step(2.3,finish)
        self.assertEqual(self.store.board(self.ev['id'])['stageResults'][0]['penalty_ms'],36000)

    def test_exit_does_not_send_unconfirmed_checkpoint(self):
        self.mon.event={**self.ev,'launcherProtocol':'0.2.4','allowBreaks':True,
            'stages':[self.ev['stages'][0],{**self.ev['stages'][1],'serviceBefore':True}]}
        self.mon.stage_index=1;self.mon.status='ready'
        with mock.patch.object(self.api,'call',wraps=self.api.call) as call:
            self.mon._exit_at_service(10)
            self.assertFalse(any(c.args[0]=='/api/checkpoint' for c in call.call_args_list))
        self.assertFalse(self.mon.checkpoint_sent)
        self.assertTrue(any('NIEZATWIERDZONA' in line for line in self.log))

    def test_legacy_rally_uploads_personal_checkpoint_after_service_exit(self):
        self.ev['stages'][1]['serviceBefore']=True
        self.store.db.execute('UPDATE events SET config=? WHERE id=?',(json.dumps(self.ev),self.ev['id']))
        self.step(0,frame(0));self.step(.1,frame(500));self.step(.3,frame(203452));self.step(.8,frame(203452));self.step(2.3,frame(203452,5))
        self.save.write_text(json.dumps([{'stage':self.ev['stages'][0]['stageId'],'started':time.time()-5,
            'runs':[{'car':'VWPoloGTIR5','time':203.452,'penalty':34.0}]}]))
        self.step(4,None)
        with mock.patch.object(monitor.rallyweekend,'progress',return_value={'done':1},create=True),mock.patch.object(monitor.integrity,'report_from_save',return_value=expected_settings(self.ev)):
            self.mon._exit_at_service(10)
        self.assertTrue(self.mon.checkpoint_sent)
        self.assertTrue(self.mon.dead)
        import attempt_updates
        self.assertTrue(attempt_updates.checkpoint(self.store,self.token)['available'])

    def test_idle_settings_change_warns_and_never_starts_or_uploads_results(self):
        from club_local.integrity import IntegrityError
        monitor.integrity.read_and_check.side_effect=IntegrityError('Changed stages in menu')
        self.step(0,frame(0));self.step(2,frame(1000))
        self.assertEqual(self.store.state(self.token)['status'],'registered')
        self.assertTrue(self.store.state(self.token)['recoveryRequired'])
        self.assertTrue(self.mon.recovery_required)
        monitor.integrity.read_and_check.side_effect=lambda ev:expected_settings(ev)
        self.step(4,frame(0));self.step(5,frame(500));self.mon.close()
        self.assertEqual(self.store.state(self.token)['status'],'registered')
        self.assertFalse(self.store.state(self.token)['results'])
        self.assertTrue(any(line.startswith('OSTRZEŻENIE:') for line in self.log))

    def test_valid_os1_copy_is_uploaded_before_menu_change_without_game_exit(self):
        import attempt_updates
        self.step(0,frame(0));self.step(.1,frame(500));self.step(.3,frame(203452));self.step(.8,frame(203452));self.step(2.3,frame(203452,5))
        self.save.write_text(json.dumps([{'stage':self.ev['stages'][0]['stageId'],'started':time.time()-5,
            'runs':[{'car':'VWPoloGTIR5','time':203.452,'penalty':34.0}]}]))
        with mock.patch.object(monitor.rallyweekend,'progress',return_value={'done':1}):self.step(4,None)
        copy=attempt_updates.checkpoint(self.store,self.token,recovery=True)
        self.assertTrue(copy['available']);self.assertFalse(self.mon.dead)
        from club_local.integrity import IntegrityError
        monitor.integrity.read_and_check.side_effect=IntegrityError('Changed calendar')
        self.step(6,None)
        self.assertEqual(self.store.state(self.token)['status'],'ready')
        self.assertEqual(self.store.state(self.token)['stage_index'],1)
        self.assertEqual(attempt_updates.checkpoint(self.store,self.token,recovery=True)['digest'],copy['digest'])

if __name__=='__main__':
    import unittest;unittest.main()
