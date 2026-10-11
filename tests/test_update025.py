"""Telemetry penalty floors and confirmed break regressions, no production writes."""
import struct
from types import SimpleNamespace
from unittest import mock
import test_update024 as fixtures
import unittest
import attempt_updates as updates
from server import Fault


class LivePenaltyTests(unittest.TestCase):
    setUp=fixtures.UpdateStoreTests.setUp
    tearDown=fixtures.UpdateStoreTests.tearDown
    finish=fixtures.UpdateStoreTests.finish
    record=fixtures.UpdateStoreTests.record
    payload=fixtures.UpdateStoreTests.payload
    def test_telemetry_floor_cannot_be_reduced_by_save_or_later_frame(self):
        self.s.start(self.token,self.ev['id'],0,self.car,self.report)
        self.s.heartbeat(self.token,self.ev['id'],0,self.report,3000)
        self.s.stage_end(self.token,self.ev['id'],0,60000,self.report,0)
        row=self.s.board(self.ev['id'])['stageResults'][0]
        self.assertEqual(row['penalty_ms'],3000);self.assertEqual(row['total_ms'],63000)
        rec=self.record(0)
        with self.assertRaisesRegex(Fault,'lower than live telemetry'): updates.stage_result(self.s,self.token,rec)
        rec.update(penaltyMs=3000,totalMs=63000)
        updates.stage_result(self.s,self.token,rec)

    def test_late_results_screen_penalty_has_same_finish_and_never_decreases(self):
        self.finish(0)
        for value in (4000,1000,0):
            updates.late_penalty(self.s,self.token,dict(stageIndex=0,clockMs=60000,penaltyMs=value))
        self.assertEqual(self.s.board(self.ev['id'])['stageResults'][0]['penalty_ms'],4000)
        for change in ({'stageIndex':1},{'clockMs':61000},{'penaltyMs':True},{'penaltyMs':-1}):
            with self.assertRaises(Fault):updates.late_penalty(self.s,self.token,{**dict(stageIndex=0,clockMs=60000,penaltyMs=4000),**change})

    def test_break_requires_all_completed_official_results(self):
        self.finish(0)
        with self.assertRaisesRegex(Fault,'Break not confirmed'):updates.checkpoint(self.s,self.token,self.payload())
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM rally_checkpoints').fetchone()[0],0)
        updates.stage_result(self.s,self.token,self.record(0))
        self.assertTrue(updates.checkpoint(self.s,self.token,self.payload())['ok'])

    def test_zero_telemetry_is_unknown_not_proof_of_no_penalty(self):
        self.s.start(self.token,self.ev['id'],0,self.car,self.report)
        self.s.stage_end(self.token,self.ev['id'],0,60000,self.report,0)
        self.assertIsNone(self.s.board(self.ev['id'])['stageResults'][0]['penalty_ms'])
        updates.stage_result(self.s,self.token,self.record(0))


class PenaltyBytesTests(unittest.TestCase):
    def test_offset_packet_timer_and_invalid_values(self):
        from club_local import live_penalties
        data=bytearray(1224);struct.pack_into('<i',data,0,7)
        text='01:00.000';data[12:12+len(text)*2]=text.encode('utf-16-le')
        frame=SimpleNamespace(packet=7,clock_ms=60000)
        with self.subTest('matching graphics frame'):
            for value,expected in ((12.5,12500),(0,0),(-1,None),(float('nan'),None),(float('inf'),None),(4000,None)):
                struct.pack_into('<f',data,1220,value)
                self.assertEqual(live_penalties.penalty_from_bytes(data,frame),expected)
            struct.pack_into('<f',data,1220,12.5)
            self.assertIsNone(live_penalties.penalty_from_bytes(data,SimpleNamespace(packet=8,clock_ms=60000)))
            self.assertIsNone(live_penalties.penalty_from_bytes(data,SimpleNamespace(packet=7,clock_ms=61000)))
            self.assertIsNone(live_penalties.penalty_from_bytes(data[:268],frame))
