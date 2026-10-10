"""V6 smoke + security: public reverse-proxy boundary, install config and docs."""
from __future__ import annotations
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import os

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server_local'))
sys.path.insert(0,str(ROOT/'tools'))
import server, public_security
import configure_public_launcher


class PublicConfigurationTests(unittest.TestCase):
    def test_public_url_requires_https_origin(self):
        for bad in ('http://example.org','https://example.org/abc','https://u:p@example.org','javascript:alert(1)'):
            with self.assertRaises(ValueError):configure_public_launcher.validate_url(bad)
        self.assertEqual(configure_public_launcher.validate_url('https://liga.example.org/'), 'https://liga.example.org')

    def test_gateway_key_and_host(self):
        with patch.object(public_security,'PUBLIC_URL','https://liga.example.org'),patch.object(public_security,'GATEWAY_SECRET','c'*64):
            self.assertFalse(public_security.gateway_ok({}))
            self.assertFalse(public_security.gateway_ok({'X-ACR-Gateway':'bad'}))
            self.assertTrue(public_security.gateway_ok({'X-ACR-Gateway':'c'*64}))
            self.assertTrue(public_security.check_host({'Host':'liga.example.org'}))
            self.assertFalse(public_security.check_host({'Host':'attacker.com'}))
            self.assertTrue(public_security.browser_origin('https://liga.example.org',{}))
            self.assertFalse(public_security.browser_origin('https://attacker.com',{}))
            self.assertTrue(public_security.browser_origin('null',{'Sec-Fetch-Site':'same-origin'}))
            self.assertTrue(public_security.browser_origin('null',{}))
            self.assertFalse(public_security.browser_origin('null',{'Sec-Fetch-Site':'cross-site'}))

    def test_rate_limit(self):
        limit=public_security.RateLimiter()
        self.assertTrue(limit.allow('1.1.1.1','register',2))
        self.assertTrue(limit.allow('1.1.1.1','register',2))
        self.assertFalse(limit.allow('1.1.1.1','register',2))
        self.assertTrue(limit.allow('2.2.2.2','register',2))

    def test_server_guide_and_download_in_public_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(server,'PUBLIC_URL','https://liga.example.org'),patch.object(public_security,'PUBLIC_URL','https://liga.example.org'),patch.object(public_security,'GATEWAY_SECRET','z'*64),patch.object(server,'DOWNLOAD_URL','https://github.com/example/example/releases/latest/download/ACR-Rally-Club-Setup.exe'):
                store=server.Store(Path(folder)/'db.sqlite3')
                auth=server.AdminAuth(Path(folder)/'admin.txt')
                web=ThreadingHTTPServer(('127.0.0.1',0),server.make_handler(store,auth))
                t=threading.Thread(target=web.serve_forever,daemon=True)
                t.start()
                def get(path,headers):
                    c=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=5)
                    c.request('GET',path,headers=headers)
                    r=c.getresponse();out=(r.status,dict(r.getheaders()),r.read().decode());c.close();return out
                try:
                    good={'Host':'liga.example.org','X-ACR-Gateway':'z'*64}
                    self.assertEqual(get('/guide',{'Host':'liga.example.org'})[0],403)
                    self.assertEqual(get('/guide',{'Host':'attacker.com','X-ACR-Gateway':'z'*64})[0],403)
                    ok=get('/guide',good)
                    self.assertEqual(ok[0],200)
                    self.assertIn('START STAGE',ok[2])
                    self.assertIn('Strict-Transport-Security',ok[1])
                    dl=get('/download',good)
                    self.assertEqual(dl[0],302)
                    self.assertTrue(dl[1]['Location'].startswith('https://github.com/'))
                    from admin_access import admin_path
                    self.assertEqual(get('/admin',good)[0],404)
                    self.assertEqual(get(admin_path(auth.key_path),good)[0],200)  # Caddy protects private path
                    c=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=5)
                    c.request('POST','/api/join',body='{"eventId":"x","nickname":"bad"}',headers={**good,'Content-Type':'application/json'})
                    r=c.getresponse(); self.assertEqual(r.status,403);r.read();c.close()
                finally:
                    web.shutdown();web.server_close();store.db.close()

if __name__=='__main__': unittest.main()
