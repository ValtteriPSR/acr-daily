"""Telemetry resource cleanup and launch dialog regressions."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'client'),str(ROOT/'server_local')]
from club_local.read_only_memory import Block, Source
from club_local.trace_sender import TraceSender


class MemoryTests(unittest.TestCase):
    def test_read_only_flags_and_idempotent_close(self):
        kernel=mock.Mock()
        kernel.OpenFileMappingW.return_value=123
        kernel.MapViewOfFile.return_value=456
        block=Block('test',200,kernel)
        kernel.OpenFileMappingW.assert_called_once_with(4,False,'Local\\test')
        kernel.MapViewOfFile.assert_called_once_with(123,4,0,0,200)
        block.close();block.close()
        kernel.UnmapViewOfFile.assert_called_once_with(456)
        kernel.CloseHandle.assert_called_once_with(123)
        with self.assertRaises(OSError):block.read()

    def test_failed_map_releases_handle(self):
        kernel=mock.Mock()
        kernel.OpenFileMappingW.return_value=123
        kernel.MapViewOfFile.return_value=0
        with self.assertRaises(OSError):Block('test',200,kernel)
        kernel.CloseHandle.assert_called_once_with(123)
        kernel.UnmapViewOfFile.assert_not_called()

    def test_thousand_partial_open_failures_release_every_view(self):
        for failure in (1,2):
            opened=[]
            def factory(name,size):
                if name==('acpmf_physics' if failure==1 else 'acpmf_static'):
                    raise OSError('missing block')
                block=mock.Mock();opened.append(block);return block
            source=Source(factory)
            for i in range(1000):self.assertFalse(source._open(float(i)))
            self.assertIsNone(source.blocks)
            for block in opened:block.close.assert_called_once()
            self.assertEqual(len(opened),1000*failure)

    def test_penalty_mapping_retries_are_throttled_without_losing_frames(self):
        from club_local import live_penalties
        wrapper=live_penalties.SharedMemory.__new__(live_penalties.SharedMemory)
        frame=SimpleNamespace(penalty_ms=None)
        wrapper.source=mock.Mock();wrapper.source.read.return_value=frame
        wrapper.penalty_block=None;wrapper.next_penalty_open=0
        with mock.patch.object(live_penalties,'Block',side_effect=OSError('unsupported')) as block:
            with mock.patch.object(live_penalties.time,'monotonic',return_value=10):
                for _ in range(100):self.assertIs(wrapper.read(),frame)
            self.assertEqual(block.call_count,1)
            with mock.patch.object(live_penalties.time,'monotonic',return_value=16):wrapper.read()
            self.assertEqual(block.call_count,2)
        wrapper.close()

    def test_offline_trace_retains_only_ninety_samples_during_long_drive(self):
        def offline(*args):raise RuntimeError('offline')
        api=SimpleNamespace(call=offline)
        sender=TraceSender(api,'event',lambda value:None);sender.started=True
        import tracemalloc
        tracemalloc.start()
        try:
            for i in range(20000):
                frame=SimpleNamespace(clock_ms=i*1000,x=i*10.,z=0.,speed=36.)
                sender.observe(0,frame,float(i))
                if i%3==0:sender.send_once()
            current,_=tracemalloc.get_traced_memory()
            self.assertLessEqual(len(sender.buffer),90)
            self.assertLessEqual(len(sender.pending['points']),12)
            self.assertLess(current,1024*1024)
        finally:tracemalloc.stop();sender.close()


class DialogTests(unittest.TestCase):
    def test_dialog_stays_in_page_and_uses_csrf_form_body(self):
        from run_dialog import section
        html,script=section()
        self.assertIn('<dialog',html)
        self.assertIn('new FormData(form)',script)
        self.assertIn("credentials:'same-origin'",script)
        self.assertIn('event.preventDefault()',script)
        self.assertNotIn('window.location',script)
        self.assertIn('open.removeAttribute',script)
