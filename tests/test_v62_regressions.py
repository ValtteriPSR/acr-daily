"""Regression suite for preregistration / private route / time and aborted RUN."""
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server_local'))
from server import Store, Fault, site
from seasons import club_register, club_join, member_by_cookie, save_season, set_rallies, mint_club_ticket
from web_launcher import enroll, mint_ticket, redeem_ticket, abort_prestart
from admin_access import admin_path


def fixture(open_delta=timedelta(days=2),close_delta=timedelta(days=7)):
    now=datetime.now(timezone.utc)
    return {'id':'future-rally', 'name':'Upcoming Rally','location':'Greece',
      'opensAt':(now+open_delta).isoformat(), 'closesAt':(now+close_delta).isoformat(),
      'carClass':'Rally2/R5','allowedCars':['VWPoloGTIR5'],
      'stages':[{'stageId':'GreeceS3ElatiaCut2Reverse','weatherGame':'WT_CLEAR','startSeconds':36000},
                {'stageId':'GreeceS3ElatiaCut2Forward','weatherGame':'WT_CLEAR','startSeconds':43200}]}

class RegistrationAndAdminRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.s=Store(Path(self.tmp.name)/'club.sqlite3')
        self.event=fixture()
        self.s.import_event(self.event)
    def tearDown(self):
        self.s.db.close();self.tmp.cleanup()
    def open_now(self):
        self.s.db.execute('UPDATE events SET opens=? WHERE id=?',(0,self.event['id']))
    def test_future_rally_regular_nick_can_register_but_cannot_run(self):
        cookie=enroll(self.s,self.event['id'],'RegularNick')
        self.assertIn('Zapis potwierdzony',site(self.s,self.event['id'], browser={'nickname':'RegularNick','status':'registered'},csrf='csrf'))
        self.assertNotIn('type="submit">RUN RALLY',site(self.s,self.event['id'], browser={'nickname':'RegularNick','status':'registered'},csrf='csrf'))
        with self.assertRaises(Fault) as exc: mint_ticket(self.s,cookie,self.event['id'])
        self.assertEqual(exc.exception.code,409)
        self.open_now()
        ticket=mint_ticket(self.s,cookie,self.event['id'])
        self.assertEqual(redeem_ticket(self.s,ticket)['status'],'registered')
    def test_future_rally_club_member_can_register_but_cannot_run(self):
        member=club_register(self.s,'ClubNick')
        m=member_by_cookie(self.s,member['token'])
        s=datetime.now(timezone.utc)
        se=save_season(self.s,{'name':'Season 2027','opensAt':(s-timedelta(days=1)).isoformat(),
            'closesAt':(s+timedelta(days=30)).isoformat(), 'generalPoints':[35], 'divisionPoints':[30]})
        set_rallies(self.s,se['id'],[self.event['id']])
        club_join(self.s,self.event['id'],m['id'])
        with self.assertRaises(Fault) as exc:mint_club_ticket(self.s,self.event['id'],m['id'])
        self.assertEqual(exc.exception.code,409)
        self.open_now()
        ticket=mint_club_ticket(self.s,self.event['id'],m['id'])
        self.assertEqual(redeem_ticket(self.s,ticket)['nickname'],'ClubNick')
    def test_cannot_register_after_closing(self):
        self.s.db.execute('UPDATE events SET closes=? WHERE id=?',(0,self.event['id']))
        with self.assertRaises(Fault) as exc:enroll(self.s,self.event['id'],'LateNick')
        self.assertEqual(exc.exception.code,409)
    def test_cancel_unstarted_lease_and_retry_does_not_reset_a_run(self):
        self.open_now()
        c=enroll(self.s,self.event['id'],'AbortNick')
        token=redeem_ticket(self.s,mint_ticket(self.s,c,self.event['id']))['token']
        self.assertTrue(abort_prestart(self.s,token)['ok'])
        with self.assertRaises(Fault):self.s.state(token)
        token2=redeem_ticket(self.s,mint_ticket(self.s,c,self.event['id']))['token']
        self.assertNotEqual(token,token2)
        self.s.db.execute('UPDATE players SET status=? WHERE nickname=?',('active','AbortNick'))
        with self.assertRaises(Fault) as exc:abort_prestart(self.s,token2)
        self.assertEqual(exc.exception.code,409)
    def test_private_admin_path_generated_stable_no_public_link(self):
        key=Path(self.tmp.name)/'admin_key.txt'
        first=admin_path(key)
        self.assertRegex(first,r'^/panel-[a-z0-9]{12,80}$')
        self.assertEqual(first,admin_path(key))
        self.assertIn('server_local/admin_route.txt', (Path(__file__).resolve().parents[1]/'.gitignore').read_text().replace('**/admin_route.txt','server_local/admin_route.txt'))
        self.assertNotIn('href="/admin"',site(self.s))
    def test_fixed_utc_plus_2(self):
        ev=fixture(open_delta=timedelta(0),close_delta=timedelta(days=3))
        self.assertIn('UTC+2',site(self.s,self.event['id']))
        panel=(Path(__file__).resolve().parents[1]/'server_local/admin_panel.py').read_text()
        self.assertIn("+':00+02:00'",panel)
        self.assertIn('UTC+2',panel)

if __name__ == '__main__':unittest.main()
