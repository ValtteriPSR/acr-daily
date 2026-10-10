"""V5.1 presentation smoke tests (no database/network required)."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server_local'))
from season_views import season_list, season_detail
from site_theme import shell
from admin_panel import html as admin_html
from season_panel import html as season_admin_html

class UIPresentationTests(unittest.TestCase):
    def test_navigation(self):
        page = shell('Test', '<p>Content</p>', active='seasons')
        self.assertIn('href="/seasons" aria-current="page"', page)
        self.assertNotIn('href="/admin"', page)
        self.assertIn('class="sitebar"', page)

    def test_season_listing_escapes_user_text(self):
        page = season_list([{'id':'xx','name':'<script>alert(1)</script>',
                             'opensAt':'2026-01-01T10:00:00Z',
                             'closesAt':'2026-06-01T10:00:00Z','rallyCount':2}])
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('Wyniki i klasyfikacje', page)

    def test_season_tabs_and_search(self):
        data = {
           'season':{'id':'season','name':'Season','closesAt':'2027-10-01T10:00:00Z','teamMode':'combined'},
           'drivers':[{'nickname':'TestDriver','finishes':1,'general':35,'division':30,'total':65}],
           'divisions':[{'id':1,'name':'Pro Division','drivers':[{'nickname':'TestDriver','finishes':1,'general':35,'division':30,'total':65}]}],
           'teams':[],'rallies':[]
        }
        page=season_detail(data)
        self.assertIn('data-target-panel="div-1"',page)
        self.assertIn('id="driver-search"',page)
        self.assertIn('data-driver="TestDriver"',page)
        self.assertIn('data-driver=',page)
        self.assertIn('Punkty',page)

    def test_admin_forms_and_js_retained(self):
        for render in [admin_html,season_admin_html]:
            html=render()
            self.assertIn('class="sitebar"',html)
            self.assertIn('class="acr-admin"',html)
            self.assertIn('<script>',html)
            self.assertIn('/api/admin/login',html)

if __name__=='__main__': unittest.main()
