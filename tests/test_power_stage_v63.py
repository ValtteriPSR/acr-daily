"""Power Stage rules: official last SS result, finish-only, ties, migration and overrides."""
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server_local'))
from server import Store, Fault
from identity_helpers import register_member
from seasons import (DEFAULT_POWER_STAGE, member_by_cookie, club_join,
                     club_player, save_season, season_config, set_rallies,
                     set_rally_points, scoring, install, add_group, assign_member)
from season_panel import PAGE
from season_views import season_detail


def fixture():
    now=datetime.now(timezone.utc)
    return {'id':'power-rally', 'name':'Power Rally','location':'Greece',
       'opensAt':(now-timedelta(hours=1)).isoformat(),
       'closesAt':(now+timedelta(hours=8)).isoformat(),
       'carClass':'Rally2/R5','allowedCars':['VWPoloGTIR5'],
       'stages':[{'stageId':'GreeceS3ElatiaCut2Reverse','weatherGame':'WT_CLEAR','startSeconds':43200},
                 {'stageId':'GreeceS3ElatiaCut2Forward','weatherGame':'WT_CLEAR','startSeconds':43200}]}


class PowerStageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'club.sqlite3'
        self.store=Store(self.db)
        self.store.import_event(fixture())
        now=datetime.now(timezone.utc)
        config={'name':'Test Power Championship','opensAt':(now-timedelta(days=1)).isoformat(),
                'closesAt':(now+timedelta(days=2)).isoformat(), 'generalPoints':[35,25],
                'divisionPoints':[30,20], 'teamMode':'combined'}
        self.sid=save_season(self.store,config)['id']
        set_rallies(self.store,self.sid,['power-rally'])
    def tearDown(self):
        self.store.db.close();self.temp.cleanup()
    def finish(self,nick,first,last,complete=True):
        identity=register_member(self.store,nick)
        mid=member_by_cookie(self.store,identity['token'])['id']
        club_join(self.store,'power-rally',mid)
        row=club_player(self.store,'power-rally',mid)
        self.store.db.execute('UPDATE players SET status=? WHERE id=?',('completed' if complete else 'dnf',row['id']))
        for idx,ms in enumerate((first,last)):
            self.store.db.execute('''INSERT INTO results(player_id,stage_index,stage_id,car_id,
                 raw_ms,penalty_ms,total_ms,acr_started,finished) VALUES(?,?,?,?,?,?,?,?,?)''',
                 (row['id'],idx,fixture()['stages'][idx]['stageId'],'VWPoloGTIR5',ms,0,ms,time.time()-100,time.time()))
        return mid
    def close(self): return scoring(self.store,self.sid,now=time.time()+86400)

    def test_default_configuration_and_not_awarded_early(self):
        self.assertEqual(season_config(self.store,self.sid)['powerStagePoints'],[5,4,3,2,1])
        self.finish('FastOne',100000,300000)
        self.assertEqual(scoring(self.store,self.sid)['drivers'][0]['powerStage'],0)
        self.assertEqual(self.close()['drivers'][0]['powerStage'],5)

    def test_power_stage_ranked_by_final_official_ss_not_rally_total(self):
        self.finish('WinnerOverall',100000,80000)   # total 180000, PS slower
        self.finish('WinnerPower',160000,10000)     # total 170000, PS quicker
        result=self.close()
        r={r['nickname']:r for r in result['drivers']}
        self.assertEqual(r['WinnerPower']['powerStage'],5)
        self.assertEqual(r['WinnerOverall']['powerStage'],4)
        self.assertEqual(result['rallies'][0]['results'][0]['rankPowerStage'],1)
        self.assertIn('Power Stage',season_detail(result))

    def test_tie_dnf_and_no_points_below_configured_rank(self):
        set_rally_points(self.store,self.sid,'power-rally',None,None,[8])
        self.finish('Zeta',120000,20000)
        self.finish('Alpha',100000,20000)
        self.finish('DNF',90000,10000,complete=False)
        out=self.close()
        rs={r['nickname']:r for r in out['drivers']}
        self.assertEqual(rs['Alpha']['powerStage'],8)
        self.assertEqual(rs['Zeta']['powerStage'],8)
        self.assertEqual(rs['DNF']['powerStage'],0)
        rows=out['rallies'][0]['results']
        self.assertEqual([e['rankPowerStage'] for e in rows],[1,1])

    def test_override_restored_after_reordering_and_locked_after_start(self):
        set_rally_points(self.store,self.sid,'power-rally',None,None,[10,7,5])
        self.assertEqual(season_config(self.store,self.sid)['events'][0]['powerStagePoints'],[10,7,5])
        set_rallies(self.store,self.sid,['power-rally'])
        self.assertEqual(season_config(self.store,self.sid)['events'][0]['powerStagePoints'],[10,7,5])
        self.finish('StartLock',10000,20000)
        with self.assertRaises(Fault):set_rally_points(self.store,self.sid,'power-rally',None,None,[100])

    def test_disabled_ps_team_points_and_invalid_values(self):
        team=add_group(self.store,self.sid,'team','Team PS')['id']
        mid=self.finish('TeamDriver',100000,60000)
        # A member who started cannot be assigned retroactively; use unstarted status for test.
        self.store.db.execute('UPDATE players SET status=? WHERE club_member_id=?',('registered',mid))
        assign_member(self.store,self.sid,mid,None,team)
        self.store.db.execute('UPDATE players SET status=? WHERE club_member_id=?',('completed',mid))
        set_rally_points_err=False
        try:set_rally_points(self.store,self.sid,'power-rally',None,None,[])
        except Fault:set_rally_points_err=True
        self.assertTrue(set_rally_points_err)
        self.assertEqual(self.close()['teams'][0]['points'],40) # 35 general + 5 PS; no division
        self.assertIn('powerStage',json.dumps(self.close()))
        with self.assertRaises(Fault):save_season(self.store,{'name':'Some Name','opensAt':fixture()['opensAt'],
           'closesAt':fixture()['closesAt'],'powerStagePoints':['five']})

    def test_migration_of_existing_v62_database_preserves_season(self):
        # SQLite schema evolution simulation: previously installed V6.2 columns absent.
        self.store.db.execute('ALTER TABLE seasons DROP COLUMN power_points')
        self.store.db.execute('ALTER TABLE season_events DROP COLUMN power_points')
        install(self.store)
        self.assertEqual(season_config(self.store,self.sid)['powerStagePoints'],[])  # old standings unchanged
        self.assertEqual(season_config(self.store,self.sid)['events'][0]['powerStagePoints'],None)

    def test_power_stage_can_be_disabled_prestart(self):
        set_rally_points(self.store,self.sid,'power-rally',None,None,[])
        self.finish('NoBonus',100000,50000)
        self.assertEqual(self.close()['drivers'][0]['powerStage'],0)

    def test_sixth_power_stage_finisher_gets_zero(self):
        for i in range(1,7):
            self.finish(f'Power{i}',60000+i*1000,10000+i*1000)
        data=self.close()
        rows=sorted(data['drivers'],key=lambda x:int(x['nickname'][5:]))
        self.assertEqual([r['powerStage'] for r in rows],[5,4,3,2,1,0])
        self.assertTrue(all(r['general']>0 for r in rows))  # finish-point fallback

    def test_html_admin_has_points_input(self):
        for needle in ('id="powerStage"','powerStagePoints','Power Stage','5,4,3,2,1'):
            self.assertIn(needle,PAGE)


if __name__=='__main__':unittest.main()
