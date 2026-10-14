import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server_local'))
import unittest
import tempfile
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from server import Store, Fault, site
from integrity_rules import expected_settings


import timing_guard  # testy symulują OS natychmiast; zegar serwera sprawdza test_projectsimracing.py
timing_guard.HARD_LIMIT_MS = timing_guard.REVIEW_LIMIT_MS = float('inf')

def event():
    now=datetime.now(timezone.utc)
    return {'id':'greece-test-2026','name':'Rally Zeli test','location':'Greece',
            'opensAt':(now-timedelta(hours=1)).isoformat(),
            'closesAt':(now+timedelta(days=2)).isoformat(),
            'carClass':'Rally2/R5','allowedCars':['VWPoloGTIR5','SkodaFabiaRSRally2'],
            'stages':[{'stageId':'GreeceS3ElatiaCut2Reverse','weatherGame':'WT_CLEAR','startSeconds':36000},
                      {'stageId':'GreeceS3ElatiaCut2Forward','weatherGame':'WT_CLEAR','startSeconds':42000}]}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3',inactive=1)
        self.ev=event()
        self.store.import_event(self.ev)
        self.token=self.store.join(self.ev['id'],'Test Driver')['token']

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_one_shot_and_finalize_both_stages_with_official_penalties(self):
        slug=self.ev['id']; car='VWPoloGTIR5'
        self.store.start(self.token,slug,0,car,expected_settings(self.ev))
        with self.assertRaises(Fault):
            self.store.start(self.token,slug,0,car,expected_settings(self.ev))
        self.store.heartbeat(self.token,slug,0,expected_settings(self.ev))
        self.store.stage_end(self.token,slug,0,203452,expected_settings(self.ev))
        self.assertEqual(self.store.state(self.token)['status'],'ready')
        self.store.start(self.token,slug,1,car,expected_settings(self.ev))
        self.store.stage_end(self.token,slug,1,212783,expected_settings(self.ev))
        self.assertEqual(self.store.state(self.token)['status'],'awaiting_results')
        t=time.time()
        rows=[{'stageIndex':0,'stageId':self.ev['stages'][0]['stageId'],'carId':car,
               'rawMs':203452,'penaltyMs':34000,'totalMs':237452,'acrStarted':t-10},
              {'stageIndex':1,'stageId':self.ev['stages'][1]['stageId'],'carId':car,
               'rawMs':212783,'penaltyMs':56000,'totalMs':268783,'acrStarted':t-5}]
        self.assertEqual(self.store.finalize(self.token,{'stages':rows,'settings':expected_settings(self.ev)})['status'],'completed')
        board=self.store.board(slug)['players'][0]
        self.assertEqual(board['completed_stages'],2)
        self.assertEqual(board['total'],506235)
        self.assertEqual(board['penalty'],90000)
        self.assertEqual(self.store.state(self.token)['status'],'completed')
        with self.assertRaises(Fault):
            self.store.finalize(self.token,{'stages':rows,'settings':expected_settings(self.ev)})
        html=site(self.store,slug)
        self.assertIn('08:26.235',html)
        self.assertIn('META',html)

    def test_restart_dnf_permanent(self):
        self.store.start(self.token,self.ev['id'],0,'VWPoloGTIR5',expected_settings(self.ev))
        self.store.dnf(self.token,'restarted')
        with self.assertRaises(Fault):
            self.store.start(self.token,self.ev['id'],0,'VWPoloGTIR5',expected_settings(self.ev))
        self.assertEqual(self.store.board(self.ev['id'])['players'][0]['status'],'dnf')

    def test_crash_timeout_dnf(self):
        self.store.start(self.token,self.ev['id'],0,'VWPoloGTIR5',expected_settings(self.ev))
        with self.store.lock:
            self.store.db.execute('UPDATE players SET last_seen=?',(time.time()-3,))
        self.assertEqual(self.store.state(self.token)['status'],'dnf')

    def test_no_nickname_takeover(self):
        with self.assertRaises(Fault):
            self.store.join(self.ev['id'],'test driver')
        with self.assertRaises(Fault):
            self.store.state('invalid_token')

    def test_no_partial_results_on_bad_bulk(self):
        slug=self.ev['id']; car='VWPoloGTIR5';now=time.time()
        for stage in range(2):
            self.store.start(self.token,slug,stage,car,expected_settings(self.ev))
            self.store.stage_end(self.token,slug,stage,200000,expected_settings(self.ev))
        rows=[{'stageIndex':0,'stageId':self.ev['stages'][0]['stageId'],'carId':car,
               'rawMs':200000,'penaltyMs':30000,'totalMs':230000,'acrStarted':now-10},
              {'stageIndex':1,'stageId':self.ev['stages'][1]['stageId'],'carId':car,
               'rawMs':200000,'penaltyMs':30000,'totalMs':777777,'acrStarted':now-5}]
        with self.assertRaises(Fault):
            self.store.finalize(self.token,{'stages':rows,'settings':expected_settings(self.ev)})
        rows_in_db=self.store.db.execute('SELECT COUNT(*) FROM results').fetchone()[0]
        self.assertEqual(rows_in_db,0)
        self.assertEqual(self.store.state(self.token)['status'],'awaiting_results')

    def test_concurrent_first_start_only_one_wins(self):
        def attempt(_):
            try:
                self.store.start(self.token,self.ev['id'],0,'VWPoloGTIR5',expected_settings(self.ev));return 'accepted'
            except Fault:
                return 'blocked'
        with ThreadPoolExecutor(max_workers=8) as executor:
            results=list(executor.map(attempt,range(8)))
        self.assertEqual(results.count('accepted'),1)
        self.assertEqual(results.count('blocked'),7)

if __name__=='__main__':unittest.main()
