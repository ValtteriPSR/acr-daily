"""Quiet first-run setup, bounded snapshots and expandable participant console."""
import ast,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'client'),str(ROOT/'tests')]
import test_update0211 as prior
from club_local import save_safety as safety,save_layout as layout

class QuietBackupTests(unittest.TestCase):
    setUp=prior.SafetyTests.setUp
    tearDown=prior.SafetyTests.tearDown
    def test_first_run_silently_backs_up_configured_weekend_then_starts_normally(self):
        self.assertTrue(safety.prepare_run())
        self.assertEqual((self.dir/'Master.sav').read_bytes(),self.raw)
        self.assertEqual(safety.state()['good']['proof'],'initial-weekend')
        self.assertFalse(safety.prepare_run())
        safety.replace(self.raw[:-1]+b'\1')
        self.assertEqual((self.dir/'Master.sav').read_bytes(),self.raw)
        with self.assertRaises(layout.InvalidSave):safety.prepare_run()
    def test_existing_weekend_enters_normal_club_preparation_without_dialog(self):
        import test_update0212 as methods
        window=SimpleNamespace(ticket='synthetic',queue=__import__('queue').Queue(),log=mock.Mock(),set_status=mock.Mock(),set_navigation=mock.Mock(),observe_private_stages=mock.Mock())
        api=mock.Mock(token=None)
        def call(path,payload=None):
            if path=='/api/launcher/redeem':return {'event':{'id':'synthetic','name':'Test','stages':[{}]},'nickname':'Test','token':'test','playerId':1}
            if path=='/api/catalog':raise RuntimeError('Test stops after entering normal Club preparation')
            return {}
        api.call.side_effect=call
        with mock.patch.dict(methods.ui_globals,{'Api':lambda server:api,'saveslot':self.fake}):methods.prepare(window)
        self.assertIn(mock.call('/api/catalog'),api.call.call_args_list)
        self.assertTrue(window.queue.empty())
        self.assertEqual(safety.state()['good']['proof'],'initial-weekend')
        self.assertIn(mock.call(safety.MASTER_NOTICE),window.log.call_args_list)
    def test_missing_weekend_does_not_create_master(self):
        self.path.write_bytes(b'No Rally Weekend')
        with self.assertRaises(safety.WeekendRequired):safety.prepare_run()
        self.assertFalse((self.dir/'Master.sav').exists())
    def test_first_run_backup_is_restorable_before_any_club_stage_succeeds(self):
        safety.prepare_run();self.path.write_bytes(b'broken club save');safety.restore_previous()
        self.assertEqual(self.path.read_bytes(),self.raw)
        with self.assertRaises(layout.InvalidSave):safety.prepare_run()
        with mock.patch.object(safety.os,'getpid',return_value=987654321):
            self.assertFalse(safety.prepare_run())
        safety.ensure_run_allowed()
        with self.assertRaises(layout.InvalidSave):safety.replace(b'broken club save')
    def test_successful_stage_removes_legacy_good_and_quarantine_copies(self):
        for kind in ('confirmed-good','quarantine'):
            for i in range(3):(self.dir/(kind+'-'+str(i)+'.sav')).write_bytes(self.raw)
        (self.dir/'Quarantine.sav').write_bytes(b'broken')
        safety.confirm_stage_start()
        self.assertEqual(len(safety.state()['confirmedCopies']),1)
        self.assertFalse(list(self.dir.glob('confirmed-good-*.sav')))
        self.assertFalse(list(self.dir.glob('*quarantine*.sav')))
        self.assertFalse((self.dir/'Quarantine.sav').exists())
    def test_working_and_quarantine_backups_replace_fixed_files(self):
        for i in range(10):
            safety.archive(self.raw,'before-run');safety.archive(self.raw,'quarantine')
        self.assertEqual(set(x.name for x in self.dir.glob('*.sav')),{'player.sav','BeforeRun.sav','Quarantine.sav'})
    def test_metadata_write_failure_rolls_master_back(self):
        safety.prepare_run();before=safety.state();self.path.write_bytes(self.raw[:-1]+b'\1')
        with mock.patch.object(safety,'record',side_effect=OSError('Interrupted metadata commit')):
            with self.assertRaises(OSError):safety.confirm_stage_start()
        self.assertEqual((self.dir/'Master.sav').read_bytes(),self.raw)
        self.assertEqual(safety.state(),before)
    def test_generated_notice_tells_player_where_to_restore(self):
        self.assertIn('MASTER',safety.MASTER_NOTICE)
        self.assertIn('przywróć ją w launcherze',safety.MASTER_NOTICE)

class ConsoleTests(unittest.TestCase):
    def test_console_is_hidden_initially_and_toggle_expands_and_collapses(self):
        source=(ROOT/'client/club_local/web_launch.py').read_text()
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='WebLaunchWindow')
        method=next(n for n in node.body if isinstance(n,ast.FunctionDef) and n.name=='toggle_console')
        ns={};exec(compile(ast.Module(body=[method],type_ignores=[]),'<console toggle>','exec'),ns)
        window=SimpleNamespace(console_visible=False,console_frame=mock.Mock(),console_toggle=mock.Mock(),root=mock.Mock(),setup_notice=mock.Mock(get=lambda:''))
        ns['toggle_console'](window)
        self.assertTrue(window.console_visible);window.console_frame.pack.assert_called_once()
        ns['toggle_console'](window)
        self.assertFalse(window.console_visible);window.console_frame.pack_forget.assert_called_once()
        self.assertIn('self.console_visible=False',source)
        self.assertNotIn('Gra crashuje — zablokuj RUN',source)
        self.assertNotIn('Brak aktualnej kopii Master',source)
