"""Rally season summaries reflect effective scoring and keep admin IDs accessible."""
from html import escape
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server_local'))
import i18n
import season_panel
from rally_details import rally_conditions
from seasons import save_season, set_rallies, set_rally_points, add_group
from server import Store, site
from test_seasons import new_event, new_season


class SeasonRulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'club.sqlite3')
        self.event = new_event()
        self.store.import_event(self.event)
        self.language = i18n._language.set('en')
    def tearDown(self):
        i18n._language.reset(self.language)
        self.store.db.close(); self.temp.cleanup()
    def season(self, **overrides):
        self.sid = save_season(self.store, {**new_season(), **overrides})['id']
        set_rallies(self.store, self.sid, [self.event['id']])
        return self.sid
    def test_standalone_rally_has_no_season_block(self):
        self.assertNotIn('<div class="season-rules"', site(self.store, self.event['id']))
    def test_defaults_eligibility_and_disabled_groups(self):
        self.season()
        page = rally_conditions(self.event, store=self.store)
        self.assertIn('Positions from 1: 35, 25.', page)
        self.assertIn('Other classified finishers: 1 point.', page)
        self.assertIn('5, 4, 3, 2, 1', page)
        self.assertIn('who finish every SS. DNF: 0 points.', page)
        self.assertIn('after the rally closes.', page)
        self.assertIn('No teams configured.', page)
        self.assertIn('<strong>Divisions:</strong> Not configured', page)
        self.assertNotIn('<strong>Division points:', page)
        self.assertIn('/season/' + self.sid, page)
    def test_rally_overrides_and_empty_power_override(self):
        self.season()
        add_group(self.store, self.sid, 'division', 'D1')
        set_rally_points(self.store, self.sid, self.event['id'], [99, 44], [88, 33], [])
        page = rally_conditions(self.event, store=self.store)
        self.assertIn('99, 44', page); self.assertIn('88, 33', page)
        self.assertNotIn('35, 25', page)
        self.assertIn('<strong>Power Stage:</strong> Disabled', page)
        set_rally_points(self.store, self.sid, self.event['id'], None, None, [0])
        self.assertIn('<strong>Power Stage:</strong> Disabled', rally_conditions(self.event, store=self.store))
    def test_all_team_modes_sum_all_members(self):
        for mode, label in [('combined', 'Overall + division + Power Stage'),
                            ('general', 'Overall + Power Stage'), ('division', 'Division points only')]:
            with self.subTest(mode=mode):
                if not hasattr(self, 'sid'): self.season(teamMode=mode)
                else: save_season(self.store, {**new_season(), 'teamMode': mode}, self.sid)
                page = rally_conditions(self.event, store=self.store)
                self.assertIn('Sum of points from all assigned team drivers: ' + label, page)
    def test_polish_page_and_escaped_names(self):
        name = 'Sezon <b>Test & Club</b>'
        self.season(name=name)
        division = 'Dywizja <b>A & B</b>'
        add_group(self.store, self.sid, 'division', division)
        add_group(self.store, self.sid, 'team', 'Club Team')
        token = i18n._language.set('pl')
        try: page = site(self.store, self.event['id'])
        finally: i18n._language.reset(token)
        for label in ('Punktacja generalna', 'Punktacja dywizji', 'Kto punktuje',
                      'Punktacja zespołów', 'Dywizje', 'Suma punktów wszystkich zawodników'):
            self.assertIn(label, page)
        self.assertIn(escape(name), page); self.assertIn(escape(division), page)
        self.assertNotIn(name, page); self.assertNotIn(division, page)
        self.assertNotIn('Nie ustawiono zespołów.', page)
    def test_season_id_on_list_and_editor_in_both_languages(self):
        for language, label in [('en', 'Season ID'), ('pl', 'ID sezonu')]:
            token = i18n._language.set(language)
            try: page = season_panel.html()
            finally: i18n._language.reset(token)
            self.assertIn(label + ': <code class="season-id">${safe(s.id)}</code>', page)
            self.assertIn('id="seasonId"', page)
            self.assertIn("$('seasonId').textContent=detail.id", page)
            self.assertIn('data-delete-season=', page)
            if language == 'pl': self.assertIn('Zapisz ustawienia sezonu', page)


if __name__ == '__main__': unittest.main()
