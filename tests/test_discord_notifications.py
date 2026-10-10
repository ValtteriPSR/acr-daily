import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from test_server import event
from server import Store, Fault
from integrity_rules import expected_settings
import discord_notifications as discord

WEBHOOK = 'https://discord.com/api/webhooks/123456789012345678/' + 'a'*60

class DiscordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'db.sqlite3'
        self.store = Store(self.path)
        self.ev = event()
        self.store.import_event(self.ev)
        self.token = self.store.join(self.ev['id'], 'Driver')['token']
        with patch.object(discord.time,'time',return_value=time.time()-10):
            discord.configure(self.store, {'webhook':WEBHOOK,'enabled':True})
        self.worker = discord.Worker(self.store)
    def tearDown(self):
        self.store.db.close();self.tmp.cleanup()
    def test_rejects_invites_ssrf_and_redirect_hosts(self):
        for url in ['https://discord.gg/club','http://discord.com/api/webhooks/123456/'+ 'a'*60,
                    WEBHOOK+'?x=1', WEBHOOK+'#x', WEBHOOK.replace('discord.com','discord.com.attacker.com'),
                    WEBHOOK.replace('discord.com','user@discord.com'), 'https://127.0.0.1/test']:
            with self.assertRaises(Fault):discord.validate_webhook(url)
        self.assertEqual(discord.validate_webhook(WEBHOOK),WEBHOOK)
        self.assertIsNone(discord.NoRedirect().redirect_request(None,None,302,'',{},WEBHOOK))
    def test_settings_hide_token_keep_blank_and_disable(self):
        self.assertNotIn('a'*60,json.dumps(discord.status(self.store)))
        discord.configure(self.store,{'enabled':False})
        self.assertTrue(discord.status(self.store)['configured'])
        self.assertFalse(discord.status(self.store)['enabled'])
        with patch.object(discord,'send') as send:self.worker.tick();send.assert_not_called()
    def test_live_updates_same_message_and_restart_does_not_resend(self):
        with patch.object(discord,'send',return_value='123') as send:
            self.worker.tick();self.assertEqual(send.call_count,1);self.assertIsNone(send.call_args.args[2])
            discord.Worker(self.store).tick();self.assertEqual(send.call_count,1)
            self.store.start(self.token,self.ev['id'],0,'VWPoloGTIR5',expected_settings(self.ev))
            self.worker.tick();self.assertEqual(send.call_args.args[2],'123');self.assertEqual(send.call_count,2)
    def test_provisional_times_explicitly_unverified_and_mentions_disabled(self):
        self.store.start(self.token,self.ev['id'],0,'VWPoloGTIR5',expected_settings(self.ev))
        self.store.stage_end(self.token,self.ev['id'],0,200000,expected_settings(self.ev))
        data=discord.payload(self.store,self.ev['id'],language='en')
        self.assertIn('telemetry 03:20.000 (unverified)',data['embeds'][0]['description'])
        self.assertEqual(data['allowed_mentions'],{'parse':[]})
    def test_summary_waits_for_finish_and_sent_once(self):
        with patch.object(discord,'send',return_value='123') as send:
            self.store.start(self.token,self.ev['id'],0,'VWPoloGTIR5',expected_settings(self.ev))
            self.store.db.execute('UPDATE events SET closes=?',(time.time()-1,))
            self.worker.tick();self.assertEqual(send.call_count,1)
            self.store.dnf(self.token,'test')
            self.worker.tick();self.assertEqual(send.call_count,3)
            self.assertIn('Podsumowanie',send.call_args.args[1]['embeds'][0]['title'])
            discord.Worker(self.store).tick();self.assertEqual(send.call_count,3)
    def test_retries_persist_and_do_not_block_results(self):
        with patch.object(discord,'send',side_effect=discord.DeliveryError('rate limited',120)) as send:
            self.worker.tick();self.worker.tick();self.assertEqual(send.call_count,1)
        self.store.start(self.token,self.ev['id'],0,'VWPoloGTIR5',expected_settings(self.ev))
        self.assertEqual(self.store.state(self.token)['status'],'active')
        self.store.db.execute('UPDATE discord_settings SET next_attempt=0')
        with patch.object(discord,'send',return_value='123'):self.worker.tick()
        self.assertEqual(discord.status(self.store)['lastError'],'')
    def test_test_message_requires_saved_webhook_and_reports_success(self):
        with patch.object(discord,'send',return_value='123') as send:
            self.assertTrue(discord.test_connection(self.store)['ok']);send.assert_called_once()
        self.assertIsNotNone(discord.status(self.store)['lastSent'])
    def test_deleted_live_message_is_recreated_after_retry(self):
        with patch.object(discord,'send',return_value='123'):self.worker.tick()
        self.store.start(self.token,self.ev['id'],0,'VWPoloGTIR5',expected_settings(self.ev))
        self.store.dnf(self.token,'test')
        with patch.object(discord,'send',side_effect=discord.DeliveryError('missing',1,True)):self.worker.tick()
        self.store.db.execute('UPDATE discord_settings SET next_attempt=0')
        with patch.object(discord,'send',return_value='456') as send:
            self.worker.tick();self.assertIsNone(send.call_args.args[2])
    def test_transport_confirms_message_and_uses_patch(self):
        response=io.BytesIO(b'{"id":"123"}')
        with patch.object(discord,'build_opener') as build:
            build.return_value.open.return_value.__enter__.return_value=response
            self.assertEqual(discord.send(WEBHOOK,{'content':'test'},'123'),'123')
            request=build.return_value.open.call_args.args[0]
            self.assertEqual(request.method,'PATCH');self.assertEqual(request.full_url,WEBHOOK+'/messages/123')
    def test_rate_limit_and_error_never_expose_webhook(self):
        error=HTTPError(WEBHOOK,429,'bad',{},io.BytesIO(b'{"retry_after":42}'))
        with patch.object(discord,'build_opener') as build:
            build.return_value.open.side_effect=error
            with self.assertRaises(discord.DeliveryError) as caught:discord.send(WEBHOOK,{'content':'test'})
            self.assertEqual(caught.exception.delay,42);self.assertNotIn('a'*60,str(caught.exception))
            build.return_value.open.side_effect=URLError(WEBHOOK)
            with self.assertRaises(discord.DeliveryError) as caught:discord.send(WEBHOOK,{'content':'test'})
            self.assertNotIn('a'*60,str(caught.exception))

if __name__=='__main__':unittest.main()
