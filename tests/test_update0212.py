"""Automatic Master proof uses synthetic files and telemetry, never player data."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'client'),str(ROOT/'tests')]
import test_update0211 as prior
from club_local import save_safety as safety,save_layout as layout
# Execute the actual preparation method without importing a graphical runtime.
import ast
source=(ROOT/'client/club_local/web_launch.py').read_text()
class_node=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='WebLaunchWindow')
prepare_node=next(n for n in class_node.body if isinstance(n,ast.FunctionDef) and n.name=='prepare')
ui_globals={'__package__':'club_local','acr_daily_settings':SimpleNamespace(load=lambda:None),
            'configured_server':lambda:'https://example.com','Api':mock.Mock(),
            'saveslot':SimpleNamespace(game_running=lambda:False),'Path':Path,
            'integrity':SimpleNamespace(IntegrityError=ValueError)}
exec(compile(ast.Module(body=[prepare_node],type_ignores=[]),'<launcher preparation>','exec'),ui_globals)
prepare=ui_globals['prepare']

class AutomaticMasterTests(unittest.TestCase):
    setUp=prior.SafetyTests.setUp
    tearDown=prior.SafetyTests.tearDown
    def observer(self):
        self.frames=[];self.messages=[]
        self.source=SimpleNamespace(read=lambda:self.frames.pop(0),close=mock.Mock())
        self.ob=safety.StageStartObserver(self.messages.append,self.source)
        return self.ob
    def poll(self,clock,track='Test stage',car='Test car'):
        self.frames.append(None if clock is None else SimpleNamespace(clock_ms=clock,track=track,car=car))
        self.ob.poll()
    def start(self):
        for clock in [0,100,100,200]:self.poll(clock)
    def test_automatic_first_master_only_after_fresh_advancing_clock(self):
        self.observer()
        for clock in [500,600,None,0,0,100,100]:self.poll(clock)
        self.assertFalse(safety.state().get('good'))
        self.poll(200)
        self.assertEqual((self.dir/'Master.sav').read_bytes(),self.raw)
        self.assertEqual(safety.state()['good']['proof'],'stage-start')
        safety.ensure_run_allowed()
        self.assertEqual(len(self.messages),1)
    def test_next_stage_start_updates_master_but_driving_and_menu_do_not(self):
        self.observer();self.start();first=safety.state()['good']['path']
        changed=self.raw[:-1]+b'\1';self.path.write_bytes(changed)
        for clock in [300,400,None,900,1000]:self.poll(clock)
        self.assertEqual((self.dir/'Master.sav').read_bytes(),self.raw)
        self.start()
        self.assertEqual((self.dir/'Master.sav').read_bytes(),changed)
        self.assertEqual(Path(first).read_bytes(),self.raw)
    def test_mismatched_car_track_and_non_advancing_timer_cannot_confirm(self):
        self.observer();self.poll(0);self.poll(100,track='Other');self.poll(200,track='Other')
        self.assertFalse(safety.state().get('good'))
        for c in [None,0,100,50,200]:self.poll(c)
        self.assertFalse(safety.state().get('good'))
    def test_corrupt_or_reported_bad_file_never_overwrites_master(self):
        self.observer();self.start();self.path.write_bytes(b'broken');self.start()
        self.assertEqual((self.dir/'Master.sav').read_bytes(),self.raw)
        self.path.write_bytes(self.raw[:-1]+b'\1');safety.report_crash();self.start()
        self.assertEqual((self.dir/'Master.sav').read_bytes(),self.raw)
        self.assertTrue(safety.state()['blocked'])
    def test_stage_start_confirms_pending_install_without_manual_button(self):
        safety.confirm_good();safety.replace(self.raw[:-1]+b'\1')
        self.assertTrue(safety.state()['pending'])
        self.observer();self.start()
        self.assertNotIn('pending',safety.state());safety.ensure_run_allowed()
    def test_changing_save_does_not_replace_master(self):
        self.observer();self.start();old=safety.state()['good']
        with mock.patch.object(safety,'read_file',side_effect=[self.raw,self.raw[:-1]+b'\1']):
            with self.assertRaises(layout.InvalidSave):safety.confirm_stage_start()
        self.assertEqual(safety.state()['good'],old)
    def test_restore_requires_new_launcher_and_game_exit_then_stage_proof(self):
        self.observer();self.start();self.path.write_bytes(b'broken');safety.report_crash();safety.restore_previous()
        self.start();self.assertTrue(safety.state()['restartRequired'])
        self.fake.game_running=lambda:True
        self.observer();self.ob.poll();self.assertTrue(safety.state()['restartRequired'])
        self.fake.game_running=lambda:False;self.ob.game_running=self.fake.game_running
        with mock.patch.object(safety.os,'getpid',return_value=987654321):self.poll(None)
        self.assertNotIn('restartRequired',safety.state())
        with self.assertRaises(layout.InvalidSave):safety.ensure_run_allowed()
        self.start();safety.ensure_run_allowed()
    def test_retention_keeps_first_and_twenty_recent_confirmed_snapshots(self):
        first=None
        for i in range(25):
            self.path.write_bytes(self.raw[:-1]+bytes([i]))
            safety.confirm_stage_start()
            if first is None:first=safety.state()['good']['path']
        self.assertEqual(len(safety.state()['confirmedCopies']),21)
        self.assertTrue(Path(first).exists())
        self.assertEqual(len(list(self.dir.glob('confirmed-good-*.sav'))),21)
    def test_no_weekend_or_invalid_file_requests_initial_setup(self):
        self.assertTrue(safety.has_weekend());self.path.write_bytes(b'broken')
        self.assertFalse(safety.has_weekend())
        self.assertEqual(safety.FIRST_WEEKEND_MESSAGE,'ustaw w grze dowolny Rally Weekend, uruchom pierwszy OS (nie musisz kończyć), wyjdź z gry i ponownie kliknij RUN.')
    def test_failed_master_write_preserves_previous_protected_copy(self):
        self.observer();self.start();old=safety.state()['good'];self.path.write_bytes(self.raw[:-1]+b'\1')
        real=safety.atomic
        def fail(path,raw):
            if Path(path).name=='Master.sav':raise OSError('Interrupted Master update')
            real(path,raw)
        with mock.patch.object(safety,'atomic',side_effect=fail),self.assertRaises(OSError):safety.confirm_stage_start()
        self.assertEqual(safety.state()['good'],old)
        self.assertEqual(Path(old['path']).read_bytes(),self.raw)

class FirstRunTests(unittest.TestCase):
    def test_setup_abort_precedes_private_observation_and_never_writes_club_save(self):
        for weekend in (False,True):
            with self.subTest(weekend=weekend):
                window=SimpleNamespace()
                window.ticket='synthetic';window.queue=__import__('queue').Queue();window.log=mock.Mock()
                window.set_status=mock.Mock();window.set_navigation=mock.Mock();window.observe_private_stages=mock.Mock()
                api=mock.Mock(token=None)
                api.call.return_value={'event':{'id':'synthetic'},'nickname':'Test','token':'test','playerId':1}
                with mock.patch.dict(ui_globals,{'Api':lambda server:api}),mock.patch.object(safety,'needs_stage_proof',return_value=True),mock.patch.object(safety,'has_weekend',return_value=weekend):
                    prepare(window)
                self.assertEqual(api.call.call_args_list,[mock.call('/api/launcher/redeem',{'ticket':'synthetic'}),mock.call('/api/launcher/abort',{})])
                window.observe_private_stages.assert_called_once()
                self.assertEqual(window.queue.get()[0],'dialog')
    def test_participant_window_has_no_manual_confirmation_or_ram_loop(self):
        source=(ROOT/'client/club_local/web_launch.py').read_text()
        self.assertNotIn('log_memory',source)
        self.assertNotIn('Zapis działa — zachowaj kopię',source)
        self.assertNotIn("action=='confirm'",source)
