"""Idle SQL budget, fresh critical reads, archive retention, and deletion."""
import base64
import json
import sys
import time
import unittest
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'server_local'),str(ROOT/'tests')]
import test_update024 as fixture
import telemetry_audit as audit
import discord_notifications as discord
import attempt_updates
import admin_penalties
from server import Fault
from seasons import save_season,set_rallies,member_by_cookie,_new_session
from identity_helpers import register_member
from idle_database import READ_TTL


class Probe:
    def __init__(self,raw):self.raw,self.calls=raw,0
    def execute(self,*args):
        self.calls+=1
        return self.raw.execute(*args)
    def __getattr__(self,name):return getattr(self.raw,name)


class IdleOptimizationTests(unittest.TestCase):
    setUp=fixture.UpdateStoreTests.setUp
    tearDown=fixture.UpdateStoreTests.tearDown
    finish=fixture.UpdateStoreTests.finish
    record=fixture.UpdateStoreTests.record

    def probe(self):
        raw=Probe(self.s.db.raw)
        self.s.db.raw=raw
        return raw

    def test_half_hour_idle_workers_issue_zero_sql(self):
        self.s.listing()
        worker=discord.Worker(self.s);worker.tick()
        probe=self.probe();now=time.time()
        for offset in range(30,1801,30):
            with patch('time.time',return_value=now+offset):
                self.s._sweep();worker.tick()
        self.assertEqual(probe.calls,0)

    def test_repeated_idle_boards_use_zero_sql_after_warmup(self):
        self.s.board(self.ev['id'])
        probe=self.probe()
        for _ in range(100):self.s.board(self.ev['id'])
        self.assertEqual(probe.calls,0)

    def test_first_join_and_start_after_idle_reach_database(self):
        self.s.board(self.ev['id']);probe=self.probe()
        token=self.s.join(self.ev['id'],'Fresh Driver')['token']
        self.s.start(token,self.ev['id'],0,self.car,self.report)
        self.assertGreater(probe.calls,0)
        self.assertEqual(self.s.state(token)['status'],'active')
        self.assertIn('Fresh Driver',str(self.s.board(self.ev['id'])))

    def test_cached_rows_are_detached_and_committed_writes_visible(self):
        row=self.s.db.execute('SELECT id,config FROM events').fetchone()
        row['config']='broken'
        self.assertNotEqual(self.s.db.execute('SELECT id,config FROM events').fetchone()['config'],'broken')
        self.s.db.execute('UPDATE events SET opens=opens+1')
        self.assertEqual(self.s.db.execute('SELECT opens FROM events').fetchone()[0],
                         self.s.db.raw.execute('SELECT opens FROM events').fetchone()[0])

    def test_transaction_bypasses_cache_and_rollback_keeps_original(self):
        sql='SELECT nickname FROM players WHERE token_hash IS NOT NULL'
        original=self.s.db.execute(sql).fetchone()[0]
        self.s._begin();self.s.db.execute("UPDATE players SET nickname='Changed'")
        self.assertEqual(self.s.db.execute(sql).fetchone()[0],'Changed')
        self.s.db.execute('ROLLBACK')
        self.assertEqual(self.s.db.execute(sql).fetchone()[0],original)

    def test_expired_cache_rechecks_database_only_on_request(self):
        sql='SELECT id FROM events'
        self.s.db.execute(sql);probe=self.probe()
        with patch('time.monotonic',return_value=time.monotonic()+READ_TTL+1):
            self.s.db.execute(sql)
        self.assertEqual(probe.calls,1)

    def test_session_expiration_and_revocation_apply_to_cached_identity(self):
        member=register_member(self.s,'Session Driver')
        token=_new_session(self.s,member['memberId'],steam_verified=True)
        self.assertIsNotNone(member_by_cookie(self.s,token))
        expiry=self.s.db.execute('SELECT expires FROM club_sessions').fetchone()[0]
        with patch('seasons._now',return_value=expiry+1):
            self.assertIsNone(member_by_cookie(self.s,token))
        self.s.db.execute('DELETE FROM club_sessions')
        self.assertIsNone(member_by_cookie(self.s,token))

    def test_heartbeat_and_result_deadlines_remain_enforced(self):
        self.s.start(self.token,self.ev['id'],0,self.car,self.report)
        self.s._sweep()
        with patch('time.time',return_value=time.time()+self.s.inactive+1):
            self.s._sweep()
            self.assertEqual(self.s.state(self.token)['status'],'dnf')

    def test_heartbeat_extends_deadline(self):
        now=time.time();self.s.start(self.token,self.ev['id'],0,self.car,self.report)
        with patch('time.time',return_value=now+60):
            self.s.heartbeat(self.token,self.ev['id'],0,self.report)
        with patch('time.time',return_value=now+121):
            self.s._sweep();self.assertEqual(self.s.state(self.token)['status'],'active')

    def test_compressed_and_legacy_traces_are_lossless(self):
        data={'points':[[i,i*.1,0,50,.5,.1,0,2,4000,False] for i in range(12)],'dropped':0}
        raw=json.dumps(data,separators=(',',':'));packed=audit.pack_payload(raw)
        self.assertLess(len(packed),len(raw))
        self.assertEqual(audit.unpack_payload(packed),data)
        self.assertEqual(audit.unpack_payload(raw),data)
        bomb='z1:'+base64.b64encode(zlib.compress(b'x'*65537)).decode()
        with self.assertRaises(ValueError):audit.unpack_payload(bomb)

    def trace_and_results(self):
        self.s.start(self.token,self.ev['id'],0,self.car,self.report)
        audit.submit(self.s,self.token,{'eventId':self.ev['id'],'stageIndex':0,'seq':0,
            'points':[[1000,0,0,50,.5,.1,0,2,4000,False]],'dropped':0})
        self.s.stage_end(self.token,self.ev['id'],0,60000,self.report,5000)
        record={**self.record(0),'penaltyMs':5000,'totalMs':65000}
        attempt_updates.stage_result(self.s,self.token,record)
        pid=self.s._auth(self.token)['id']
        admin_penalties.add(self.s,{'eventId':self.ev['id'],'playerId':pid,'stageIndex':0,'amountMs':3000,'reason':'Preserve penalty'})
        return pid

    def season(self,ends):
        now=datetime.now(timezone.utc)
        sid=save_season(self.s,{'name':'Archive','opensAt':(now-timedelta(days=60)).isoformat(),
                              'closesAt':(now+timedelta(days=10)).isoformat()})['id']
        # Seed historical membership without asking the admin API to move an
        # already driven rally into a season (correctly forbidden in production).
        self.s.db.execute('INSERT INTO season_events(season_id,event_id,position) VALUES(?,?,?)',(sid,self.ev['id'],1))
        self.s.db.execute('UPDATE seasons SET closes=? WHERE id=?',(ends.timestamp(),sid))
        return sid

    def test_waiting_at_service_does_not_expire_like_an_active_stage(self):
        self.finish(0)
        with patch('time.time',return_value=time.time()+1800):
            self.s._sweep()
            self.assertEqual(self.s.state(self.token)['status'],'ready')

    def test_missing_official_result_timeout_is_unchanged(self):
        self.finish(0);self.finish(1)
        with patch('time.time',return_value=time.time()+601):
            self.s._sweep()
            self.assertEqual(self.s.state(self.token)['status'],'dnf')

    def test_archive_cleanup_keeps_every_result_and_penalty(self):
        self.trace_and_results();self.season(datetime.now(timezone.utc)-timedelta(days=1))
        now=time.time()
        self.s.db.execute('UPDATE events SET closes=?',(now-7*86400-1,))
        before={t:[dict(r) for r in self.s.db.execute('SELECT * FROM '+t)] for t in
                ('results','provisional','telemetry_penalties','admin_time_penalties','stage_starts')}
        audit.expire(self.s,now+31)
        for t in ('telemetry_chunks','telemetry_runs'):
            self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0],0)
        for t,rows in before.items():self.assertEqual([dict(r) for r in self.s.db.execute('SELECT * FROM '+t)],rows)

    def test_active_season_and_first_week_keep_telemetry(self):
        self.trace_and_results();sid=self.season(datetime.now(timezone.utc)+timedelta(days=1))
        now=time.time();self.s.db.execute('UPDATE events SET closes=?',(now-8*86400,))
        audit.expire(self.s,now+31)
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM telemetry_chunks').fetchone()[0],1)
        self.s.db.execute('UPDATE seasons SET closes=? WHERE id=?',(now-1,sid))
        self.s.db.execute('UPDATE events SET closes=?',(now-6*86400,))
        audit.expire(self.s,now+62)
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM telemetry_chunks').fetchone()[0],1)

    def test_manual_deletion_removes_rows_and_cached_results(self):
        pid=self.trace_and_results();sid=self.season(datetime.now(timezone.utc)+timedelta(days=1))
        self.s.audit('local','example',self.ev['id'],{'eventId':self.ev['id']})
        self.s.db.execute('INSERT INTO discord_deliveries(delivery_key,message_id,digest) VALUES(?,?,?)',
                          ('g:'+self.ev['id']+':live','123','abc'))
        self.s.board(self.ev['id'])
        self.s.delete_event(self.ev['id'],self.ev['id'])
        for table in ('events','players','results','provisional','telemetry_chunks','telemetry_runs',
                      'telemetry_penalties','admin_time_penalties','stage_starts','timing_flags',
                      'rally_checkpoints','rally_recovery','rally_save_problems','launch_tickets',
                      'launch_leases','web_sessions','season_events','admin_audit','discord_deliveries'):
            self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0,table)
        with self.assertRaises(Fault):self.s.board(self.ev['id'])
        self.assertEqual(self.s.db.execute('SELECT id FROM seasons').fetchone()[0],sid)


if __name__=='__main__':unittest.main()
