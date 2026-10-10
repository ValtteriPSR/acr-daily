"""Steam assertion verification, migration, nickname integrity and real HTTP flow."""
from datetime import datetime, timezone
import http.cookiejar
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server_local'))
import steam_auth as steam
import server
from server import Store, Fault, make_handler
from admin_panel import AdminAuth
from seasons import (steam_finish, member_by_cookie, change_nickname, club_register,
                     club_recover, club_join, club_player, club_logout)
from public_security import launcher_release_page
from test_seasons import new_event


def assertion(store, origin='https://league.example.com', steam_id='76561198012345678', nonce=None):
    url, state = steam.start(store, origin)
    return_to = parse_qs(urlsplit(url).query)['openid.return_to'][0]
    return state, {
        'state':state, 'openid.ns':steam.NAMESPACE, 'openid.mode':'id_res',
        'openid.op_endpoint':steam.ENDPOINT, 'openid.return_to':return_to,
        'openid.claimed_id':'https://steamcommunity.com/openid/id/' + steam_id,
        'openid.identity':'https://steamcommunity.com/openid/id/' + steam_id,
        'openid.response_nonce':nonce or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')+state,
        'openid.assoc_handle':'handle', 'openid.sig':'signed-by-steam',
        'openid.signed':'op_endpoint,claimed_id,identity,return_to,response_nonce,assoc_handle'}


def authenticated_pending(store, steam_id='76561198012345678'):
    state, values = assertion(store, steam_id=steam_id)
    with patch.object(steam, 'verify_with_steam', return_value=True):
        return steam.callback(store, urlencode(values), state, 'https://league.example.com')


class SteamIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'club.sqlite3')

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_requires_valid_signature_before_creating_session(self):
        state, values = assertion(self.store)
        with patch.object(steam, 'verify_with_steam', return_value=False):
            with self.assertRaises(Fault):
                steam.callback(self.store, urlencode(values), state, 'https://league.example.com')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM steam_pending_sessions').fetchone()[0], 0)

    def test_provider_verification_posts_only_to_fixed_steam_endpoint(self):
        with patch.object(steam,'build_opener') as opener:
            response=opener.return_value.open.return_value.__enter__.return_value
            response.status=200
            response.read.return_value=('ns:'+steam.NAMESPACE+'\nis_valid:true\n').encode()
            self.assertTrue(steam.verify_with_steam({'openid.mode':'id_res','openid.op_endpoint':'https://attacker.com','state':'private-state'}))
            sent=opener.return_value.open.call_args.args[0]
            self.assertEqual(sent.full_url,steam.ENDPOINT)
            body=parse_qs(sent.data.decode())
            self.assertEqual(body['openid.mode'],['check_authentication'])
            self.assertNotIn('state',body)
            response.read.return_value=b'is_valid:false\n'
            self.assertFalse(steam.verify_with_steam({}))

    def test_expired_pending_login_cannot_create_account(self):
        pending=authenticated_pending(self.store)
        self.store.db.execute('UPDATE steam_pending_sessions SET expires=0')
        with self.assertRaises(Fault):steam_finish(self.store,pending,'Late Driver')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM club_members').fetchone()[0],0)

    def test_forged_state_provider_identity_signed_fields_and_return_url(self):
        for field, value in [('state','X'*43), ('openid.op_endpoint','https://attacker.com'),
                             ('openid.claimed_id','https://attacker.com/openid/id/76561198012345678'),
                             ('openid.identity','https://steamcommunity.com/openid/id/76561198012345679'),
                             ('openid.return_to','https://attacker.com/callback'),
                             ('openid.signed','return_to'), ('openid.response_nonce','2020-01-01T00:00:00Zold')]:
            state, values = assertion(self.store)
            values[field] = value
            with patch.object(steam, 'verify_with_steam') as verify:
                with self.subTest(field=field), self.assertRaises(Fault):
                    steam.callback(self.store,urlencode(values),state,'https://league.example.com')
                verify.assert_not_called()

    def test_callback_and_nonce_are_single_use(self):
        state, values = assertion(self.store)
        with patch.object(steam, 'verify_with_steam', return_value=True):
            steam.callback(self.store,urlencode(values),state,'https://league.example.com')
            with self.assertRaises(Fault):
                steam.callback(self.store,urlencode(values),state,'https://league.example.com')
            other, replay = assertion(self.store,nonce=values['openid.response_nonce'])
            with self.assertRaises(Fault):
                steam.callback(self.store,urlencode(replay),other,'https://league.example.com')

    def test_duplicate_query_and_expired_state_are_rejected(self):
        state, values = assertion(self.store)
        with self.assertRaises(Fault):
            steam.callback(self.store,urlencode(values)+'&state='+state,state,'https://league.example.com')
        self.store.db.execute('UPDATE steam_login_states SET expires=0')
        with self.assertRaises(Fault):
            steam.callback(self.store,urlencode(values),state,'https://league.example.com')

    def test_nickname_onboarding_and_repeat_steam_signin_keep_one_identity(self):
        pending=authenticated_pending(self.store)
        self.assertIsNone(steam_finish(self.store,pending))
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM club_members').fetchone()[0],0)
        account=steam_finish(self.store,pending,'Club Driver')
        member=member_by_cookie(self.store,account['token'],steam_only=True)
        self.assertEqual(member['nickname'],'Club Driver')
        again=steam_finish(self.store,authenticated_pending(self.store))
        self.assertEqual(again['memberId'],account['memberId'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM club_members').fetchone()[0],1)
        with self.assertRaises(Fault):steam_finish(self.store,pending,'Another Driver')

    def test_rename_preserves_rally_attempt_and_identity(self):
        account=steam_finish(self.store,authenticated_pending(self.store),'Old Driver')
        event=new_event();self.store.import_event(event)
        club_join(self.store,event['id'],account['memberId'])
        before=club_player(self.store,event['id'],account['memberId'])
        change_nickname(self.store,account['token'],'New Driver')
        after=club_player(self.store,event['id'],account['memberId'])
        for key in ('id','club_member_id','status','token_hash','stage_index','created'):
            self.assertEqual(after[key],before[key],key)
        self.assertEqual(after['nickname'],'New Driver')
        with self.assertRaises(Fault):club_join(self.store,event['id'],account['memberId'])

    def test_rename_collision_rolls_back_and_legacy_sessions_cannot_edit(self):
        one=steam_finish(self.store,authenticated_pending(self.store),'First Driver')
        two=steam_finish(self.store,authenticated_pending(self.store,'76561198012345679'),'Second Driver')
        with self.assertRaises(Fault):change_nickname(self.store,one['token'],'second driver')
        self.assertEqual(member_by_cookie(self.store,one['token'])['nickname'],'First Driver')
        legacy=club_register(self.store,'Legacy Driver')
        self.assertIsNone(member_by_cookie(self.store,legacy['token'],steam_only=True))
        with self.assertRaises(Fault):change_nickname(self.store,legacy['token'],'Other Driver')

    def test_link_legacy_account_preserves_entries_and_revokes_old_session(self):
        legacy=club_register(self.store,'Legacy Driver')
        member=member_by_cookie(self.store,legacy['token'])
        event=new_event();self.store.import_event(event);club_join(self.store,event['id'],member['id'])
        linked=steam_finish(self.store,authenticated_pending(self.store),'Legacy Driver',legacy['recovery'])
        self.assertEqual(linked['memberId'],member['id'])
        self.assertIsNotNone(club_player(self.store,event['id'],member['id']))
        self.assertIsNone(member_by_cookie(self.store,legacy['token']))
        with self.assertRaises(Fault):club_recover(self.store,'Legacy Driver',legacy['recovery'])
        with self.assertRaises(Fault):steam_finish(self.store,authenticated_pending(self.store,'76561198012345679'),'Legacy Driver',legacy['recovery'])

    def test_pending_and_club_logout_revoke_tokens(self):
        pending=authenticated_pending(self.store)
        club_logout(self.store,None,pending)
        self.assertIsNone(steam.pending_steam_id(self.store,pending))
        account=steam_finish(self.store,authenticated_pending(self.store),'Driver')
        club_logout(self.store,account['token'])
        self.assertIsNone(member_by_cookie(self.store,account['token']))

    def test_download_redirects_to_latest_installer(self):
        self.assertEqual(launcher_release_page('https://github.com/example/club/releases/download/v0.2.1/setup.exe'),
                         'https://github.com/example/club/releases/latest/download/ACR-Rally-Club-Setup.exe')
        self.assertEqual(launcher_release_page('https://github.com/example/club/releases/latest/download/setup.exe'),
                         'https://github.com/example/club/releases/latest/download/ACR-Rally-Club-Setup.exe')
        with self.assertRaises(ValueError):launcher_release_page('https://attacker.com/setup.exe')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None


class SteamHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'club.sqlite3')
        self.web=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,AdminAuth(Path(self.tmp.name)/'admin.txt')))
        self.thread=threading.Thread(target=self.web.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.web.server_port)
        self.jar=http.cookiejar.CookieJar()
        self.browser=build_opener(HTTPCookieProcessor(self.jar))
        self.direct=build_opener(HTTPCookieProcessor(self.jar),NoRedirect)

    def tearDown(self):
        self.web.shutdown();self.web.server_close();self.thread.join(1);self.store.db.close();self.tmp.cleanup()

    def get(self,path):
        with self.browser.open(self.origin+path) as response:return response.read().decode()

    def post(self,path,payload):
        csrf=next(c.value for c in self.jar if c.name=='acrclub_csrf')
        request=Request(self.origin+path,data=urlencode({**payload,'csrf':csrf}).encode(),
                        headers={'Content-Type':'application/x-www-form-urlencoded','Origin':self.origin})
        with self.browser.open(request) as response:return response.read().decode()

    def test_browser_flow_onboarding_edit_logout_and_repeated_signin(self):
        self.assertIn('Steam',self.get('/club'))
        with self.assertRaises(HTTPError) as redirect:self.direct.open(self.origin+'/auth/steam')
        self.assertEqual(redirect.exception.code,303)
        provider=parse_qs(urlsplit(redirect.exception.headers['Location']).query)
        state=next(c.value for c in self.jar if c.name=='acrclub_steam_state')
        _,values=assertion(self.store,self.origin)
        values['state']=state;values['openid.return_to']=provider['openid.return_to'][0]
        with patch.object(steam,'verify_with_steam',return_value=True):
            page=self.get('/auth/steam/callback?'+urlencode(values))
        self.assertIn('Steam',page)
        self.assertTrue(any(c.name=='acrclub_steam_pending' for c in self.jar))
        page=self.post('/web/club/register',{'nickname':'Steam Driver'})
        self.assertIn('Steam Driver',page)
        self.assertFalse(any(c.name=='acrclub_steam_pending' for c in self.jar))
        page=self.post('/web/club/nickname',{'nickname':'New Steam Driver'})
        self.assertIn('New Steam Driver',page)
        self.post('/web/club/logout',{})
        self.assertFalse(any(c.name=='acrclub_member' for c in self.jar))
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM club_members').fetchone()[0],1)

    def test_public_mode_rejects_anonymous_registration(self):
        self.get('/club')
        with patch.object(server,'PUBLIC_URL',self.origin), patch.object(server,'browser_origin',return_value=True):
            with self.assertRaises(HTTPError) as failed:self.post('/web/club/register',{'nickname':'Anonymous Driver'})
        self.assertEqual(failed.exception.code,401)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM club_members').fetchone()[0],0)
