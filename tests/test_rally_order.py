"""Public calendar prioritizes live and imminent rallies at request time."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server_local'))
import i18n
from server import site


class RallyOrderTests(unittest.TestCase):
    now = datetime(2026, 10, 16, 8, tzinfo=timezone.utc)

    def event(self, identifier, opening, closing):
        return {'id': identifier, 'name': identifier, 'location': 'Greece',
                'opensAt': (self.now + timedelta(hours=opening)).isoformat(),
                'closesAt': (self.now + timedelta(hours=closing)).isoformat(),
                'carClass': 'Rally2/R5', 'stages': [{}]}

    def page(self, events, now=None):
        with patch('server.time.time', return_value=(now or self.now).timestamp()):
            return site(SimpleNamespace(listing=lambda: events))

    def ids(self, page):
        return re.findall(r'<h2><a href="/rally/([^"]+)"', page)

    def test_live_then_upcoming_chronologically_then_latest_archive(self):
        events = [self.event('far', 72, 96), self.event('near', 2, 12),
                  self.event('live-new', -1, 3), self.event('live-old', -5, 2),
                  self.event('old', -100, -80), self.event('recent', -12, -2)]
        original = list(events)
        for language in ('pl', 'en'):
            token = i18n._language.set(language)
            try:
                page = self.page(events)
                self.assertEqual(self.ids(page),
                                 ['live-old', 'live-new', 'near', 'far', 'recent', 'old'])
                main, archive = page.split('<details class="round archive">', 1)
                self.assertEqual(self.ids(main), ['live-old', 'live-new', 'near', 'far'])
                self.assertEqual(self.ids(archive), ['recent', 'old'])
                self.assertEqual(events, original)
            finally:
                i18n._language.reset(token)

    def test_boundaries_and_status_are_recomputed_without_server_restart(self):
        events = [self.event('future', 1, 2), self.event('starting', 0, 1),
                  self.event('ending', -1, 0)]
        self.assertEqual(self.ids(self.page(events)), ['ending', 'starting', 'future'])
        later = self.now + timedelta(hours=1)
        page = self.page(events, later)
        main, archive = page.split('<details class="round archive">', 1)
        self.assertEqual(self.ids(main), ['starting', 'future'])
        self.assertEqual(self.ids(archive), ['ending'])

    def test_equal_start_times_have_a_stable_id_tiebreaker_and_offsets(self):
        a, b = self.event('a', 2, 4), self.event('b', 2, 4)
        a['opensAt'] = datetime.fromisoformat(a['opensAt']).astimezone(
            timezone(timedelta(hours=2))).isoformat()
        self.assertEqual(self.ids(self.page([b, a])), ['a', 'b'])
        self.assertEqual(self.ids(self.page([a, b])), ['a', 'b'])


if __name__ == '__main__':
    unittest.main()
