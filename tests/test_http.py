import json
import sys
import tempfile
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
import unittest
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server_local'))
from server import Store, make_handler
from test_server import event

class HTTPTests(unittest.TestCase):
    def test_page_join_and_authenticated_state(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Store(Path(folder)/'db.sqlite3')
            ev=event()
            db.import_event(ev)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db))
            th=threading.Thread(target=server.serve_forever,daemon=True)
            th.start()
            try:
                address='http://127.0.0.1:'+str(server.server_address[1])
                with urlopen(address+'/') as stream:
                    homepage=stream.read().decode('utf-8')
                self.assertIn('ACR Rally Club',homepage)
                self.assertIn('Rally Zeli test',homepage)
                with urlopen(Request(address+'/api/join',
                        data=json.dumps({'eventId':ev['id'],'nickname':'Driver One'}).encode(),
                        headers={'Content-Type':'application/json'},method='POST')) as stream:
                    token=json.load(stream)['token']
                with urlopen(Request(address+'/api/me',
                        headers={'Authorization':'Bearer '+token})) as stream:
                    state=json.load(stream)
                self.assertEqual(state['status'],'registered')
                self.assertEqual(state['nickname'],'Driver One')
                self.assertEqual(len(state['event']['stages']),2)
            finally:
                server.shutdown()
                server.server_close()
                db.db.close()
                th.join(1)
