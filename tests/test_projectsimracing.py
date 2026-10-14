"""Zmiany Project Simracing: zegar serwera, nicki, czas polski, eksport wyników, motyw."""
import json
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server_local'))
sys.path.insert(0, str(ROOT / 'tests'))
import timing_guard
from server import Store, Fault, make_handler, nick_key
from admin_panel import AdminAuth
from integrity_rules import expected_settings
from identity_helpers import register_member
from seasons import club_join, mint_club_ticket, save_season, set_rallies, add_group, assign_member
from web_launcher import redeem_ticket
from test_server import event


class TimingGuardTests(unittest.TestCase):
    def setUp(self):
        self.saved = (timing_guard.HARD_LIMIT_MS, timing_guard.REVIEW_LIMIT_MS)
        timing_guard.HARD_LIMIT_MS, timing_guard.REVIEW_LIMIT_MS = 30_000, 10_000
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'c.sqlite3')
        self.ev = event()
        self.store.import_event(self.ev)
        member = register_member(self.store, 'Kierowca')
        club_join(self.store, self.ev['id'], member['memberId'])
        launch = redeem_ticket(self.store, mint_club_ticket(self.store, self.ev['id'], member['memberId']))
        self.token, self.pid = launch['token'], launch['playerId']
        self.settings = expected_settings(self.ev)

    def tearDown(self):
        timing_guard.HARD_LIMIT_MS, timing_guard.REVIEW_LIMIT_MS = self.saved
        self.store.db.close()
        self.tmp.cleanup()

    def start(self, stage, seconds_ago):
        self.store.start(self.token, self.ev['id'], stage, 'VWPoloGTIR5', self.settings)
        timing_guard.record_start(self.store, self.pid, stage, time.time() - seconds_ago)

    def test_instant_fabricated_stage_is_dnf(self):
        self.store.start(self.token, self.ev['id'], 0, 'VWPoloGTIR5', self.settings)
        with self.assertRaises(Fault) as caught:
            self.store.stage_end(self.token, self.ev['id'], 0, 180_000, self.settings)
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.store.state(self.token)['status'], 'dnf')

    def test_realistic_stage_and_long_pause_are_accepted(self):
        self.start(0, 185)  # 180 s jazdy + odliczanie/sieć
        self.assertEqual(self.store.stage_end(self.token, self.ev['id'], 0, 180_000, self.settings)['status'], 'ready')
        self.start(1, 3600)  # godzina pauzy w trakcie OS-u: timer gry stoi, to dozwolone
        self.assertEqual(self.store.stage_end(self.token, self.ev['id'], 1, 200_000, self.settings)['status'],
                         'awaiting_results')
        self.assertEqual(timing_guard.flags(self.store, self.pid), [])

    def test_small_mismatch_is_flagged_for_review_not_dnf(self):
        self.start(0, 150)
        self.store.stage_end(self.token, self.ev['id'], 0, 165_000, self.settings)  # 15 s „za długo”
        self.assertEqual(self.store.state(self.token)['status'], 'ready')
        self.assertIn('do weryfikacji', timing_guard.flags(self.store, self.pid)[0])

    def test_official_result_older_than_attempt_is_rejected(self):
        self.start(0, 200)
        self.store.stage_end(self.token, self.ev['id'], 0, 195_000, self.settings)
        self.start(1, 200)
        self.store.stage_end(self.token, self.ev['id'], 1, 195_000, self.settings)
        old = time.time() - 3 * 3600  # wynik z treningu sprzed 3 godzin w tym samym .sav
        timing_guard.record_start(self.store, self.pid, 0, time.time() - 200)
        with self.store.lock:
            self.store.db.execute('UPDATE players SET created=? WHERE id=?', (old - 3600, self.pid))
        rows = [{'stageIndex': i, 'stageId': s['stageId'], 'carId': 'VWPoloGTIR5', 'rawMs': 195_000,
                 'penaltyMs': 0, 'totalMs': 195_000, 'acrStarted': (old if i == 0 else time.time() - 150)}
                for i, s in enumerate(self.ev['stages'])]
        with self.assertRaises(Fault):
            self.store.finalize(self.token, {'stages': rows, 'settings': self.settings})


class NicknameTests(unittest.TestCase):
    def test_polish_letters_allowed(self):
        self.assertEqual(nick_key('Błotny Żółw_1')[0], 'Błotny Żółw_1')

    def test_lookalike_scripts_rejected(self):
        for nick in ('Zibimаn96', 'Αdam', 'Nick​', 'a<b>'):
            with self.subTest(nick=nick), self.assertRaises(Fault):
                nick_key(nick)

    def test_fullwidth_is_normalized(self):
        self.assertEqual(nick_key('Ｋamyk')[0], 'Kamyk')


class PolishTimeTests(unittest.TestCase):
    def test_summer_and_winter(self):
        from local_time import label
        self.assertEqual(label('2026-10-24T18:00:00Z'), '24.10.2026 · 20:00')
        self.assertEqual(label('2026-10-25T19:00:00Z'), '25.10.2026 · 20:00')
        self.assertEqual(label('2026-03-29T01:00:00Z'), '29.03.2026 · 03:00')


class PublicPagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'c.sqlite3')
        now = datetime.now(timezone.utc)
        ev = event()
        ev['opensAt'] = (now - timedelta(days=3)).isoformat()
        self.store.import_event(ev)
        sid = save_season(self.store, {'name': 'ACR Sezon testowy', 'opensAt': (now - timedelta(days=10)).isoformat(),
                                       'closesAt': (now + timedelta(days=10)).isoformat()})['id']
        div = add_group(self.store, sid, 'division', 'PSR1')['id']
        set_rallies(self.store, sid, [ev['id']])
        member = register_member(self.store, 'Kamyk')
        assign_member(self.store, sid, member['memberId'], div, None)
        self.auth = AdminAuth(Path(self.tmp.name) / 'k.txt')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, self.auth))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.store.db.close()
        self.tmp.cleanup()

    def get(self, path, headers=None):
        with urlopen(Request(self.base + path, headers=headers or {})) as r:
            return r.read(), r.headers

    def test_export_matches_league_sheet_format_and_cors(self):
        body, headers = self.get('/api/ps/wyniki', {'Origin': 'http://localhost:8000'})
        data = json.loads(body)
        self.assertEqual(data['title'], 'ACR Sezon testowy')
        self.assertEqual(data['sheets'][0]['name'], 'Klasyfikacja generalna')
        self.assertIn('Kierowca', data['sheets'][0]['headers'])
        self.assertEqual(data['sheets'][0]['rows'][0][1], 'Kamyk')
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'http://localhost:8000')
        meta = json.loads(self.get('/api/ps/wyniki?meta=1')[0])
        self.assertEqual(set(meta), {'title', 'updated'})
        _, foreign = self.get('/api/ps/wyniki', {'Origin': 'https://evil.example'})
        self.assertIsNone(foreign['Access-Control-Allow-Origin'])

    def test_calendar_export(self):
        events = json.loads(self.get('/api/ps/kalendarz')[0])['events']
        self.assertEqual(events[0]['round'], 1)
        self.assertEqual(events[0]['location'], 'Grecja')

    def test_theme_assets_and_navigation(self):
        page = self.get('/')[0].decode()
        self.assertIn('https://projectsimracing.pl/wyniki.html?champ=acr', page)
        self.assertIn('class="language-switch"', page)
        self.assertIn('/static/ps/saira-condensed-800.woff2', page)
        font, headers = self.get('/static/ps/saira-condensed-800.woff2')
        self.assertEqual(headers['Content-Type'], 'font/woff2')
        for bad in ('/static/ps/../server.py', '/static/ps/admin_key.txt'):
            with self.subTest(path=bad), self.assertRaises(Exception):
                self.get(bad)


if __name__ == '__main__':
    unittest.main()


class LegacyHostTests(unittest.TestCase):
    """Przejście z acr-rally-club.onrender.com na własną domenę."""

    def test_browser_redirected_launcher_api_kept(self):
        import http.client
        from unittest.mock import patch
        import public_security
        import server as srv
        new, old, secret = 'https://acr.projectsimracing.pl', 'acr-rally-club.onrender.com', 'g' * 64
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(srv, 'PUBLIC_URL', new), patch.object(public_security, 'PUBLIC_URL', new), \
                patch.object(public_security, 'GATEWAY_SECRET', secret), \
                patch.object(public_security, 'REDIRECT_HOSTS', {old}):
            store = srv.Store(Path(folder) / 'c.sqlite3')
            web = ThreadingHTTPServer(('127.0.0.1', 0), srv.make_handler(store, srv.AdminAuth(Path(folder) / 'k.txt')))
            threading.Thread(target=web.serve_forever, daemon=True).start()

            def get(path, headers):
                c = http.client.HTTPConnection('127.0.0.1', web.server_port, timeout=5)
                c.request('GET', path, headers={'X-ACR-Gateway': secret, **headers})
                r = c.getresponse(); out = (r.status, r.getheader('Location')); r.read(); c.close()
                return out
            try:
                # Render: Caddy podmienia Host na nową domenę, oryginał w X-Forwarded-Host
                proxied = {'Host': 'acr.projectsimracing.pl', 'X-Forwarded-Host': old}
                self.assertEqual(get('/seasons?x=1', proxied), (301, new + '/seasons?x=1'))
                self.assertEqual(get('/api/events', proxied)[0], 200)
                self.assertEqual(get('/seasons', {'Host': 'acr.projectsimracing.pl'})[0], 200)
                self.assertEqual(get('/seasons', {'Host': 'evil.example', 'X-Forwarded-Host': 'evil.example'})[0], 403)
            finally:
                web.shutdown(); web.server_close(); store.db.close()

    def test_menu_name(self):
        from site_theme import shell
        self.assertIn('Klub AC Rally', shell('t', '<p>x</p>'))
