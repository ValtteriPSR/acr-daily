"""Real byte-layout and recovery-loop checks, with synthetic saves only."""
import base64,gzip,hashlib,json,struct,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'client'),str(ROOT/'server_local'),str(ROOT/'tests')]
from club_local import save_layout as layout,save_safety as safety
from save_fixtures import make_save,string
from test_server import event
from server import Store,Fault,site
from integrity_rules import expected_settings
import attempt_updates as updates


class LayoutTests(unittest.TestCase):
    def setUp(self):self.ev=event();self.ev['stages'][1]['serviceBefore']=True
    def reader(self,raw):
        lay=layout.inspect(raw);row=next(x for x in lay['modes'] if x[0]=='DefaultRally')
        d=raw.find(string('RaceEventRaceSettingsRallyWeekendComponent'))+len(string('RaceEventRaceSettingsRallyWeekendComponent'))
        return {'data':d,'end':d+4+layout.integer(raw,d),'in_progress':layout.integer(raw,row[2])==2}
    def test_last_rally_entry_park_preserves_entire_selection_and_suffix(self):
        raw=make_save(self.ev);old=layout.inspect(raw);suffix=raw[old['selection']:]
        parked=layout.park(raw,SimpleNamespace(read_weekend=self.reader))
        new=layout.inspect(parked)
        self.assertEqual(parked[new['selection']:],suffix)
        self.assertEqual(layout.rally_report(parked)[1],0)
        self.assertFalse(self.reader(parked)['in_progress'])
        # Exact old boundary-scanner loss: delete everything up to next Default.
        at=parked.find(b'DefaultTimeAttack',new['selection'])-4
        corrupt=bytearray(parked[:new['selection']]+parked[at:]);so=layout.payload(parked)
        struct.pack_into('<i',corrupt,so,len(corrupt)-so-4)
        with self.assertRaises(layout.InvalidSave):layout.inspect(bytes(corrupt))
    def test_settings_and_progress_are_read_from_actual_bytes(self):
        raw=make_save(self.ev)
        report,done=layout.rally_report(raw)
        self.assertEqual(done,1)
        from integrity_rules import compare
        self.assertFalse(compare(self.ev,report))
    def test_change_outside_rally_and_truncation_are_rejected(self):
        raw=make_save(self.ev);bad=bytearray(raw);bad[-1]^=1
        with self.assertRaises(layout.InvalidSave):layout.preserve_other_sections(raw,bytes(bad))
        for b in [b'not a save',raw[:-1]]:
            with self.assertRaises(layout.InvalidSave):layout.inspect(b)
    def test_valid_result_map_cannot_be_mistaken_for_settings(self):
        raw=make_save(self.ev);boundary=layout.inspect(raw)['selection']
        bad=bytearray(raw[:boundary]+raw[raw.find(string('DefaultTimeAttack'),boundary):])
        so=layout.payload(raw);struct.pack_into('<i',bad,so,len(bad)-so-4)
        with self.assertRaises(layout.InvalidSave):layout.inspect(bytes(bad))


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.dir=Path(self.tmp.name);self.path=self.dir/'player.sav'
        self.raw=make_save(event(),0);self.path.write_bytes(self.raw)
        self.fake=SimpleNamespace(SAVE=str(self.path),game_running=lambda:False)
        import acr_daily
        self.patches=[mock.patch.object(acr_daily,'saveslot',self.fake,create=True),mock.patch.object(safety,'directory',return_value=self.dir)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_first_run_requires_explicit_good_confirmation(self):
        with self.assertRaises(layout.InvalidSave):safety.ensure_run_allowed()
        safety.confirm_good();safety.ensure_run_allowed()
    def test_unconfirmed_write_blocks_next_run_and_keeps_confirmed_copy(self):
        old=safety.confirm_good();candidate=bytearray(self.raw);candidate[-1]^=1
        safety.replace(bytes(candidate))
        self.assertEqual(Path(old).read_bytes(),self.raw)
        with self.assertRaises(layout.InvalidSave):safety.ensure_run_allowed()
        self.assertEqual(self.path.read_bytes(),bytes(candidate))
    def test_crash_quarantine_and_restore_do_not_clear_run_block(self):
        old=safety.confirm_good();self.path.write_bytes(b'broken');safety.report_crash()
        with self.assertRaises(layout.InvalidSave):safety.ensure_run_allowed()
        safety.restore_previous();self.assertEqual(self.path.read_bytes(),self.raw)
        with self.assertRaises(layout.InvalidSave):safety.ensure_run_allowed()
        safety.confirm_good();safety.ensure_run_allowed()
        self.assertTrue(Path(old).exists())
    def test_reported_bad_confirmed_copy_is_never_restored_again(self):
        safety.confirm_good();safety.report_crash()
        with self.assertRaises(layout.InvalidSave):safety.restore_previous()
        with self.assertRaises(layout.InvalidSave):safety.confirm_good()
    def test_invalid_candidate_or_running_game_never_changes_disk(self):
        safety.confirm_good()
        with self.assertRaises(layout.InvalidSave):safety.replace(b'broken')
        self.assertEqual(self.path.read_bytes(),self.raw)
        self.fake.game_running=lambda:True
        with self.assertRaises(layout.InvalidSave):safety.replace(self.raw)
        self.assertEqual(self.path.read_bytes(),self.raw)
    def test_bad_local_file_is_quarantined_without_overwriting_good_copy(self):
        old=safety.confirm_good();self.path.write_bytes(b'broken')
        with self.assertRaises(layout.InvalidSave):safety.preflight()
        self.assertEqual(Path(old).read_bytes(),self.raw)
        self.assertTrue(safety.state()['blocked'])
    def test_earlier_confirmed_copy_is_used_when_newest_was_reported_bad(self):
        safety.confirm_good();new=self.raw[:-1]+b'\1';self.path.write_bytes(new)
        safety.confirm_good();safety.report_crash();safety.restore_previous()
        self.assertEqual(self.path.read_bytes(),self.raw)
        with self.assertRaises(layout.InvalidSave):safety.ensure_run_allowed()
    def test_source_change_during_preparation_refuses_overwrite(self):
        safety.confirm_good()
        with self.assertRaises(layout.InvalidSave):safety.replace(self.raw,expected_source_digest='0'*64)
        self.assertEqual(self.path.read_bytes(),self.raw)
    def test_failed_atomic_install_keeps_original_and_recovery_marker(self):
        safety.confirm_good();real=safety.atomic
        def fail(path,raw):
            if Path(path)==self.path:raise OSError('Simulated interrupted save install')
            return real(path,raw)
        with mock.patch.object(safety,'atomic',side_effect=fail),self.assertRaises(OSError):safety.replace(self.raw)
        self.assertEqual(self.path.read_bytes(),self.raw)
        with self.assertRaises(layout.InvalidSave):safety.ensure_run_allowed()
    def test_oversized_input_stops_before_any_replacement(self):
        safety.confirm_good();self.path.write_bytes(b'x'*(4*1024*1024+1))
        with self.assertRaises(layout.InvalidSave):safety.preflight()
        self.assertEqual(self.path.stat().st_size,4*1024*1024+1)
        self.assertTrue(safety.state()['blocked'])


class ServerSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db')
        self.ev=event();self.ev.update(allowBreaks=True,launcherProtocol='0.2.4');self.ev['stages'][1]['serviceBefore']=True
        self.store.import_event(self.ev);self.token=self.store.join(self.ev['id'],'Synthetic driver')['token']
        self.report=expected_settings(self.ev);self.car=self.ev['allowedCars'][0]
        self.store.start(self.token,self.ev['id'],0,self.car,self.report);self.store.stage_end(self.token,self.ev['id'],0,60000,self.report)
        updates.stage_result(self.store,self.token,dict(stageIndex=0,stageId=self.ev['stages'][0]['stageId'],carId=self.car,rawMs=60000,penaltyMs=0,totalMs=60000,acrStarted=time.time(),settings=self.report))
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def payload(self,raw):return dict(stageIndex=1,save=base64.b64encode(gzip.compress(raw)).decode(),digest=hashlib.sha256(raw).hexdigest(),baseline={},settings=self.report)
    def test_malformed_replacement_preserves_prior_copy_and_attempt(self):
        good=self.payload(make_save(self.ev));updates.checkpoint(self.store,self.token,good)
        for raw in [b'broken',make_save(self.ev,0)]:
            with self.assertRaises(Fault):updates.checkpoint(self.store,self.token,self.payload(raw))
        self.assertEqual(updates.checkpoint(self.store,self.token)['digest'],good['digest'])
        self.assertEqual(self.store.state(self.token)['status'],'ready')
    def test_repeated_fetch_and_upload_of_quarantined_copy_are_blocked(self):
        good=self.payload(make_save(self.ev));updates.checkpoint(self.store,self.token,good)
        updates.save_problem(self.store,self.token,{'digest':good['digest']})
        for _ in range(2):
            with self.assertRaises(Fault):updates.checkpoint(self.store,self.token)
        with self.assertRaises(Fault):updates.checkpoint(self.store,self.token,good)
        self.assertTrue(self.store.state(self.token)['saveCopyBlocked'])
        self.assertEqual(self.store.state(self.token)['status'],'ready')
        from i18n import tr
        self.assertIn(tr('SAVE COPY BLOCKED'),site(self.store,self.ev['id']))
    def test_legacy_malformed_server_copy_is_quarantined_on_read(self):
        bad=self.payload(b'legacy broken save');p=self.store._auth(self.token)['id']
        self.store.db.execute('INSERT INTO rally_checkpoints(player_id,stage_index,payload,digest,created) VALUES(?,?,?,?,?)',(p,1,json.dumps({'save':bad['save'],'baseline':{}}),bad['digest'],time.time()))
        with self.assertRaises(Fault):updates.checkpoint(self.store,self.token)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM rally_save_problems').fetchone()[0],1)
    def test_deleting_rally_removes_quarantine_records(self):
        good=self.payload(make_save(self.ev));updates.checkpoint(self.store,self.token,good)
        updates.save_problem(self.store,self.token,{'digest':good['digest']})
        updates.purge_event_rows(self.store,self.ev['id'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM rally_save_problems').fetchone()[0],0)
