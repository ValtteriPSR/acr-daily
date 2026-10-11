"""HTTP localization, request isolation and user-data regression tests."""
import concurrent.futures
import http.cookiejar
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server_local'))
from admin_access import admin_path
from admin_panel import AdminAuth
from i18n import safe_return_path
from server import Store, make_handler
from test_server import event


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'club.sqlite3')
        self.event = event()
        self.event['name'] = 'Rajdy <English & Polski>'
        self.store.import_event(self.event)
        self.auth = AdminAuth(Path(self.tmp.name) / 'admin_key.txt')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, self.auth))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.jar = http.cookiejar.CookieJar()
        self.browser = build_opener(HTTPCookieProcessor(self.jar))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)
        self.store.db.close()
        self.tmp.cleanup()

    def get(self, path):
        with self.browser.open(self.base + path) as response:
            return response.read().decode(), response.headers, response.url

    def switch(self, chosen, target='/'):
        return self.get('/language?' + urlencode({'lang': chosen, 'next': target}))

    def test_switch_preserves_page_and_persists(self):
        page, headers, url = self.switch('en', '/club?view=profile')
        self.assertEqual(url, self.base + '/club?view=profile')
        self.assertIn('<html lang="en">', page)
        self.assertIn('Sign in through Steam', page)
        self.assertEqual(headers['Content-Language'], 'en')
        cookie = next(c for c in self.jar if c.name == 'acrclub_language')
        self.assertEqual(cookie.value, 'en')
        self.assertIn('HttpOnly', cookie._rest)
        self.assertEqual(cookie._rest['SameSite'], 'Lax')
        self.assertIn('Results and standings', self.get('/seasons')[0])
        self.assertIn('Zaloguj się przez Steam', self.switch('pl', '/club')[0])

    def test_public_and_admin_templates_are_translated(self):
        self.switch('en')
        cases = [('/', 'Rallies and events'), ('/club', 'Sign in through Steam'),
                 ('/guide', 'Every stage has one attempt.'),
                 ('/launcher', 'Download Windows installer'),
                 ('/seasons', 'Results and standings'),
                 ('/rally/' + self.event['id'], 'Individual stage results'),
                 (admin_path(self.auth.key_path), 'Administrator sign-in'),
                 (admin_path(self.auth.key_path) + '/seasons', 'Save season settings')]
        for path, expected in cases:
            with self.subTest(path=path):
                page = self.get(path)[0]
                self.assertIn(expected, page)
                self.assertIn('aria-label="English"', page)
                self.assertIn('<html lang="en">', page)
                self.assertNotIn('Punktacja', page)
                self.assertNotIn('Zaloguj', page)
        self.assertIn('Punktacja', self.switch('pl', admin_path(self.auth.key_path) + '/seasons')[0])

    def test_user_names_and_api_data_are_not_translated(self):
        self.switch('en')
        page = self.get('/')[0]
        self.assertIn('Rajdy &lt;English &amp; Polski&gt;', page)
        self.assertNotIn('Rallies &lt;English', page)
        data = json.loads(self.get('/api/events')[0])
        self.assertEqual(data['events'][0]['name'], self.event['name'])

    def test_language_does_not_leak_between_requests(self):
        def fetch(chosen):
            request = Request(self.base + '/', headers={'Cookie': 'acrclub_language=' + chosen})
            with urlopen(request) as response:
                page = response.read().decode()
                return response.headers['Content-Language'], page
        choices = ['en', 'pl', 'en', 'pl', 'invalid', 'en']
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(fetch, choices))
        for chosen, (header, page) in zip(choices, results):
            expected = 'en' if chosen == 'en' else 'pl'
            self.assertEqual(header, expected)
            self.assertIn('<html lang="' + expected + '">', page)
        self.assertIn('Rajdy i wydarzenia', self.get('/')[0])

    def test_registration_errors_use_selected_language(self):
        page = self.switch('en', '/club')[0]
        from test_steam_auth import authenticated_pending
        pending = authenticated_pending(self.store)
        self.jar.set_cookie(http.cookiejar.Cookie(0,'acrclub_steam_pending',pending,None,False,
            '127.0.0.1',False,False,'/',True,False,None,True,None,None,{}))
        csrf = next(c.value for c in self.jar if c.name == 'acrclub_csrf')
        request = Request(self.base + '/web/club/register',
                          data=urlencode({'nickname': 'x', 'csrf': csrf}).encode(),
                          headers={'Origin': self.base,
                                   'Content-Type': 'application/x-www-form-urlencoded'})
        with self.assertRaises(HTTPError) as caught:
            self.browser.open(request)
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.loads(caught.exception.read())['error'], 'Nickname: 2–24 characters')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM club_members').fetchone()[0], 0)

    def test_switch_rejects_external_redirects_and_invalid_languages(self):
        for target in ['https://example.com', '//example.com', '/\\example.com', '/\nexample.com']:
            self.assertEqual(safe_return_path(target), '/')
            self.assertEqual(self.switch('en', target)[2], self.base + '/')
        with self.assertRaises(HTTPError) as caught:
            self.switch('fr')
        self.assertEqual(caught.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
