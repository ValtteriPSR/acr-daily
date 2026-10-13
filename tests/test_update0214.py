"""Missing saves bypass stale transaction flags without starting a Club attempt."""
import ast,sys,unittest,queue
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'client'),str(ROOT/'tests')]
import test_update0211 as prior
from club_local import save_safety as safety,save_layout as layout

class SetupTests(unittest.TestCase):
    setUp=prior.SafetyTests.setUp
    tearDown=prior.SafetyTests.tearDown
    def test_missing_save_takes_precedence_over_stale_pending_and_blocked_flags(self):
        self.path.unlink();safety.record({'pending':{'digest':'old'},'blocked':'old failure'})
        with self.assertRaises(safety.WeekendRequired):safety.prepare_run()
        self.assertFalse((self.dir/'Master.sav').exists())
        self.assertTrue(safety.state()['pending'])
    def test_valid_save_without_weekend_takes_precedence_even_with_old_good_copy(self):
        safety.prepare_run();good=(self.dir/'Master.sav').read_bytes()
        raw=self.raw.replace(b'DefaultRally',b'DefaultOther');layout.inspect(raw)
        self.path.write_bytes(raw);meta=safety.state();meta['pending']={'digest':'old'};safety.record(meta)
        with self.assertRaises(safety.WeekendRequired):safety.prepare_run()
        self.assertEqual((self.dir/'Master.sav').read_bytes(),good)
    def test_private_stage_creates_master_and_clears_stale_pending_only_after_start(self):
        safety.record({'pending':{'digest':'old'},'blocked':'old failure'})
        frames=iter(SimpleNamespace(clock_ms=n,car='Synthetic car',track='Synthetic track') for n in (0,100,200))
        messages=[];source=SimpleNamespace(read=lambda:next(frames),close=lambda:None)
        observer=safety.StageStartObserver(messages.append,source)
        observer.poll();observer.poll();self.assertTrue(safety.state()['pending'])
        observer.poll();safety.ensure_run_allowed()
        self.assertEqual((self.dir/'Master.sav').read_bytes(),self.raw)
        self.assertTrue(messages[0].startswith('Kopia MASTER została'))
    def test_private_setup_completion_is_visible_outside_collapsed_console(self):
        source=(ROOT/'client/club_local/web_launch.py').read_text()
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='WebLaunchWindow')
        method=next(n for n in node.body if isinstance(n,ast.FunctionDef) and n.name=='observe_private_stages')
        ns={'__package__':'club_local'};exec(compile(ast.Module(body=[method],type_ignores=[]),'<private setup>','exec'),ns)
        window=SimpleNamespace(queue=queue.Queue(),log=mock.Mock(),set_status=mock.Mock(),running=True)
        def observer(emit):
            def poll():emit(safety.MASTER_NOTICE);window.running=False
            return SimpleNamespace(poll=poll,close=mock.Mock())
        with mock.patch.object(safety,'StageStartObserver',side_effect=observer):ns['observe_private_stages'](window,setup=True)
        self.assertEqual(window.queue.get(),('setup',safety.SETUP_COMPLETE))
        self.assertIn("textvariable=self.setup_notice,fg='#ffd166'",source)
        for text in ['Pozostaw launcher otwarty','nie zostanie zaliczony','nie zużyje','odliczanie','RUN RALLY']:self.assertIn(text,safety.FIRST_WEEKEND_MESSAGE)
