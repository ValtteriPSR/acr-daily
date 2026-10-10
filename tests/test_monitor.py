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
        if endpoint=='/api/heartbeat':return self.store.heartbeat(self.token,data['eventId'],data['stageIndex'],data.get('settings'))
        if endpoint=='/api/stage-end':return self.store.stage_end(self.token,data['eventId'],data['stageIndex'],data['clockMs'],data.get('settings'))
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
        self.mon=monitor.AttemptMonitor(self.api,self.ev,'Driver',self.log.append,source=self.src)
        self.mon.resume()
        self.clock=[0.0]
        self.clock_patch=mock.patch.object(monitor.time,'monotonic',side_effect=lambda:self.clock[0])
        self.clock_patch.start()

    def tearDown(self):
        self.clock_patch.stop()
        self.catalog_patch.stop()
        self.integrity_patch.stop()
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

if __name__=='__main__':
    import unittest;unittest.main()
