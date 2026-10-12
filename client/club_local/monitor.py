"""Telemetry + read-only ACR Daily Rally Weekend result monitor.

The in-game official result is the sole timing source. Live telemetry is used
only for detecting a fresh stage start, restart, quitting, and missing game.

IMPORTANT: This is an initial local test monitor. Full ACR Daily route/shortcut
Judge validation requires route data and is not claimed here.
"""
from __future__ import annotations
from collections import Counter
import json
import base64
import gzip
import hashlib
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

from acr_daily import rallyweekend, rallyclub, saveslot, telemetry
from acr_daily.names import same_car
from . import integrity
from . import live_penalties
from .version import VERSION as CLIENT_VERSION


def catalog_paths():
    """Find catalog.json in source or PyInstaller one-file payload."""
    import sys
    if getattr(sys, 'frozen', False):
        return [Path(sys._MEIPASS) / 'club_local' / 'catalog.json']
    return [Path(__file__).parent / 'catalog.json',
            Path(__file__).resolve().parents[2] / 'server' / 'src' / 'cars.js']


def load_catalog():
    for path in catalog_paths():
        if not path.exists():
            continue
        if path.suffix == '.json':
            rows = json.loads(path.read_text(encoding='utf-8'))
            if rows:
                return rows
        else:
            txt = path.read_text(encoding='utf-8')
            pat = re.compile(r"\{\s*id:\s*'([^']+)',\s*telemetry:\s*'([^']+)',\s*name:\s*'([^']+)',\s*cls:\s*'([^']+)',\s*group:\s*'([^']+)'", re.M)
            rows = [dict(id=a,telemetry=b,name=c,cls=d,group=e) for a,b,c,d,e in pat.findall(txt)]
            if rows:
                return rows
    raise RuntimeError('Brak katalogu aut. Uruchom tools\\export_club_catalog.py przed buildem.')


def car_by_telemetry(reported, allowed, catalog):
    valid = []
    for c in catalog:
        if c['id'] in allowed and same_car(reported, {
                'car': c['name'], 'carId': c['id'], 'carAliases': [c['telemetry']]}):
            valid.append(c['id'])
    return valid[0] if len(valid) == 1 else None


def fingerprint_key(entry):
    return json.dumps(rallyclub.result_fingerprint(entry), ensure_ascii=False, separators=(',', ':'))


def baseline_counts(save_bytes):
    return dict(Counter(fingerprint_key(e) for e in rallyweekend.results(save_bytes)))


def new_results(save_bytes, before):
    """The game retains older results. Multiset diff isolates new ones."""
    seen = Counter()
    rows = []
    for e in rallyweekend.results(save_bytes):
        key = fingerprint_key(e)
        seen[key] += 1
        if seen[key] > before.get(key, 0):
            rows.append(e)
    return rows


class ApiError(RuntimeError):
    pass


class Api:
    def __init__(self, server, token=None):
        server = server.rstrip('/')
        if not (server.startswith('http://127.0.0.1:') or
                server.startswith('http://localhost:') or server.startswith('https://') or
                server.startswith('http://192.168.') or server.startswith('http://10.') or
                server.startswith('http://172.')):
            raise ValueError('HTTP tylko localhost/LAN w zaufanej sieci; Internet wymaga HTTPS')
        self.server, self.token = server, token

    def call(self, path, payload=None):
        hdr = {'Accept':'application/json', 'X-ACR-Launcher-Version':CLIENT_VERSION}
        if self.token:
            hdr['Authorization'] = 'Bearer ' + self.token
        if payload is not None:
            hdr['Content-Type'] = 'application/json'
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(self.server + path, body, hdr,
                                     method='POST' if payload is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=4.0) as res:
                return json.loads(res.read().decode('utf-8'))
        except urllib.error.HTTPError as ex:
            try:
                reason = json.loads(ex.read().decode('utf-8')).get('error', str(ex))
            except Exception:
                reason = str(ex)
            raise ApiError(f'HTTP {ex.code}: {reason}') from ex
        except (TimeoutError, OSError, urllib.error.URLError) as ex:
            raise ApiError(f'Nie można połączyć się z {self.server}: {ex}') from ex


class AttemptMonitor:
    """Single-thread worker. Call poll() approx 5-20 times per second."""
    def __init__(self, api, event, nickname, emit, source=None, baseline=None, catalog=None):
        self.api = api
        self.event = event
        self.nickname = nickname
        self.emit = emit
        self.source = source if source is not None else live_penalties.SharedMemory()
        self.catalog = catalog if catalog is not None else load_catalog()
        if catalog is None and event.get('launcherProtocol')=='0.2.4':
            self.catalog = api.call('/api/catalog')['cars']
        self.baseline = baseline if baseline is not None else self.read_baseline()
        self.stage_index = None
        self.stage_started = None
        self.status = 'registered'
        self.chosen_car = None
        self.highwater = 0
        self.prev_clock = 0
        self.last_seen_zero = False
        self.active_track = None
        self.last_frame_at = time.monotonic()
        self.unloaded_since = None
        self.result_candidate = None
        self.candidate_since = None
        self.next_scan = 0
        self.heartbeat_at = 0
        self.failed_net = None
        self.dead = False
        self.freeze_since = None
        self.freeze_at = None
        self.freeze_moved = False
        self.last_save_poll = 0.0
        self.last_final_try = 0.0
        self.confirmed_stages = set()
        self.penalty_peak = None
        self.penalty_origin = None
        self.startline_penalty = None
        self.last_finished_telemetry = None
        self.last_penalty_report = -1.0
        self.reported_penalty = None
        self.game_seen = False
        self.next_game_check=0.0
        self.checkpoint_sent = False
        self.checkpoint_try = 0.0
        self.final_timeout_started = None
        self._integrity_report = None
        self._integrity_checked_at = -1.0
        self._integrity_mismatch_since = None
        self._integrity_error_since = None
        self._integrity_last_message = None
        self.recovery_required = False
        self.recovery_notified = False
        self.snapshot_digest = None
        self.snapshot_try = -5.0

    def read_baseline(self):
        path = Path(saveslot.SAVE)
        if not path.exists():
            raise RuntimeError('Nie znaleziono PlayerDataSaveSlot.sav')
        return baseline_counts(path.read_bytes())

    def resume(self):
        state = self.api.call('/api/me')
        self.status = state['status']
        self.stage_index = state['stage_index']
        self.chosen_car = state.get('car_id')
        self.confirmed_stages={r['stage_index'] for r in state.get('results',[])}
        if self.status=='ready' and not self.event.get('allowBreaks',True):
            self._reject_integrity('Rajd trzeba przejechać na raz; poprzednia sesja została zamknięta')
            return state
        if self.status == 'active':
            # If client was killed mid-stage, don't give a fresh legal attempt.
            # This is stricter than relying on server's heartbeat timeout alone.
            try:
                self.api.call('/api/dnf', {'reason': 'Uruchomiono ponownie klienta podczas aktywnego OS'})
            except ApiError:
                pass
            self.status = 'dnf'
            self.emit('DNF: poprzednia sesja klienta została przerwana podczas OS')
        return state

    def _server_dnf(self, reason):
        if self.status != 'active':
            return
        self.emit(f'DNF · OS {min(self.stage_index+1,len(self.event["stages"]))}: ' + reason)
        try:
            self.api.call('/api/dnf', {'reason': reason})
        except ApiError as exc:
            self.emit('Nie udało się dostarczyć DNF; serwer zablokuje próbę po timeout: ' + str(exc))
        self.status = 'dnf'
        self.dead = True

    def _reject_integrity(self, reason):
        reason = str(reason)[:250]
        self.emit(f'DNF · OS {min(self.stage_index+1,len(self.event["stages"]))} — niezgodne ustawienia Rally Weekend: ' + reason)
        try:
            self.api.call('/api/integrity-violation', {'reason':reason})
        except ApiError as exc:
            self.emit('Nie udało się przekazać DNF: '+str(exc))
        self.status = 'dnf'
        self.dead = True

    def _request_recovery(self,reason):
        self.recovery_required=True
        if not self.recovery_notified:
            self.emit('OSTRZEŻENIE: niezgodna konfiguracja Rally Weekend lub samochód. Podejście zachowane; czasy nie będą wysyłane. Zamknij grę ORAZ program EXE launchera przed ponownym RUN na stronie. Jeśli EXE pozostanie otwarty, RUN poprosi o potwierdzenie restartu launchera. '+str(reason))
        try:
            self.api.call('/api/integrity-violation',{'reason':str(reason)[:250]})
            self.recovery_notified=True
        except ApiError as exc:
            self.emit('OSTRZEŻENIE: nie potwierdzono blokady na stronie; pozostaw launcher otwarty do odzyskania połączenia: '+str(exc))

    def _capture_recovery_copy(self,now):
        if self.recovery_required or not self.event.get('allowBreaks',True) or self.status!='ready' or not 0<self.stage_index<len(self.event['stages']) or now-self.snapshot_try<5.0:
            return
        if any(idx not in self.confirmed_stages for idx in range(self.stage_index)):
            return
        try:
            raw=Path(saveslot.SAVE).read_bytes()
            from .integrity_rules import compare
            report=integrity.report_from_save(raw)
            if compare(self.event,report): return
            progress=rallyweekend.progress(raw)
            if self.stage_index and (not progress or progress.get('done')!=self.stage_index): return
            digest=hashlib.sha256(raw).hexdigest()
            if digest==self.snapshot_digest: return
            self.snapshot_try=now
            self.api.call('/api/recovery-checkpoint',{'save':base64.b64encode(gzip.compress(raw)).decode('ascii'),
                'digest':digest,'baseline':self.baseline,'stageIndex':self.stage_index,'settings':report})
            self.snapshot_digest=digest
            self.emit(f'KOPIA CLUB: poprawny zapis przed OS {self.stage_index+1} potwierdzony na serwerze.')
        except (ApiError,OSError,ValueError,IndexError,TypeError) as exc:
            self.emit('Kopia poprawnego zapisu będzie ponowiona: '+str(exc))

    def _check_integrity(self, now, force=False):
        """Verify locally persisted rules; fail closed after confirmed differences.

        ACR may write .sav non-atomically or hold it locked during transitions.
        A single unreadable sample is not treated as deliberate cheating.
        """
        if self.recovery_required:
            if not self.recovery_notified and now-self._integrity_checked_at>=3.0:
                self._integrity_checked_at=now
                self._request_recovery(self._integrity_last_message or 'Nieprawidłowe ustawienia')
            return False
        if not force and now-self._integrity_checked_at < 1.0:
            return self._integrity_report is not None
        self._integrity_checked_at = now
        try:
            report = integrity.read_and_check(self.event)
        except integrity.IntegrityError as exc:
            self._integrity_report = None
            msg=str(exc)
            if msg!=self._integrity_last_message:
                self.emit('NIEZGODNOŚĆ ustawień .sav: '+msg)
                self._integrity_last_message=msg
            if self.status=='registered' or (self.status=='ready' and self.event.get('allowBreaks',True)):
                self._request_recovery(msg)
                return False
            if self._integrity_mismatch_since is None:
                self._integrity_mismatch_since = now
            elif now - self._integrity_mismatch_since >= 1.0:
                if self.status=='registered' or (self.status=='ready' and self.event.get('allowBreaks',True)):
                    self._request_recovery(msg)
                else: self._reject_integrity(msg)
            return False
        except (OSError, IndexError, ValueError, TypeError) as exc:
            self._integrity_report = None
            if self._integrity_error_since is None:
                self._integrity_error_since=now
                self.emit('Nie mogę odczytać ustawień .sav; wstrzymuję start: '+str(exc))
            elif now-self._integrity_error_since>=10.0:
                if self.status=='registered' or (self.status=='ready' and self.event.get('allowBreaks',True)):
                    self._request_recovery('Brak możliwości weryfikacji ustawień przez ponad 10 s')
                else: self._reject_integrity('Brak możliwości weryfikacji ustawień przez ponad 10 s')
            return False
        self._integrity_report = report
        self._integrity_mismatch_since = None
        self._integrity_error_since = None
        self._integrity_last_message = None
        return True

    def _begin(self, f):
        if not self._check_integrity(time.monotonic(), force=True):
            return
        self.emit('TELEMETRIA: nazwa samochodu = '+str(f.car))
        car = car_by_telemetry(f.car, self.event['allowedCars'], self.catalog)
        if not car:
            if self.status=='registered' or self.event.get('allowBreaks',True):
                self._request_recovery('Samochód '+str(f.car)+' nie należy do listy dozwolonej klasy; przejazd nie został rozpoczęty na serwerze.')
            else: self.emit('OSTRZEŻENIE: wybierz samochód dozwolonej klasy. W trybie jazdy na raz nie zamykaj gry ani launchera.')
            return
        if self.chosen_car and car != self.chosen_car:
            if self.event.get('allowBreaks',True): self._request_recovery('Samochód różni się od wybranego na OS1; RUN przywróci właściwy zapis.')
            else: self.emit('OSTRZEŻENIE: przywróć samochód z OS1 bez zamykania gry ani launchera w trybie jazdy na raz.')
            return
        stage = self.event['stages'][self.stage_index]
        # The official stage ID cannot be extracted from Shared Memory on all ACR stages.
        # We validate it against the game's save when the result appears.
        try:
            self.api.call('/api/start', {'eventId': self.event['id'],
                     'stageIndex': self.stage_index,'carId':car,'settings':self._integrity_report})
        except ApiError as exc:
            self.dead = True
            self.emit('Serwer zablokował start: ' + str(exc))
            return
        self.status = 'active'
        self.penalty_peak = None
        value=getattr(f,'penalty_ms',None)
        self.penalty_origin=self.startline_penalty if self.startline_penalty is not None else (value if type(value) is int and 0<=value<=3600000 else None)
        self.startline_penalty=None
        self.last_finished_telemetry = None
        self.reported_penalty = None
        self.chosen_car = car
        self.stage_started = time.time()
        self.highwater = f.clock_ms
        self.active_track = f.track
        self._observe_live_penalty(f,time.monotonic())
        self.last_frame_at = time.monotonic()
        self.emit(f'START OS {self.stage_index+1}: {stage["stageId"]} | {car} | pierwsza próba zajęta na serwerze')

    def _has_official_stage_result(self, now):
        # Fallback for a very quick transition to the menu after the finish.
        if now < self.next_scan:
            return False
        self.next_scan = now + 0.75
        try:
            entries = new_results(Path(saveslot.SAVE).read_bytes(), self.baseline)
        except (OSError, ValueError, IndexError, TypeError):
            return False
        expected = self.event['stages'][self.stage_index]['stageId']
        return any(e['stage'].casefold() == expected.casefold() and
                   any(r['car'].casefold() == self.chosen_car.casefold() for r in e['runs'])
                   for e in entries)

    def _stage_end(self):
        if not self._check_integrity(time.monotonic(), force=True):
            return
        index = self.stage_index
        self.emit(f'META TELEMETRYCZNA OS {index + 1}: timer {self.highwater/1000:.3f}s; wysyłam czas i odczytane kary na serwer')
        try:
            outcome = self.api.call('/api/stage-end', {'eventId':self.event['id'],
                 'stageIndex':index,'clockMs':int(self.highwater),'settings':self._integrity_report,
                 'penaltyMs':self.penalty_peak})
        except ApiError as exc:
            self._server_dnf('Serwer odrzucił zamknięcie OS-u: '+str(exc))
            return
        self.status = outcome['status']
        if self.penalty_peak:
            self.emit(f'OS {index+1}: serwer zapisał karę telemetryczną +{self.penalty_peak/1000:.3f}s; oczekuję na oficjalny zapis gry')
        else:
            self.emit(f'OS {index+1}: brak dodatniej kary w telemetrii nie potwierdza zera kar; oczekuję na oficjalny zapis gry')
        self.last_finished_telemetry = (index,int(self.highwater),self.active_track,self.chosen_car)
        self.reported_penalty = self.penalty_peak
        self.stage_index = outcome['nextStage']
        self.prev_clock = 0
        self.highwater = 0
        self.last_seen_zero = False
        self.active_track = None
        self.checkpoint_sent = False
        self.snapshot_digest=None
        self.snapshot_try=-5.0
        self.freeze_since = None
        self.freeze_at = None
        self.freeze_moved = False
        if self.status == 'awaiting_results':
            self.final_timeout_started = time.monotonic()
            self.emit('Wszystkie OS-y ukończone; oczekuję na pełen zapis oficjalnych czasów i kar z ACR')
        else:
            self.emit('OS potwierdzony telemetrycznie; przejdź w grze do kolejnego OS-u')
        # Do not wait for the next poll/next stage to submit a save already available.
        self.last_final_try = -1.0
        self._finalize_if_available(time.monotonic())

    def _observe_live_penalty(self, frame, now):
        if frame is None: return
        value=getattr(frame,'penalty_ms',None)
        if type(value) is not int or not 0<=value<=3600000: return
        if self.status in ('registered','ready') and frame.clock_ms==0:
            self.startline_penalty=value
            return
        if self.status=='active':
            if frame.track!=self.active_track or not car_by_telemetry(frame.car,[self.chosen_car],self.catalog): return
            if self.penalty_origin is None:
                self.penalty_origin=value
                return
            if value<self.penalty_origin: self.penalty_origin=0
            value=max(0,value-self.penalty_origin)
            if value>(self.penalty_peak or 0):
                self.heartbeat_at=0
                self.emit(f'TELEMETRIA OS {self.stage_index+1}: kara +{value/1000:.3f}s')
            self.penalty_peak=max(value,self.penalty_peak or 0)
            return
        if not self.last_finished_telemetry or self.status not in ('ready','awaiting_results'): return
        idx,clock,track,car=self.last_finished_telemetry
        if frame.clock_ms!=clock or frame.track!=track or not car_by_telemetry(frame.car,[car],self.catalog): return
        if self.penalty_origin is None: return
        value=max(0,value-self.penalty_origin)
        if value<= (self.reported_penalty or 0) or now-self.last_penalty_report<0.5: return
        self.last_penalty_report=now
        try:
            self.api.call('/api/telemetry-penalty',{'stageIndex':idx,'clockMs':clock,'penaltyMs':value})
            self.reported_penalty=value
        except ApiError as exc:
            self.emit('Nie potwierdzono kary z telemetrii: '+str(exc))

    def _finalize_if_available(self, now):
        if not self._check_integrity(now):
            return
        if now - self.last_final_try < 0.25:
            return
        self.last_final_try = now
        if self.final_timeout_started is not None and now - self.final_timeout_started > 300:
            self.emit('Nie pojawiły się wszystkie oficjalne wyniki w .sav po 5 minutach. Czekam na timeout serwera.')
            self.dead = True
            return
        try:
            content = Path(saveslot.SAVE).read_bytes()
            from .integrity_rules import compare
            report=integrity.report_from_save(content)
            if compare(self.event,report):
                if self.status=='registered' or (self.status=='ready' and self.event.get('allowBreaks',True)):
                    self._request_recovery('Zapis wyników ma inne ustawienia niż rajd')
                else: self._reject_integrity('Zapis wyników ma inne ustawienia niż rajd')
                return
            self._integrity_report=report
            entries = new_results(content, self.baseline)
        except (OSError, IndexError, ValueError, TypeError):
            return
        # Preserve order and avoid confusing historical results with the new rally.
        # Match by stage ID and chosen car, never by the display name/RAW alone.
        ordered = []
        previous_started = 0
        for ix, planned in enumerate(self.event['stages'][:self.stage_index]):
            match = None
            for entry in entries:
                if entry['started'] <= previous_started or \
                        entry['stage'].casefold() != planned['stageId'].casefold():
                    continue
                runs = [r for r in entry['runs'] if r['car'].casefold() == self.chosen_car.casefold()]
                if len(runs) != 1:
                    continue
                r = runs[0]
                match = {'stageIndex':ix, 'stageId':planned['stageId'], 'carId':self.chosen_car,
                         'rawMs':round(r['time']*1000), 'penaltyMs':round(r['penalty']*1000),
                         'totalMs':round((r['time']+r['penalty'])*1000), 'acrStarted':entry['started']}
                previous_started = entry['started']
                break
            if match is None:
                break
            ordered.append(match)
        for record in ordered:
            if record['stageIndex'] in self.confirmed_stages: continue
            try:
                self.api.call('/api/stage-result',{**record,'settings':self._integrity_report})
                self.confirmed_stages.add(record['stageIndex'])
                self.emit(f'OS {record["stageIndex"]+1}: wynik z karami potwierdzony na stronie')
            except ApiError as exc:
                self.emit('Potwierdzenie OS-u będzie ponowione: '+str(exc))
                return
        self._capture_recovery_copy(now)
        if self.status!='awaiting_results' or len(ordered)!=len(self.event['stages']): return
        try:
            answer = self.api.call('/api/finalize', {'stages':ordered,'settings':self._integrity_report})
        except ApiError as exc:
            self.emit('Serwer nie zatwierdził kompletu wyników: '+str(exc))
            self.dead = True
            return
        self.status = answer['status']
        self.dead = True
        total = sum(x['totalMs'] for x in ordered)
        penalties = sum(x['penaltyMs'] for x in ordered)
        for rec in ordered:
            self.emit(f'OFICJALNY OS {rec["stageIndex"]+1}: {rec["totalMs"]/1000:.3f}s (kara +{rec["penaltyMs"]/1000:.3f}s)')
        self.emit(f'WYNIK WYSŁANY: łącznie {total/1000:.3f}s, kary {penalties/1000:.3f}s')

    def poll(self):
        if self.dead or self.status in ('completed', 'dnf'):
            return
        now = time.monotonic()
        if not self._check_integrity(now):
            return
        f = self.source.read()
        self._observe_live_penalty(f,now)
        if self.stage_index and self.status!='active':
            self._finalize_if_available(now)
        elif self.status=='registered':
            self._capture_recovery_copy(now)
        if self.status == 'awaiting_results' or self.dead:
            return
        if os.name=='nt' and now>=self.next_game_check:
            self.next_game_check=now+0.75
            running=saveslot.game_running()
            self.game_seen=self.game_seen or running
            if self.game_seen and not running and self.status=='ready':
                self._exit_at_service(now)
                return
        unloaded = getattr(self.source, 'unloaded', False)
        if self.status == 'active':
            if now >= self.heartbeat_at:
                try:
                    self.api.call('/api/heartbeat', {'eventId': self.event['id'],
                                  'stageIndex': self.stage_index,'settings':self._integrity_report,
                                  'penaltyMs':self.penalty_peak})
                    self.failed_net = None
                except ApiError as exc:
                    if self.failed_net is None:
                        self.failed_net = now
                        self.emit('Brak łączności podczas OS — wymagane odzyskanie połączenia: ' + str(exc))
                    if now - self.failed_net > 30:
                        self._server_dnf('Brak połączenia z serwerem >30 s')
                        return
                self.heartbeat_at = now + 3.0
            if f is None:
                if self._has_official_stage_result(now):
                    self._stage_end()
                    return
                if unloaded:
                    if self.unloaded_since is None:
                        self.unloaded_since = now
                    if now - self.unloaded_since >= 8:
                        self._server_dnf('Wyjście z OS-u do menu przed oficjalnym wynikiem')
                elif now - self.last_frame_at > 30:
                    self._server_dnf('Utrata gry lub telemetrii podczas OS-u >30 s')
                return
            self.unloaded_since = None
            self.last_frame_at = now
            if f.clock_ms < self.highwater - 500:
                self._server_dnf('Restart OS-u — cofnięcie timera')
                return
            if self.active_track and f.track and f.track != self.active_track:
                self._server_dnf('Zmiana OS-u zanim zapisano oficjalny wynik')
                return
            if self.chosen_car and not car_by_telemetry(f.car, [self.chosen_car], self.catalog):
                self._server_dnf('Zmiana samochodu w trakcie OS-u')
                return
            if f.clock_ms > self.highwater:
                self.freeze_since = None
                self.freeze_at = None
                self.freeze_moved = False
            elif f.clock_ms == self.highwater and self.highwater > 10000:
                if self.freeze_since is None:
                    self.freeze_since = now
                    self.freeze_at = (f.x, f.z)
                if self.freeze_at is not None:
                    moved = ((self.freeze_at[0] - f.x)**2 + (self.freeze_at[1] - f.z)**2)**0.5
                    if moved > 2.0:
                        self.freeze_moved = True
                if self.freeze_moved and now - self.freeze_since > 1.25:
                    self._stage_end()
                    return
            self.highwater = max(self.highwater, f.clock_ms)
            return
        # Not running: only new clock starts from zero count.
        if f is None:
            self.prev_clock = 0
            self.last_seen_zero = False
            return
        if f.clock_ms <= 0:
            self.last_seen_zero = True
        elif self.last_seen_zero and self.prev_clock <= 0:
            self.last_seen_zero = False
            self._begin(f)
        self.prev_clock = f.clock_ms

    def _exit_at_service(self, now):
        next_stage=self.event['stages'][self.stage_index]
        if self.event.get('launcherProtocol')!='0.2.4' and self.event.get('allowBreaks',True) and not next_stage.get('serviceBefore',False):
            return  # Existing legacy local continuation outside service stays unchanged.
        if not self.event.get('allowBreaks',True) or not next_stage.get('serviceBefore',False):
            self._reject_integrity('Wyjście z gry poza dozwolonym serwisem; rajd musi być kontynuowany bez zamykania gry')
            return
        if self.checkpoint_sent or now-self.checkpoint_try<3.0: return
        self.checkpoint_try=now
        if any(idx not in self.confirmed_stages for idx in range(self.stage_index)):
            self.emit('PRZERWA NIEZATWIERDZONA: czekam na oficjalne czasy i kary ukończonych OS-ów. Nie zamykaj launchera. Pozwól grze zapisać wyniki na ekranie wyników lub na serwisie przed wyjściem.')
            return
        try:
            raw=Path(saveslot.SAVE).read_bytes()
            from .integrity_rules import compare
            report=integrity.report_from_save(raw)
            if compare(self.event,report): raise ValueError('Ustawienia zapisu różnią się od rajdu')
            progress=rallyweekend.progress(raw)
            if not progress or progress.get('done')!=self.stage_index:
                raise ValueError('Gra nie zapisała jeszcze postępu przed kolejnym OS-em')
            if len(raw)>4*1024*1024: raise ValueError('Plik zapisu przekracza limit 4 MB')
            self.api.call('/api/checkpoint',{'save':base64.b64encode(gzip.compress(raw)).decode('ascii'),
                'digest':hashlib.sha256(raw).hexdigest(),'baseline':self.baseline,
                'stageIndex':self.stage_index,'settings':report})
            self.checkpoint_sent=True
            self.dead=True  # The Club session is parked; do not monitor a later private rally.
            self.emit('PRZERWA: kopia zapisu przesłana na serwer. Możesz zamknąć launcher. Wznów przez RUN na stronie.')
        except (ApiError,OSError,ValueError) as exc:
            self.emit('Nie zapisano kopii na serwerze; nie zamykaj launchera, ponawiam: '+str(exc))

    def close(self):
        if self.recovery_required:
            self.source.close()
            return
        if self.status == 'active':
            self._server_dnf('Zamknięto klienta podczas OS-u')
        elif self.status=='ready':
            if not self.event.get('allowBreaks',True):
                self._reject_integrity('Zamknięto launcher w rajdzie wymagającym jazdy na raz')
            elif os.name=='nt' and not saveslot.game_running() and not self.checkpoint_sent:
                self._exit_at_service(time.monotonic())
        self.source.close()
