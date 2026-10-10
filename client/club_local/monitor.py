"""Telemetry + read-only ACR Daily Rally Weekend result monitor.

The in-game official result is the sole timing source. Live telemetry is used
only for detecting a fresh stage start, restart, quitting, and missing game.

IMPORTANT: This is an initial local test monitor. Full ACR Daily route/shortcut
Judge validation requires route data and is not claimed here.
"""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

from acr_daily import rallyweekend, rallyclub, saveslot, telemetry
from acr_daily.names import same_car
from . import integrity
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
    def __init__(self, api, event, nickname, emit, source=None, baseline=None):
        self.api = api
        self.event = event
        self.nickname = nickname
        self.emit = emit
        self.source = source if source is not None else telemetry.SharedMemory()
        self.catalog = load_catalog()
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
        self.final_timeout_started = None
        self._integrity_report = None
        self._integrity_checked_at = -1.0
        self._integrity_mismatch_since = None
        self._integrity_error_since = None
        self._integrity_last_message = None

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
        self.emit('DNF: ' + reason)
        try:
            self.api.call('/api/dnf', {'reason': reason})
        except ApiError as exc:
            self.emit('Nie udało się dostarczyć DNF; serwer zablokuje próbę po timeout: ' + str(exc))
        self.status = 'dnf'
        self.dead = True

    def _reject_integrity(self, reason):
        reason = str(reason)[:250]
        self.emit('DNF — niezgodne ustawienia Rally Weekend: ' + reason)
        try:
            self.api.call('/api/integrity-violation', {'reason':reason})
        except ApiError as exc:
            self.emit('Nie udało się przekazać DNF: '+str(exc))
        self.status = 'dnf'
        self.dead = True

    def _check_integrity(self, now, force=False):
        """Verify locally persisted rules; fail closed after confirmed differences.

        ACR may write .sav non-atomically or hold it locked during transitions.
        A single unreadable sample is not treated as deliberate cheating.
        """
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
            if self._integrity_mismatch_since is None:
                self._integrity_mismatch_since = now
            elif now - self._integrity_mismatch_since >= 1.0:
                self._reject_integrity(msg)
            return False
        except (OSError, IndexError, ValueError, TypeError) as exc:
            self._integrity_report = None
            if self._integrity_error_since is None:
                self._integrity_error_since=now
                self.emit('Nie mogę odczytać ustawień .sav; wstrzymuję start: '+str(exc))
            elif now-self._integrity_error_since>=10.0:
                self._reject_integrity('Brak możliwości weryfikacji ustawień przez ponad 10 s')
            return False
        self._integrity_report = report
        self._integrity_mismatch_since = None
        self._integrity_error_since = None
        self._integrity_last_message = None
        return True

    def _begin(self, f):
        if not self._check_integrity(time.monotonic(), force=True):
            return
        car = car_by_telemetry(f.car, self.event['allowedCars'], self.catalog)
        if not car:
            self.emit('Zły lub nierozpoznany samochód: ' + str(f.car) + ' — próba nie jest zaliczana')
            return
        if self.chosen_car and car != self.chosen_car:
            self.emit('Auto różni się od wybranego na OS1 — start odrzucony')
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
        self.chosen_car = car
        self.stage_started = time.time()
        self.highwater = f.clock_ms
        self.active_track = f.track
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
        self.emit(f'META TELEMETRYCZNA OS {index + 1}: timer {self.highwater/1000:.3f}s; wynik oficjalny odczytam po rajdzie')
        try:
            outcome = self.api.call('/api/stage-end', {'eventId':self.event['id'],
                 'stageIndex':index,'clockMs':int(self.highwater),'settings':self._integrity_report})
        except ApiError as exc:
            self._server_dnf('Serwer odrzucił zamknięcie OS-u: '+str(exc))
            return
        self.status = outcome['status']
        self.stage_index = outcome['nextStage']
        self.prev_clock = 0
        self.highwater = 0
        self.last_seen_zero = False
        self.active_track = None
        self.freeze_since = None
        self.freeze_at = None
        self.freeze_moved = False
        if self.status == 'awaiting_results':
            self.final_timeout_started = time.monotonic()
            self.emit('Wszystkie OS-y ukończone; oczekuję na pełen zapis oficjalnych czasów i kar z ACR')
        else:
            self.emit('OS potwierdzony telemetrycznie; przejdź w grze do kolejnego OS-u')

    def _finalize_if_available(self, now):
        if not self._check_integrity(now):
            return
        if now - self.last_final_try < 1.0:
            return
        self.last_final_try = now
        if self.final_timeout_started is not None and now - self.final_timeout_started > 300:
            self.emit('Nie pojawiły się wszystkie oficjalne wyniki w .sav po 5 minutach. Czekam na timeout serwera.')
            self.dead = True
            return
        try:
            content = Path(saveslot.SAVE).read_bytes()
            entries = new_results(content, self.baseline)
        except (OSError, IndexError, ValueError, TypeError):
            return
        # Preserve order and avoid confusing historical results with the new rally.
        # Match by stage ID and chosen car, never by the display name/RAW alone.
        ordered = []
        previous_started = 0
        for ix, planned in enumerate(self.event['stages']):
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
                return
            ordered.append(match)
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
        if self.status == 'awaiting_results':
            self._finalize_if_available(now)
            return
        f = self.source.read()
        unloaded = getattr(self.source, 'unloaded', False)
        if self.status == 'active':
            if now >= self.heartbeat_at:
                try:
                    self.api.call('/api/heartbeat', {'eventId': self.event['id'],
                                  'stageIndex': self.stage_index,'settings':self._integrity_report})
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
                if not self.freeze_moved and now - self.freeze_since > 15 * 60:
                    self._server_dnf('Pauza trwała ponad 15 minut')
                    return
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

    def close(self):
        if self.status == 'active':
            self._server_dnf('Zamknięto klienta podczas OS-u')
        self.source.close()
