"""Console follows authoritative server status; exit/attempt rules stay unchanged."""
import sys,unittest,json
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'client'),str(ROOT/'server_local'),str(ROOT/'tests')]
import test_monitor as fixtures
from club_local import monitor

class CommunicationTests(unittest.TestCase):
    setUp=fixtures.MonitorTests.setUp
    tearDown=fixtures.MonitorTests.tearDown
    def test_exit_before_os2_clock_preserves_existing_server_recovery_without_false_dnf(self):
        self.ev.update(launcherProtocol='0.2.4',allowBreaks=True)
        self.ev['stages'][1]['serviceBefore']=False
        self.store.db.execute('UPDATE events SET config=? WHERE id=?',(json.dumps(self.ev),self.ev['id']))
        player=self.store._auth(self.token)
        self.store.db.execute("UPDATE players SET status='ready',stage_index=1 WHERE id=?",(player['id'],))
        self.mon.event=self.ev;self.mon.status='ready';self.mon.stage_index=1
        with mock.patch.object(self.api,'call',wraps=self.api.call) as call:self.mon._exit_at_service(10)
        self.assertEqual([c.args[0] for c in call.call_args_list],['/api/integrity-violation'])
        state=self.store.state(self.token)
        self.assertEqual(state['status'],'ready');self.assertTrue(state['recoveryRequired'])
        self.assertEqual(self.mon.status,'ready');self.assertTrue(self.mon.recovery_notified)
        self.assertFalse(any('DNF' in line for line in self.log))
        self.assertTrue(any('PRZERWA · OS 2' in line and 'RUN RALLY' in line for line in self.log))
    def test_active_stage_violation_still_reports_actual_server_dnf(self):
        self.step=fixtures.MonitorTests.step.__get__(self)
        self.step(0,fixtures.frame(0));self.step(.1,fixtures.frame(500))
        self.mon._reject_integrity('Synthetic active-stage mismatch')
        self.assertEqual(self.store.state(self.token)['status'],'dnf')
        self.assertEqual(self.mon.status,'dnf')
        self.assertTrue(any(line.startswith('DNF · OS 1') for line in self.log))
