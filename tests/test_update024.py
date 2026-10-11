"""0.2.4 behavior and abuse regressions on disposable databases only."""
import base64
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server_local'))
import attempt_updates as updates
import club_settings
from server import Store,Fault,site
from integrity_rules import expected_settings
from test_server import event
import test_admin
from seasons import save_season,set_rallies
from i18n import _language
from admin_customization import enhance
from admin_panel import PAGE
from season_panel import enhance_deletion,PAGE as SEASON_PAGE


class UpdateStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'test.db')
        self.ev=event();self.ev.update(allowBreaks=True,launcherProtocol='0.2.4')
        self.ev['stages'][1]['serviceBefore']=True
        self.s.import_event(self.ev);self.token=self.s.join(self.ev['id'],'AA')['token']
        self.car=self.ev['allowedCars'][0];self.report=expected_settings(self.ev)
    def tearDown(self): self.s.db.close();self.tmp.cleanup()
    def finish(self,idx):
        self.s.start(self.token,self.ev['id'],idx,self.car,self.report)
        self.s.stage_end(self.token,self.ev['id'],idx,60000,self.report)
    def record(self,idx):
        return dict(stageIndex=idx,stageId=self.ev['stages'][idx]['stageId'],carId=self.car,rawMs=60000,penaltyMs=1000,totalMs=61000,acrStarted=time.time()+idx,settings=self.report)
    def payload(self,raw=b'player-specific-save'):
        return dict(stageIndex=1,save=base64.b64encode(gzip.compress(raw)).decode(),digest=hashlib.sha256(raw).hexdigest(),baseline={},settings=self.report)
    def test_stage_results_immediate_and_immutable_then_complete(self):
        self.finish(0);b=self.s.board(self.ev['id']);self.assertEqual(b['stageResults'][0]['raw_ms'],60000);self.assertFalse(b['stageResults'][0]['verified'])
        rec=self.record(0);updates.stage_result(self.s,self.token,rec);updates.stage_result(self.s,self.token,rec)
        self.assertEqual(self.s.board(self.ev['id'])['stageResults'][0]['total_ms'],61000)
        altered={**rec,'penaltyMs':0,'totalMs':60000}
        with self.assertRaises(Fault): updates.stage_result(self.s,self.token,altered)
        self.finish(1);second=self.record(1);updates.stage_result(self.s,self.token,second)
        with self.assertRaises(Fault): self.s.finalize(self.token,{'stages':[altered,second],'settings':self.report})
        self.assertEqual(self.s.state(self.token)['status'],'awaiting_results')
        self.s.finalize(self.token,{'stages':[rec,second],'settings':self.report})
        self.assertEqual(self.s.state(self.token)['status'],'completed')
    def test_invalid_record_timestamps_and_telemetry_are_rejected(self):
        self.finish(0)
        for changes in [{'acrStarted':float('nan')},{'acrStarted':True},{'acrStarted':float('inf')},{'rawMs':1,'totalMs':1001},{'rawMs':80000,'totalMs':81000},{'stageIndex':False},{'carId':'other'},{'stageId':'other'}]:
            with self.subTest(changes=changes),self.assertRaises(Fault):updates.stage_result(self.s,self.token,{**self.record(0),**changes})
        self.assertFalse(self.s.state(self.token)['results'])
    def test_cannot_submit_without_telemetry(self):
        with self.assertRaises(Fault):updates.stage_result(self.s,self.token,self.record(0))
    def test_checkpoint_private_bounded_and_progress_locked(self):
        self.finish(0);data=self.payload();answer=updates.checkpoint(self.s,self.token,data)
        fetched=updates.checkpoint(self.s,self.token);self.assertEqual(fetched['digest'],answer['digest']);self.assertEqual(gzip.decompress(base64.b64decode(fetched['save'])),b'player-specific-save')
        other=self.s.join(self.ev['id'],'BB')['token']
        with self.assertRaises(Fault):updates.checkpoint(self.s,other)
        for changes in [{'stageIndex':0},{'digest':'fake'},{'save':'not-base64'},{'baseline':{'key':True}},{'settings':{}}]:
            with self.subTest(changes=changes),self.assertRaises(Fault):updates.checkpoint(self.s,self.token,{**data,**changes})
        self.s.start(self.token,self.ev['id'],1,self.car,self.report)
        with self.assertRaises(Fault):updates.checkpoint(self.s,self.token)
    def test_checkpoint_rejects_decompression_bomb(self):
        self.finish(0)
        with self.assertRaises(Fault):updates.checkpoint(self.s,self.token,self.payload(b'x'*(updates.MAX_SAVE+1)))
    def test_pause_forbidden_without_service_or_in_one_sitting(self):
        self.finish(0)
        for changes in [{'allowBreaks':False},{'stages':[self.ev['stages'][0],{**self.ev['stages'][1],'serviceBefore':False}]}]:
            cfg={**self.ev,**changes};self.s.db.execute('UPDATE events SET config=? WHERE id=?',(json.dumps(cfg),self.ev['id']))
            with self.assertRaises(Fault):updates.checkpoint(self.s,self.token,self.payload())
    def test_purge_active_rally_removes_every_dependent_record(self):
        self.finish(0);updates.stage_result(self.s,self.token,self.record(0));updates.checkpoint(self.s,self.token,self.payload())
        self.s.audit('test','create',self.ev['id'],{'name':'private old rally'})
        self.s.start(self.token,self.ev['id'],1,self.car,self.report)
        with self.assertRaises(Fault):self.s.delete_event(self.ev['id'],'wrong')
        self.s.delete_event(self.ev['id'],self.ev['id'])
        for table in ('events','players','results','provisional','rally_checkpoints','admin_audit'):
            self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
        with self.assertRaises(Fault):self.s.state(self.token)
    def test_purge_season_can_keep_or_remove_its_rallies(self):
        from datetime import datetime,timezone,timedelta
        now=datetime.now(timezone.utc)
        payload={'name':'Season','opensAt':(now-timedelta(days=1)).isoformat(),'closesAt':(now+timedelta(days=5)).isoformat(),'generalPoints':[10],'divisionPoints':[5],'powerStagePoints':[1],'teamMode':'combined'}
        season=save_season(self.s,payload)['id'];set_rallies(self.s,season,[self.ev['id']])
        with self.assertRaises(Fault):updates.purge_season(self.s,season,'wrong',True)
        updates.purge_season(self.s,season,season,False);self.assertEqual(len(self.s.listing()),1)
        season=save_season(self.s,payload)['id'];set_rallies(self.s,season,[self.ev['id']]);updates.purge_season(self.s,season,season,True)
        self.assertEqual(self.s.listing(),[])
    def test_branding_escapes_and_validates_invites(self):
        b=club_settings.configure(self.s,{'title':'<script>brand</script>','subtitle':'My Club','tagline':'Custom subtitle','discordInvite':'https://discord.gg/club42'})
        @club_settings.context(self.s)
        def render():return site(self.s)
        page=render();self.assertIn('&lt;script&gt;brand&lt;/script&gt;',page);self.assertNotIn('<script>brand</script>',page);self.assertIn('https://discord.gg/club42',page);self.assertIn('Custom subtitle',page)
        for url in ('javascript:alert(1)','https://discord.gg.evil.test/x','https://user:password@discord.gg/x','https://discord.com/channels/123'):
            with self.assertRaises(Fault):club_settings.configure(self.s,{'discordInvite':url})
        with self.assertRaises(Fault):club_settings.configure(self.s,{'logo':'data:image/svg+xml;base64,PHN2Zz4='})
    def test_catalog_persists_and_keeps_used_ids(self):
        cat=club_settings.catalog(self.s,Path(__file__).resolve().parents[1]);data={k:copy.deepcopy(cat[k]) for k in ('cars','stages')}
        data['stages'].append({'id':'GreeceS9NewRoute','name':'Future stage'});updates_result=club_settings.save_catalog(self.s,data)
        self.assertTrue(updates_result['ok']);self.assertIn('GreeceS9NewRoute',[r['id'] for r in club_settings.catalog(self.s,Path(__file__).resolve().parents[1])['stages']])
        data['cars']=[r for r in data['cars'] if r['id']!=self.car]
        with self.assertRaises(Fault):club_settings.save_catalog(self.s,data)
    def test_archives_and_stage_details_start_collapsed(self):
        p=site(self.s,self.ev['id']);self.assertNotIn('<details class="round" open',p)
        cfg={**self.ev,'opensAt':'2025-01-01T00:00:00Z','closesAt':'2025-01-02T00:00:00Z'}
        self.s.db.execute('UPDATE events SET config=? WHERE id=?',(json.dumps(cfg),cfg['id']))
        page=site(self.s);archive=page.index('<details class="round archive">');self.assertGreater(page.index('Rally Zeli test'),archive)


class UpdateHttpTests(unittest.TestCase):
    setUp=test_admin.AdminHttpTests.setUp
    tearDown=test_admin.AdminHttpTests.tearDown
    send=test_admin.AdminHttpTests.send
    def test_settings_endpoints_need_admin_and_csrf(self):
        self.assertEqual(self.send('GET','/api/admin/branding')[0],401)
        self.assertEqual(self.send('POST','/api/admin/login',{'key':self.auth._secret},{'X-ACR-Admin':'1'})[0],200)
        self.assertEqual(self.send('POST','/api/admin/branding',{'title':'Club'})[0],403)
        self.assertEqual(self.send('POST','/api/admin/branding',{'title':'Club'},{'X-ACR-Admin':'1'})[0],200)
        self.assertEqual(self.send('GET','/api/admin/branding',headers={'X-ACR-Admin':'1'})[1]['title'],'Club')
        self.assertEqual(self.send('GET','/api/catalog')[0],200)


if __name__=='__main__':unittest.main()
