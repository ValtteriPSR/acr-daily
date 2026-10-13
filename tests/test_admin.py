import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen, HTTPCookieProcessor, build_opener
from urllib.error import HTTPError
from http.cookiejar import CookieJar

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server_local'))
from admin_panel import AdminAuth, load_catalog, validate_catalog_event, html
from server import Store, make_handler
from test_server import event as fixture_event


def build_catalog(root):
    src = root / 'server' / 'src'
    src.mkdir(parents=True)
    with (src / 'cars.js').open('w', encoding='utf-8') as out:
        for i in range(15):
            out.write("{ id: '%s', telemetry: '%s', name: '%s', cls: '%s', group: 'Test' },\n" % (
                ['VWPoloGTIR5','SkodaFabiaRSRally2'][i] if i<2 else 'carid'+str(i),
                'tele'+str(i), 'Car #'+str(i), 'Rally2/R5' if i<3 else 'WR Evo 2'))
    with (src / 'stages.js').open('w', encoding='utf-8') as out:
        out.write("GreeceS3ElatiaCut2Reverse: 'Zeli reverse',\n")
        out.write("GreeceS3ElatiaCut2Forward: 'Zeli forward',\n")
        for i in range(25):
            out.write("GreeceStageRoute%02d: 'Greece Stage %02d',\n" % (i, i))


class AdminHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        build_catalog(self.root)
        self.store = Store(self.root/'club.sqlite3')
        self.auth = AdminAuth(self.root/'admin_key.txt')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, self.auth, self.root))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_address[1])
        self.client = build_opener(HTTPCookieProcessor(CookieJar()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.store.db.close()
        self.thread.join(timeout=1)
        self.temp.cleanup()

    def send(self, method, path, body=None, headers=None, use_cookie=True):
        hdr = dict(headers or {})
        data = None
        if body is not None:
            hdr['Content-Type'] = 'application/json'
            data = json.dumps(body).encode('utf-8')
        req = Request(self.base+path, data=data, method=method, headers=hdr)
        opener = self.client if use_cookie else None
        try:
            with (opener.open(req) if opener else urlopen(req)) as response:
                content = response.read()
                return response.status, (json.loads(content) if response.headers['Content-Type'].startswith('application/json') else content.decode())
        except HTTPError as err:
            return err.code, json.loads(err.read().decode())

    def login(self):
        key = (self.root/'admin_key.txt').read_text().strip()
        code, payload = self.send('POST','/api/admin/login', {'key':key}, {'X-ACR-Admin':'1'})
        self.assertEqual(code, 200, payload)

    def test_administrator_time_penalties_require_admin_and_csrf_header(self):
        from integrity_rules import expected_settings
        ev=fixture_event();self.store.import_event(ev);token=self.store.join(ev['id'],'Penalty driver')['token']
        report=expected_settings(ev);car=ev['allowedCars'][0]
        self.store.start(token,ev['id'],0,car,report);self.store.stage_end(token,ev['id'],0,60000,report)
        payload={'eventId':ev['id'],'playerId':self.store._auth(token)['id'],'stageIndex':0,'amountMs':5000,'reason':'HTTP review'}
        self.assertEqual(self.send('GET','/api/admin/time-penalties?eventId='+ev['id'])[0],401)
        self.assertEqual(self.send('POST','/api/admin/time-penalties',payload,{'X-ACR-Admin':'1'})[0],401)
        self.login()
        self.assertEqual(self.send('POST','/api/admin/time-penalties',payload)[0],403)
        code,record=self.send('POST','/api/admin/time-penalties',payload,{'X-ACR-Admin':'1'})
        self.assertEqual(code,200,record)
        self.assertEqual(self.send('GET','/api/admin/time-penalties?eventId='+ev['id'])[1]['penalties'][0]['amount_ms'],5000)
        self.assertEqual(self.send('POST','/api/admin/time-penalties/revoke',{'eventId':ev['id'],'id':record['id']},{'X-ACR-Admin':'1'})[0],200)

    def test_discord_configuration_requires_admin_and_keeps_secrets_private(self):
        url='https://discord.com/api/webhooks/123456789012345678/'+'a'*60
        self.assertEqual(self.send('GET','/api/admin/discord')[0],401)
        self.login()
        self.assertEqual(self.send('POST','/api/admin/discord',{'webhook':url,'enabled':True})[0],403)
        code,data=self.send('POST','/api/admin/discord',{'webhook':url,'enabled':True},{'X-ACR-Admin':'1'})
        self.assertEqual(code,200);self.assertTrue(data['configured'])
        self.assertNotIn('a'*60,json.dumps(data))
        self.assertEqual(self.send('POST','/api/admin/discord',{'webhook':'https://discord.gg/test','enabled':True},{'X-ACR-Admin':'1'})[0],400)
        audit=self.store.db.execute('SELECT details FROM admin_audit').fetchall()
        self.assertNotIn('a'*60,str([dict(row) for row in audit]))

    def test_admin_auth_csrf_and_create_edit_delete(self):
        from admin_access import admin_path
        secret_path=admin_path(self.auth.key_path)
        self.assertEqual(self.send('GET','/admin')[0],404)
        self.assertEqual(self.send('GET',secret_path)[0],200)
        self.assertEqual(self.send('GET',secret_path+'/seasons')[0],200)
        self.assertEqual(self.send('GET','/api/admin/events')[0], 401)
        self.assertEqual(self.send('POST','/api/admin/login',{'key':'bad'}, {'X-ACR-Admin':'1'})[0], 401)
        self.assertEqual(self.send('POST','/api/admin/login',{'key':self.auth._secret})[0], 403)
        self.login()
        self.assertGreaterEqual(len(self.send('GET','/api/admin/catalog')[1]['cars']),10)
        self.assertEqual(self.send('POST','/api/admin/events',fixture_event())[0], 403)
        config=fixture_event()
        code, created = self.send('POST','/api/admin/events',config, {'X-ACR-Admin':'1'})
        self.assertEqual(code, 200)
        generated_id = created['id']
        self.assertRegex(generated_id, r'^rally-\d{8}-[0-9a-f]{8}$')
        self.assertNotEqual(generated_id, config['id'])
        self.assertEqual(self.send('GET','/api/events')[1]['events'][0]['id'],generated_id)
        # A second create request always makes a new event and generates a new ID.
        code, second = self.send('POST','/api/admin/events',config, {'X-ACR-Admin':'1'})
        self.assertEqual(code, 200)
        self.assertNotEqual(second['id'], generated_id)
        changed=copy.deepcopy(config);changed['name']='Improved Rally Zeli';changed['id']=generated_id
        self.assertEqual(self.send('POST',f'/api/admin/events/{generated_id}',changed, {'X-ACR-Admin':'1'})[0],200)
        self.assertEqual(self.store.event(generated_id)[1]['name'],'Improved Rally Zeli')
        self.assertEqual(self.send('POST',f'/api/admin/events/{generated_id}/delete',{'confirmId':generated_id}, {'X-ACR-Admin':'1'})[0],200)
        self.assertEqual(len(self.send('GET','/api/events')[1]['events']), 1)
        self.assertEqual(self.send('POST','/api/admin/logout',{}, {'X-ACR-Admin':'1'})[0],200)
        self.assertEqual(self.send('GET','/api/admin/events')[0],401)


    def test_admin_auto_id_ignores_untrusted_proposed_id(self):
        self.login()
        config = fixture_event()
        config.pop('id', None)
        code, created = self.send('POST', '/api/admin/events', config, {'X-ACR-Admin':'1'})
        self.assertEqual(code, 200)
        self.assertRegex(created['id'], r'^rally-\d{8}-[0-9a-f]{8}$')
        config['id'] = 'evil-fixed-id'
        code, created2 = self.send('POST', '/api/admin/events', config, {'X-ACR-Admin':'1'})
        self.assertEqual(code, 200)
        self.assertNotEqual(created2['id'], config['id'])
        self.assertNotEqual(created2['id'], created['id'])
        audit_rows = self.store.db.execute('SELECT action, event_id, details FROM admin_audit ORDER BY id').fetchall()
        self.assertTrue(any(row['action']=='create' and row['event_id']==created2['id'] for row in audit_rows))

    def test_login_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.send('POST','/api/admin/login',{'key':'wrong'}, {'X-ACR-Admin':'1'})[0],401)
        # Correct key is blocked for 15 minutes from that IP after brute-force.
        self.assertEqual(self.send('POST','/api/admin/login',{'key':self.auth._secret}, {'X-ACR-Admin':'1'})[0],401)

    def test_admin_audit_contains_before_after_and_no_secrets(self):
        self.login()
        code, created = self.send('POST','/api/admin/events', fixture_event(), {'X-ACR-Admin':'1'})
        self.assertEqual(code, 200)
        conf=self.store.event(created['id'])[1]
        conf['name']='Edited Rally'
        self.assertEqual(self.send('POST',f'/api/admin/events/{created["id"]}',conf,{'X-ACR-Admin':'1'})[0],200)
        actions=[dict(x) for x in self.store.db.execute('SELECT * FROM admin_audit ORDER BY id')]
        self.assertTrue(any(x['action']=='login_ok' for x in actions))
        self.assertTrue(any(x['action']=='create' for x in actions))
        revision=next(x for x in actions if x['action']=='update')
        parsed=json.loads(revision['details'])
        self.assertEqual(parsed['before']['name'],fixture_event()['name'])
        self.assertEqual(parsed['after']['name'],'Edited Rally')
        self.assertNotIn(self.auth._secret,json.dumps(actions))

    def test_registered_event_is_locked(self):
        self.login()
        ev=fixture_event()
        code, created = self.send('POST','/api/admin/events',ev,{'X-ACR-Admin':'1'})
        self.assertEqual(code, 200)
        ev['id'] = created['id']
        self.store.join(ev['id'], 'Somebody')
        changed=copy.deepcopy(ev);changed['name']='Tampered'
        self.assertEqual(self.send('POST',f'/api/admin/events/{ev["id"]}',changed,{'X-ACR-Admin':'1'})[0],409)
        self.assertEqual(self.send('POST',f'/api/admin/events/{ev["id"]}/delete',{}, {'X-ACR-Admin':'1'})[0],400)
        self.assertEqual(self.store.event(ev['id'])[1]['name'],ev['name'])

    def test_catalog_restricts_class_stages_and_rules(self):
        catalog=load_catalog(self.root)
        ev=fixture_event()
        validate_catalog_event(ev,catalog)
        ev['allowedCars']=['carid3']
        with self.assertRaises(ValueError): validate_catalog_event(ev,catalog)
        ev=fixture_event(); ev['stages'][0]['stageId']='GreeceUnknownStage'
        with self.assertRaises(ValueError): validate_catalog_event(ev,catalog)
        ev=fixture_event(); ev['weekend']={'penalty':'invalid','respawn':True,'damage':True,'damageIntensity':'light','wear':'light','failures':'off'}
        with self.assertRaises(ValueError): validate_catalog_event(ev,catalog)

    def test_session_unusable_with_a_different_cookie_jar(self):
        self.login()
        self.assertEqual(self.send('GET','/api/admin/events',use_cookie=False)[0],401)


if __name__=='__main__': unittest.main()
