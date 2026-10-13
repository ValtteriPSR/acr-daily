import http.cookiejar
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server_local'))
from server import Store, make_handler, Fault, allowed_browser_origin, allowed_null_local_form_origin
from web_launcher import (browser_player, enroll, mint_ticket, redeem_ticket,
                          LAUNCH_TICKET_SECONDS)
from test_server import event


class BrowserOriginUnit(unittest.TestCase):
    def test_loopback_aliases(self):
        port = 8790
        self.assertTrue(allowed_browser_origin('http://127.0.0.1:8790', 'localhost:8790', port))
        self.assertTrue(allowed_browser_origin('http://localhost:8790', '127.0.0.1:8790', port))
        self.assertTrue(allowed_browser_origin('http://[::1]:8790', 'localhost:8790', port))
        self.assertTrue(allowed_browser_origin('http://LOCALHOST:8790', '127.0.0.1:8790', port))
        self.assertTrue(allowed_browser_origin('http://127.0.0.1:8790', '127.0.0.1:8790', port))

    def test_foreign_origins_are_rejected(self):
        port=8790
        for origin, host in (
            ('null', '127.0.0.1:8790'),
            ('http://evil.example:8790', '127.0.0.1:8790'),
            ('http://localhost:8791', '127.0.0.1:8790'),
            ('http://localhost:8790.evil.example', 'localhost:8790'),
            ('http://localhost:8790/evil', 'localhost:8790'),
            ('http://127.0.0.1:8790', 'evil.example:8790'),
            ('http://localhost:8790', 'localhost:8791'),
            ('http://localhost:bad', 'localhost:8790'),
            ('http://127.0.0.1:8790', 'localhost:bad'),
        ):
            with self.subTest(origin=origin, host=host):
                self.assertFalse(allowed_browser_origin(origin, host, port))



class WebLauncherUnit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'db.sqlite3')
        self.event=event()
        self.store.import_event(self.event)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_ticket_one_use_and_no_username_tampering(self):
        cookie=enroll(self.store,self.event['id'],'Rider123')
        self.assertIsNotNone(browser_player(self.store,cookie,self.event['id']))
        ticket=mint_ticket(self.store,cookie,self.event['id'])
        launch=redeem_ticket(self.store,ticket)
        self.assertEqual(launch['nickname'],'Rider123')
        self.assertEqual(launch['event']['id'],self.event['id'])
        state=self.store.state(launch['token'])
        self.assertEqual(state['status'],'registered')
        with self.assertRaises(Fault):
            redeem_ticket(self.store,ticket)
        fresh=mint_ticket(self.store,cookie,self.event['id'])
        self.assertNotEqual(fresh,ticket)
        with self.assertRaises(Fault):mint_ticket(self.store,cookie,self.event['id'])

    def test_ticket_timeout(self):
        cookie=enroll(self.store,self.event['id'],'Expired')
        ticket=mint_ticket(self.store,cookie,self.event['id'])
        from web_launcher import digest
        with self.store.lock:
            self.store.db.execute('UPDATE launch_tickets SET expires=0 WHERE ticket_hash=?',(digest(ticket),))
        with self.assertRaises(Fault):
            redeem_ticket(self.store,ticket)

    def test_ticket_no_duplicate_before_redemption(self):
        cookie=enroll(self.store,self.event['id'],'SingleClick')
        mint_ticket(self.store,cookie,self.event['id'])
        with self.assertRaises(Fault):
            mint_ticket(self.store,cookie,self.event['id'])

    def test_status_blocks_web_restart(self):
        cookie=enroll(self.store,self.event['id'],'NoReplay')
        ticket=mint_ticket(self.store,cookie,self.event['id'])
        cred=redeem_ticket(self.store,ticket)
        self.store.db.execute("UPDATE players SET status='dnf' WHERE id=?",(cred['playerId'],))
        with self.assertRaises(Fault):
            mint_ticket(self.store,cookie,self.event['id'])


class WebLauncherHTTP(unittest.TestCase):
    def test_browser_form_run_and_redeem(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'db.sqlite3')
            ev=event()
            store.import_event(ev)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store))
            th=threading.Thread(target=server.serve_forever,daemon=True)
            th.start()
            address='http://127.0.0.1:'+str(server.server_address[1])
            jar=http.cookiejar.CookieJar()
            browser=build_opener(HTTPCookieProcessor(jar))
            try:
                with browser.open(address+'/rally/'+ev['id']) as response:
                    body=response.read().decode('utf-8')
                self.assertIn('ZAPISZ SIĘ',body)
                csrf=next(c.value for c in jar if c.name=='acrclub_csrf')
                data=urlencode({'eventId':ev['id'],'nickname':'BrowserDriver','csrf':csrf}).encode()
                with browser.open(Request(address+'/web/enroll',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')) as response:
                    self.assertIn('RUN RALLY',response.read().decode('utf-8'))
                csrf=next(c.value for c in jar if c.name=='acrclub_csrf')
                data=urlencode({'eventId':ev['id'],'csrf':csrf}).encode()
                with browser.open(Request(address+'/web/run',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')) as response:
                    self.assertEqual(response.url,address+'/rally/'+ev['id'])
                    self.assertIn('run-dialog',response.read().decode('utf-8'))
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM launch_tickets').fetchone()[0],0)
                bad=urlencode({'eventId':ev['id'],'csrf':'invalid'}).encode()
                with self.assertRaises(HTTPError) as invalid_csrf:
                    browser.open(Request(address+'/web/run',data=bad,headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'},method='POST'))
                self.assertEqual(invalid_csrf.exception.code,403)
                csrf=next(c.value for c in jar if c.name=='acrclub_csrf')
                data=urlencode({'eventId':ev['id'],'csrf':csrf}).encode()
                with browser.open(Request(address+'/web/run',data=data,headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'},method='POST')) as response:
                    self.assertIn('application/json',response.headers['Content-Type'])
                    page=response.read().decode('utf-8')
                self.assertIn('acrclub://start?ticket=',page)
                import re
                ticket=re.search(r'acrclub://start\?ticket=([\w-]+)',page).group(1)
                payload=json.dumps({'ticket':ticket}).encode()
                old=Request(address+'/api/launcher/redeem',data=payload,
                    headers={'Content-Type':'application/json','X-ACR-Launcher-Version':'6.2.0'},method='POST')
                with self.assertRaises(HTTPError) as incompatible:
                    urlopen(old)
                self.assertEqual(incompatible.exception.code,426)
                req=Request(address+'/api/launcher/redeem',data=payload,headers={'Content-Type':'application/json','X-ACR-Launcher-Version':'0.2.11'},method='POST')
                with urlopen(req) as response:
                    creds=json.load(response)
                self.assertEqual(creds['nickname'],'BrowserDriver')
                self.assertEqual(store.state(creds['token'])['status'],'registered')
                with self.assertRaises(HTTPError) as ex:
                    urlopen(req)
                self.assertEqual(ex.exception.code,401)
            finally:
                server.shutdown()
                server.server_close()
                store.db.close()
                th.join(1)

    def test_enroll_accepts_local_alias_and_rejects_foreign_origin(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'db.sqlite3')
            ev=event(); store.import_event(ev)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store))
            th=threading.Thread(target=server.serve_forever,daemon=True); th.start()
            base='http://127.0.0.1:'+str(server.server_address[1])
            jar=http.cookiejar.CookieJar()
            browser=build_opener(HTTPCookieProcessor(jar))
            try:
                with browser.open(base+'/rally/'+ev['id']) as response:
                    self.assertIn('ZAPISZ SIĘ',response.read().decode())
                csrf=next(c.value for c in jar if c.name=='acrclub_csrf')
                payload=urlencode({'eventId':ev['id'],'nickname':'SafeDriver','csrf':csrf}).encode()
                denied=Request(base+'/web/enroll',data=payload,
                    headers={'Content-Type':'application/x-www-form-urlencoded',
                             'Origin':'http://evil.example'},method='POST')
                with self.assertRaises(HTTPError) as error:
                    browser.open(denied)
                self.assertEqual(error.exception.code,403)
                allowed=Request(base+'/web/enroll',data=payload,
                    headers={'Content-Type':'application/x-www-form-urlencoded',
                             'Origin':'http://localhost:'+str(server.server_address[1])},method='POST')
                with browser.open(allowed) as response:
                    self.assertIn('RUN RALLY',response.read().decode())
            finally:
                server.shutdown(); server.server_close(); store.db.close(); th.join(1)

    def test_cross_site_form_without_csrf_fails(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'db.sqlite3')
            ev=event()
            store.import_event(ev)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store))
            th=threading.Thread(target=server.serve_forever,daemon=True)
            th.start()
            url='http://127.0.0.1:'+str(server.server_address[1])
            try:
                data=urlencode({'eventId':ev['id'],'nickname':'NoCSRF','csrf':'fake'}).encode()
                req=Request(url+'/web/enroll',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')
                with self.assertRaises(HTTPError) as ex:
                    urlopen(req)
                self.assertEqual(ex.exception.code,403)
            finally:
                server.shutdown()
                server.server_close()
                store.db.close()
                th.join(1)



class NullOriginFormTests(unittest.TestCase):
    def test_null_origin_scope(self):
        check = allowed_null_local_form_origin
        self.assertTrue(check('null', '127.0.0.1:8790', 8790, '127.0.0.1', 'same-origin'))
        self.assertTrue(check('null', 'localhost:8790', 8790, '127.0.0.1', None))
        self.assertFalse(check('null', 'evil.example:8790', 8790, '127.0.0.1', 'same-origin'))
        self.assertFalse(check('null', '127.0.0.1:8791', 8790, '127.0.0.1', 'same-origin'))
        self.assertFalse(check('null', '127.0.0.1:8790', 8790, '192.0.2.10', 'same-origin'))
        self.assertFalse(check('null', '127.0.0.1:8790', 8790, '127.0.0.1', 'cross-site'))
        self.assertFalse(check('http://evil.example:8790', '127.0.0.1:8790', 8790, '127.0.0.1', 'same-origin'))

    def test_http_null_origin_enroll_and_run(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'db.sqlite3')
            ev=event(); store.import_event(ev)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store))
            th=threading.Thread(target=server.serve_forever,daemon=True); th.start()
            base='http://127.0.0.1:'+str(server.server_address[1])
            jar=http.cookiejar.CookieJar()
            browser=build_opener(HTTPCookieProcessor(jar))
            try:
                with browser.open(base+'/rally/'+ev['id']) as response:
                    self.assertIn('ZAPISZ SIĘ',response.read().decode())
                csrf=next(c.value for c in jar if c.name=='acrclub_csrf')
                payload=urlencode({'eventId':ev['id'],'nickname':'LocalNullOrigin','csrf':csrf}).encode()
                headers={'Content-Type':'application/x-www-form-urlencoded',
                         'Origin':'null', 'Sec-Fetch-Site':'same-origin'}
                with browser.open(Request(base+'/web/enroll',data=payload,
                                          headers=headers,method='POST')) as response:
                    self.assertIn('RUN RALLY',response.read().decode())
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM players').fetchone()[0],1)
                csrf=next(c.value for c in jar if c.name=='acrclub_csrf')
                payload=urlencode({'eventId':ev['id'],'csrf':csrf}).encode()
                headers['Accept']='application/json'
                with browser.open(Request(base+'/web/run',data=payload,
                                          headers=headers,method='POST')) as response:
                    self.assertIn('acrclub://start?ticket=',response.read().decode())
            finally:
                server.shutdown(); server.server_close(); store.db.close(); th.join(1)

    def test_http_null_origin_bad_csrf_and_cross_site_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'db.sqlite3')
            ev=event(); store.import_event(ev)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store))
            th=threading.Thread(target=server.serve_forever,daemon=True); th.start()
            base='http://127.0.0.1:'+str(server.server_address[1])
            jar=http.cookiejar.CookieJar()
            browser=build_opener(HTTPCookieProcessor(jar))
            try:
                with browser.open(base+'/rally/'+ev['id']) as response:
                    response.read()
                csrf=next(c.value for c in jar if c.name=='acrclub_csrf')
                tests=[('fake', 'same-origin'),(csrf, 'cross-site')]
                for posted, site in tests:
                    with self.subTest(posted=posted,site=site):
                        payload=urlencode({'eventId':ev['id'],'nickname':'BadActor','csrf':posted}).encode()
                        req=Request(base+'/web/enroll',data=payload,
                            headers={'Content-Type':'application/x-www-form-urlencoded',
                                     'Origin':'null','Sec-Fetch-Site':site},method='POST')
                        with self.assertRaises(HTTPError) as err:
                            browser.open(req)
                        self.assertEqual(err.exception.code,403)
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM players').fetchone()[0],0)
            finally:
                server.shutdown(); server.server_close(); store.db.close(); th.join(1)

if __name__=='__main__':
    unittest.main()
