"""Public schedules agree with the actual launcher configuration in both languages."""
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server_local'))
import i18n
from integrity_rules import expected_settings, WEATHERS
from rally_details import stage_schedule, rally_conditions
from server import Store, site
from test_seasons import new_event


class Rows(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.rows = []
        self.current = None
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.current = []

    def handle_data(self, data):
        if self.current is not None: self.current.append(data)

    def handle_endtag(self, tag):
        if tag == 'tr':
            self.rows.append(' '.join(self.current))
            self.current = None


class RallyDetailsTests(unittest.TestCase):
    def setUp(self):
        self.event = new_event()
        self.language = i18n._language.set('en')

    def tearDown(self):
        i18n._language.reset(self.language)

    def test_order_repeated_routes_weather_time_and_actual_service(self):
        stages = self.event['stages']
        stages[0]['serviceBefore'] = False  # Launcher always provides initial service.
        stages[1].update(weatherGame='WT_HEAVY_RAIN', startSeconds=86399)
        stages.extend([deepcopy(stages[0]), deepcopy(stages[1])])
        stages[-1]['serviceBefore'] = True
        rows = Rows(stage_schedule(self.event)).rows[1:]
        self.assertEqual(len(rows), 4)
        self.assertIn('SS 1 Zeli Reverse', rows[0])
        self.assertTrue(rows[0].endswith('Yes'))
        self.assertIn('SS 2 Zeli', rows[1])
        self.assertIn('Heavy rain', rows[1])
        self.assertIn('25%', rows[1])
        self.assertIn('23:59:59', rows[1])
        self.assertTrue(rows[1].endswith('—'))
        self.assertTrue(rows[2].endswith('—'))
        self.assertTrue(rows[3].endswith('Yes'))
        self.assertEqual(expected_settings(self.event)['stages'][0]['zone'], 'ServiceParkDefault')

    def test_all_weather_types_have_human_labels_in_both_languages(self):
        self.event['stages'] = [{**self.event['stages'][0], 'weatherGame': code} for code in WEATHERS]
        for language in ('en', 'pl'):
            token = i18n._language.set(language)
            try:
                page = stage_schedule(self.event)
                self.assertNotIn('WT_', page)
                self.assertEqual(len(Rows(page).rows), len(WEATHERS) + 1)
                self.assertIn('20%', page)
                self.assertIn('25%', page)
            finally: i18n._language.reset(token)

    def test_conditions_defaults_overrides_and_disabled_damage(self):
        page = rally_conditions(self.event)
        for value in ('Damage', 'Light', 'Mechanical failures', 'Off', 'Starting position',
                      '<dd>1</dd>', 'Optimal', 'By stage weather', '0%', 'Fixed'):
            self.assertIn(value, page)
        self.event['weekend'] = dict(damage=False, damageIntensity='realistic', wear='severe',
                                     failures='realistic', penalty='realistic', respawn=False)
        page = rally_conditions(self.event)
        self.assertIn('<dt>Damage</dt><dd>Off</dd>', page)
        self.assertIn('<dt>Wear</dt><dd>Severe</dd>', page)
        self.assertIn('<dt>Mechanical failures</dt><dd>Realistic</dd>', page)
        self.assertIn('<dt>Car respawn</dt><dd>Disabled</dd>', page)
        self.assertIn('<dt>Penalty mode</dt><dd>Realistic</dd>', page)

    def test_route_names_are_escaped(self):
        with patch('rally_details.load_catalog', return_value={'stages': [
            {'id': self.event['stages'][0]['stageId'], 'name': '<script>alert("x")</script>'}]}):
            page = stage_schedule(self.event)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>', page)

    def test_full_rally_page_polish_and_long_schedule(self):
        self.event['stages'] = [deepcopy(self.event['stages'][i % 2]) for i in range(40)]
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder)/'club.sqlite3')
            try:
                store.import_event(self.event)
                token = i18n._language.set('pl')
                try: page = site(store, self.event['id'])
                finally: i18n._language.reset(token)
                self.assertIn('<h2>Harmonogram</h2>', page)
                self.assertIn('<h2>Warunki</h2>', page)
                self.assertIn('OS 40', page)
                self.assertIn('Serwis przed OS', page)
                self.assertIn('Bezchmurnie', page)
                self.assertIn('Pozycja startowa', page)
                self.assertIn('Wyniki poszczególnych OS-ów', page)
                self.assertIn('class="rally-side"', page)
            finally: store.db.close()


if __name__ == '__main__': unittest.main()
