import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server_local'))
import unittest
import tempfile
import time
from datetime import datetime,timezone,timedelta
from server import Store,Fault,site,make_handler
from identity_helpers import register_member
from seasons import (member_by_cookie,club_join,
                     save_season,set_rallies,add_group,assign_member,
                     scoring,season_config,club_player, mint_club_ticket,
                     rename_group, delete_group, set_rally_points, set_team_capacity, ensure_division_assigned)
from web_launcher import redeem_ticket


def new_event(ident='greece-one'):
    now=datetime.now(timezone.utc)
    return {'id':ident,'name':'Rally Club '+ident,'location':'Greece',
      'opensAt':(now-timedelta(hours=1)).isoformat(),
      'closesAt':(now+timedelta(days=2)).isoformat(),
      'carClass':'Rally2/R5','allowedCars':['VWPoloGTIR5'],
      'stages':[{'stageId':'GreeceS3ElatiaCut2Reverse','weatherGame':'WT_CLEAR','startSeconds':43200},
                {'stageId':'GreeceS3ElatiaCut2Forward','weatherGame':'WT_CLEAR','startSeconds':50000}]}


def new_season():
    now=datetime.now(timezone.utc)
    return {'name':'Sezon Testowy 2026','opensAt':(now-timedelta(days=3)).isoformat(),
            'closesAt':(now+timedelta(days=40)).isoformat(),
            'generalPoints':[35,25],'divisionPoints':[30,20], 'teamMode':'combined'}


class SeasonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.s=Store(Path(self.temp.name)/'db.sqlite3')
        self.e=new_event()
        self.s.import_event(self.e)
        self.sid=save_season(self.s,new_season())['id']
        set_rallies(self.s,self.sid,[self.e['id']])

    def tearDown(self):
        self.s.db.close();self.temp.cleanup()

    def test_round_status_dates_and_exact_start_end_boundaries(self):
        from season_views import season_detail
        from i18n import _language
        opening=datetime(2026,10,24,22,30,tzinfo=timezone.utc).timestamp()
        closing=datetime(2026,10,25,22,30,tzinfo=timezone.utc).timestamp()
        self.s.db.execute('UPDATE events SET opens=?,closes=? WHERE id=?',
                          (opening,closing,self.e['id']))
        for now,started,closed in [(opening-1,False,False),(opening,True,False),
                                   (closing-1,True,False),(closing,True,True)]:
            data=scoring(self.s,self.sid,now=now);rally=data['rallies'][0]
            self.assertEqual((rally['started'],rally['closed']),(started,closed))
            self.assertEqual(datetime.fromisoformat(rally['opensAt']).timestamp(),opening)
            self.assertEqual(datetime.fromisoformat(rally['closesAt']).timestamp(),closing)
            for lang in ('pl','en'):
                token=_language.set(lang)
                try:page=season_detail(data)
                finally:_language.reset(token)
                self.assertNotIn('PROVISIONAL',page)
                self.assertNotIn('PROWIZORYCZNIE',page)
                if closed:
                    self.assertIn('PUNKTY ZATWIERDZONE' if lang=='pl' else 'POINTS FINALIZED',page)
                elif started:
                    self.assertIn(('TRWA - koniec: ' if lang=='pl' else 'LIVE - ends: ')+
                                  '25.10.2026 · 23:30',page)
                else:
                    self.assertIn(('Jeszcze nie wystartował. Start - ' if lang=='pl' else
                                   'Not started yet. Start - ')+'25.10.2026 · 00:30',page)

    def test_live_round_uses_live_status_even_without_results(self):
        from season_views import season_detail
        data=scoring(self.s,self.sid)
        self.assertFalse(data['rallies'][0]['results'])
        page=season_detail(data)
        self.assertIn('TRWA - koniec: ',page)
        self.assertNotIn('PROWIZORYCZNIE',page)

    def register(self,nick):
        a=register_member(self.s,nick)
        m=member_by_cookie(self.s,a['token'])
        return a,m

    def test_club_identity_persists_and_ticket_uses_same_nick(self):
        a,m=self.register('My Driver')
        self.assertEqual(m['nickname'],'My Driver')
        with self.assertRaises(Fault):register_member(self.s,'MY DRIVER')
        club_join(self.s,self.e['id'],m['id'])
        self.assertEqual(club_player(self.s,self.e['id'],m['id'])['nickname'],'My Driver')
        self.assertEqual(len(season_config(self.s,self.sid)['assignments']),1)
        ticket=mint_club_ticket(self.s,self.e['id'],m['id'])
        info=redeem_ticket(self.s,ticket)
        self.assertEqual(info['nickname'],'My Driver')
        with self.assertRaises(Fault):redeem_ticket(self.s,ticket)
        with self.assertRaises(Fault):club_join(self.s,self.e['id'],m['id'])
        self.assertIn('My Driver',site(self.s,self.e['id']))

    def test_points_ties_dnf_fallback_and_divisions(self):
        d1=add_group(self.s,self.sid,'division','Dywizja 1')['id']
        d2=add_group(self.s,self.sid,'division','Dywizja 2')['id']
        t1=add_group(self.s,self.sid,'team','Team Alfa')['id']
        t2=add_group(self.s,self.sid,'team','Team Beta')['id']
        mids=[]
        for nick,division,team,total,status in [
            ('Anna',d1,t1,100000,'completed'),('Bartek',d2,t1,100000,'completed'),
            ('Cezary',d1,t2,130000,'completed'),('Darek',d2,t2,90000,'dnf')]:
            _,m=self.register(nick);mid=m['id'];mids.append(mid)
            club_join(self.s,self.e['id'],mid)
            assign_member(self.s,self.sid,mid,division,team)
            p=club_player(self.s,self.e['id'],mid)
            self.s.db.execute('UPDATE players SET status=? WHERE id=?',(status,p['id']))
            if status=='completed':
                for idx in (0,1):
                    self.s.db.execute('''INSERT INTO results
                        (player_id,stage_index,stage_id,car_id,raw_ms,penalty_ms,total_ms,acr_started,finished)
                        VALUES(?,?,?,?,?,?,?,?,?)''',
                        (p['id'],idx,self.e['stages'][idx]['stageId'],'VWPoloGTIR5',total//2,0,total//2,
                         time.time()-10+idx,time.time()))
        provisional=scoring(self.s,self.sid)
        self.assertEqual(provisional['rallies'][0]['results'][0]['pointsGeneral'],0)
        out=scoring(self.s,self.sid,now=time.time()+4*86400)
        result={p['nickname']:p for p in out['drivers']}
        self.assertEqual((result['Anna']['general'],result['Anna']['division']),(35,30))
        self.assertEqual((result['Bartek']['general'],result['Bartek']['division']),(35,30))
        self.assertEqual((result['Cezary']['general'],result['Cezary']['division']),(1,20))
        self.assertEqual((result['Darek']['general'],result['Darek']['division']),(0,0))
        self.assertEqual(out['teams'][0]['points'],140)  # +5 Power Stage for each tied finisher
        self.assertEqual(out['rallies'][0]['results'][2]['rankGeneral'],3)
        # Post-start members cannot be moved to another team or division.
        with self.assertRaises(Fault):assign_member(self.s,self.sid,mids[0],d2,t2)
        with self.assertRaises(Fault):save_season(self.s,{**new_season(),'generalPoints':[500]},self.sid)
        with self.assertRaises(Fault):set_rallies(self.s,self.sid,[])

    def test_team_capacity_division_limit_and_validation(self):
        team=add_group(self.s,self.sid,'team','Capacity')['id']
        for i in range(10):
            _,m=self.register(f'P{i:02d}')
            assign_member(self.s,self.sid,m['id'],None,team)
        _,extra=self.register('Eleventh')
        with self.assertRaises(Fault):assign_member(self.s,self.sid,extra['id'],None,team)
        for i in range(10):add_group(self.s,self.sid,'division',f'Division {i}')
        with self.assertRaises(Fault):add_group(self.s,self.sid,'division','Division 11')
        with self.assertRaises(Fault):save_season(self.s,{**new_season(),'divisionPoints':[30,-1]})

    def test_multiple_events_same_member_and_season_rounds(self):
        second=new_event('greece-two');self.s.import_event(second)
        set_rallies(self.s,self.sid,[self.e['id'],second['id']])
        _,m=self.register('OneNick')
        club_join(self.s,self.e['id'],m['id'])
        club_join(self.s,second['id'],m['id'])
        self.assertEqual(len(season_config(self.s,self.sid)['events']),2)
        self.assertEqual(len(season_config(self.s,self.sid)['assignments']),1)
        self.assertIn('OneNick',site(self.s,second['id']))

    def test_per_rally_point_override_and_capacity(self):
        division=add_group(self.s,self.sid,'division','Division Alpha')['id']
        team=add_group(self.s,self.sid,'team','Tiny Team',capacity=1)['id']
        _,m1=self.register('TopDriver')
        _,m2=self.register('NextDriver')
        club_join(self.s,self.e['id'],m1['id'])
        club_join(self.s,self.e['id'],m2['id'])
        with self.assertRaises(Fault):ensure_division_assigned(self.s,self.e['id'],m1['id'])
        assign_member(self.s,self.sid,m1['id'],division,team)
        with self.assertRaises(Fault):assign_member(self.s,self.sid,m2['id'],division,team)
        with self.assertRaises(Fault):set_team_capacity(self.s,self.sid,team,0)
        set_team_capacity(self.s,self.sid,team,2)
        assign_member(self.s,self.sid,m2['id'],division,team)
        set_rally_points(self.s,self.sid,self.e['id'],[45],[32])
        self.assertEqual(season_config(self.s,self.sid)['events'][0]['generalPoints'],[45])
        set_rallies(self.s,self.sid,[self.e['id']])
        self.assertEqual(season_config(self.s,self.sid)['events'][0]['generalPoints'],[45])
        for rank,mid in enumerate([m1['id'],m2['id']],1):
            p=club_player(self.s,self.e['id'],mid)
            self.s.db.execute('UPDATE players SET status=? WHERE id=?',('completed',p['id']))
            for ix,stage in enumerate(self.e['stages']):
                self.s.db.execute('INSERT INTO results(player_id,stage_index,stage_id,car_id,raw_ms,penalty_ms,total_ms,acr_started,finished) VALUES(?,?,?,?,?,?,?,?,?)',
                    (p['id'],ix,stage['stageId'],'VWPoloGTIR5',100000*rank,0,100000*rank,time.time()-1,time.time()))
        rows=scoring(self.s,self.sid,now=time.time()+4*86400)['rallies'][0]['results']
        self.assertEqual((rows[0]['pointsGeneral'],rows[0]['pointsDivision']),(45,32))
        self.assertEqual((rows[1]['pointsGeneral'],rows[1]['pointsDivision']),(1,1))
        with self.assertRaises(Fault):set_rally_points(self.s,self.sid,self.e['id'],[50],[50])
        with self.assertRaises(Fault):set_team_capacity(self.s,self.sid,team,1)

    def test_rally_limit_and_immutable_identity(self):
        with self.assertRaises(Fault):set_rallies(self.s,self.sid,['greece-one']*101)
        with self.assertRaises(Fault):set_rallies(self.s,self.sid,['missing'])
        _,m=self.register('Stable')
        club_join(self.s,self.e['id'],m['id'])
        with self.assertRaises(Fault):club_join(self.s,self.e['id'],m['id'])
        ids=add_group(self.s,self.sid,'division','Testing')['id']
        rename_group(self.s,self.sid,'division',ids,'New Name')
        delete_group(self.s,self.sid,'division',ids)

if __name__=='__main__':unittest.main()
