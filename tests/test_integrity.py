import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server_local'))
import tempfile
import unittest
from server import Store, Fault
from integrity_rules import expected_settings, compare
from test_server import event

import timing_guard  # testy symulują OS natychmiast; zegar serwera sprawdza test_projectsimracing.py
timing_guard.HARD_LIMIT_MS = timing_guard.REVIEW_LIMIT_MS = float('inf')

class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Store(Path(self.tmp.name)/'db.sqlite3')
        self.ev=event()
        self.ev['weekend']={'damage':True,'damageIntensity':'realistic',
            'penalty':'realistic','respawn':True,'wear':'severe','failures':'light'}
        self.db.import_event(self.ev)
        self.token=self.db.join(self.ev['id'],'Tester')['token']
        self.correct=expected_settings(self.ev)
    def tearDown(self):
        self.db.db.close()
        self.tmp.cleanup()
    def test_untouched_settings_are_accepted(self):
        self.assertEqual(compare(self.ev,self.correct),[])
        self.assertEqual(self.db.start(self.token,self.ev['id'],0,'VWPoloGTIR5',self.correct)['status'],'active')
        self.db.heartbeat(self.token,self.ev['id'],0,self.correct)
        self.db.stage_end(self.token,self.ev['id'],0,180000,self.correct)
        self.assertEqual(self.db.state(self.token)['status'],'ready')
    def test_damage_disabled_blocks_start_without_consuming_attempt(self):
        modified=expected_settings(self.ev)
        modified['rules']['damage']=0
        self.assertTrue(compare(self.ev,modified))
        with self.assertRaises(Fault):
            self.db.start(self.token,self.ev['id'],0,'VWPoloGTIR5',modified)
        self.assertEqual(self.db.state(self.token)['status'],'registered')
        self.assertTrue(self.db.state(self.token)['recoveryRequired'])
        with self.assertRaises(Fault):
            self.db.start(self.token,self.ev['id'],0,'VWPoloGTIR5',self.correct)
    def test_damage_change_during_stage_causes_dnf(self):
        self.db.start(self.token,self.ev['id'],0,'VWPoloGTIR5',self.correct)
        bad=expected_settings(self.ev)
        bad['rules']['intensity']=0
        with self.assertRaises(Fault):
            self.db.heartbeat(self.token,self.ev['id'],0,bad)
        self.assertEqual(self.db.state(self.token)['status'],'dnf')
    def test_calendar_or_weather_change(self):
        for name, mutate in [
            ('stage', lambda x:x['stages'][0].update(stage='GreeceS9WrongForward')),
            ('weather',lambda x:x['stages'][0].update(weather=4)),
            ('start', lambda x:x['stages'][0].update(start=12345)),
            ('zone', lambda x:x['stages'][1].update(zone='ServiceParkDefault')),
            ('count', lambda x:x['stages'].pop()),
        ]:
            with self.subTest(name=name):
                settings=expected_settings(self.ev)
                mutate(settings)
                self.assertTrue(compare(self.ev,settings))
    def test_missing_report_is_fail_closed(self):
        with self.assertRaises(Fault):
            self.db.start(self.token,self.ev['id'],0,'VWPoloGTIR5')
        self.assertEqual(self.db.state(self.token)['status'],'registered')
    def test_stage_end_requires_integrity(self):
        self.db.start(self.token,self.ev['id'],0,'VWPoloGTIR5',self.correct)
        with self.assertRaises(Fault):
            self.db.stage_end(self.token,self.ev['id'],0,180000,None)
        self.assertEqual(self.db.state(self.token)['status'],'dnf')
    def test_explicit_violation_while_registered(self):
        self.db.integrity_violation(self.token,'Wyłączone uszkodzenia')
        self.assertEqual(self.db.state(self.token)['status'],'registered')
    def test_report_is_not_raw_save_hash(self):
        self.assertTrue(compare(self.ev,{'sha256':'deadbeef'}))

if __name__=='__main__':unittest.main()
