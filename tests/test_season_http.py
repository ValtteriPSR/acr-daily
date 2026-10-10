import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server_local'))
import json
import tempfile
import time
import threading
import http.cookiejar
import re
import unittest
from datetime import datetime,timezone,timedelta
from urllib.request import HTTPCookieProcessor,build_opener,Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from http.server import ThreadingHTTPServer
from server import Store,make_handler
from admin_panel import AdminAuth
from tests.test_seasons import new_event,new_season


class SeasonHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'club.sqlite3')
        self.event=new_event()
        self.store.import_event(self.event)
        self.auth=AdminAuth(Path(self.tmp.name)/'admin_key.txt')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,self.auth))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.jar=http.cookiejar.CookieJar()
        self.browser=build_opener(HTTPCookieProcessor(self.jar))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(1)
        self.store.db.close();self.tmp.cleanup()

    def get(self,path):
        with self.browser.open(self.url+path) as response:
            return response.read().decode()

    def post(self,path,payload):
        data=urlencode(payload).encode()
        headers={'Content-Type':'application/x-www-form-urlencoded','Origin':'null','Sec-Fetch-Site':'same-origin'}
        with self.browser.open(Request(self.url+path,data=data,headers=headers,method='POST')) as response:
            return response.read().decode()

    def ajax(self,path,body):
        payload=json.dumps(body).encode()
        req=Request(self.url+path,data=payload,headers={'X-ACR-Admin':'1','Content-Type':'application/json'},method='POST')
        with self.browser.open(req) as response:
            return json.load(response)

    def csrf(self):
        return next(c.value for c in self.jar if c.name=='acrclub_csrf')

    def test_club_register_enroll_ticket_run_and_stage_table(self):
        self.assertIn('Steam',self.get('/club'))
        page=self.post('/web/club/register',{'nickname':'BrowserSeason','csrf':self.csrf()})
        self.assertIn('kod odzyskiwania',page)
        self.assertTrue(any(c.name=='acrclub_member' for c in self.jar))
        sid=self.ajax('/api/admin/login',{'key':self.auth._secret})
        self.assertTrue(sid['ok'])
        season=self.ajax('/api/admin/seasons',new_season())['id']
        self.ajax('/api/admin/seasons/'+season+'/rallies',{'eventIds':[self.event['id']]})
        self.assertIn('ZAPISZ SIĘ',self.get('/rally/'+self.event['id']))
        self.post('/web/enroll',{'eventId':self.event['id'],'csrf':self.csrf()})
        body=self.get('/rally/'+self.event['id'])
        self.assertIn('RUN RALLY',body)
        self.assertIn('Wyniki poszczególnych OS-ów',body)
        self.assertIn('BrowserSeason',body)
        page=self.post('/web/run',{'eventId':self.event['id'],'csrf':self.csrf()})
        self.assertIn('acrclub://start?ticket=',page)
        self.assertEqual(len(self.store.admin_listing()),1)
        self.assertEqual(len(self.store.db.execute('SELECT * FROM club_members').fetchall()),1)
        self.assertEqual(len(self.store.db.execute('SELECT * FROM players').fetchall()),1)
        self.assertIn('Sezon Testowy',self.get('/seasons'))
        self.assertIn('Klasyfikacja generalna',self.get('/season/'+season))

    def test_admin_protection_and_points_override(self):
        with self.assertRaises(HTTPError) as ctx:
            self.ajax('/api/admin/seasons',new_season())
        self.assertEqual(ctx.exception.code,401)
        self.ajax('/api/admin/login',{'key':self.auth._secret})
        self.assertIn('Punktacja',self.get(__import__('admin_access').admin_path(self.auth.key_path)+'/seasons'))
        sid=self.ajax('/api/admin/seasons',new_season())['id']
        self.ajax('/api/admin/seasons/'+sid+'/rallies',{'eventIds':[self.event['id']]})
        self.ajax('/api/admin/seasons/'+sid+'/rally-points',{'eventId':self.event['id'],
            'generalPoints':[60,40],'divisionPoints':[50,30]})
        with self.browser.open(self.url+'/api/admin/seasons/'+sid) as r:
            config=json.load(r)
        self.assertEqual(config['events'][0]['generalPoints'],[60,40])
        self.assertEqual(config['events'][0]['divisionPoints'],[50,30])
        self.ajax('/api/admin/seasons/'+sid+'/rallies',{'eventIds':[self.event['id']]})
        with self.browser.open(self.url+'/api/admin/seasons/'+sid) as r:
            config=json.load(r)
        self.assertEqual(config['events'][0]['generalPoints'],[60,40])
        self.assertIn('Punkty rajdu',self.get(__import__('admin_access').admin_path(self.auth.key_path)+'/seasons'))

if __name__=='__main__':unittest.main()
