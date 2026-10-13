"""AC Rally Club extension of ACR Daily Rally Weekend configuration.

Experimental: built against the structure described in ACR Daily's
rallyweekend.py for ACR v0.6.0.100866. Never write an unverified save;
check game is closed and retain ACR Daily's backup/replace workflow.
"""
from collections import Counter
import datetime as dt
import json
import math
import re
import struct

from . import rallyweekend as rw, saveslot
from .saveslot import SaveError


class ClubError(ValueError):
    pass


LOCATIONS = ('Alsace', 'Greece', 'MonteCarlo', 'Wales')
PREFIX = {'Alsace': ('Alsace',), 'Greece': ('Greece',),
          'MonteCarlo': ('MonteCarlo',), 'Wales': ('Weles', 'Wales')}


def location_of(stage_id):
    for loc, prefixes in PREFIX.items():
        if any(stage_id.startswith(p + 'S') for p in prefixes):
            return loc
    raise ClubError('Unsupported Rally Weekend stage id: ' + stage_id)


def parse_utc(value):
    if not isinstance(value, str):
        raise ClubError('Date must be ISO-8601 text')
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise ClubError('Invalid ISO-8601 timestamp: ' + str(value)) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ClubError('Timestamp must include a UTC offset (e.g. +00:00)')
    return parsed.astimezone(dt.timezone.utc)


def validate_event(event, cars_by_id=None):
    """Return validated event dict; explicit class and allowed car list.

    cars_by_id (optional) maps ID => {'cls': game class}, from catalog.
    """
    if not isinstance(event, dict):
        raise ClubError('Event must be a JSON object')
    if not isinstance(event.get('id'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,63}', event['id']):
        raise ClubError('id must be a slug of 3-64 lowercase letters, numbers, hyphens')
    if not isinstance(event.get('name'), str) or not 3 <= len(event['name'].strip()) <= 120:
        raise ClubError('Name length must be between 3 and 120')
    location = event.get('location')
    if location not in LOCATIONS:
        raise ClubError('Choose one ACR Rally Weekend location')
    opens, closes = parse_utc(event.get('opensAt')), parse_utc(event.get('closesAt'))
    if opens >= closes:
        raise ClubError('Closing time must be after opening time')
    if closes - opens > dt.timedelta(days=90):
        raise ClubError('Event window longer than 90 days')
    vehicle_class = event.get('carClass')
    cars = event.get('allowedCars')
    if not isinstance(vehicle_class, str) or not vehicle_class:
        raise ClubError('Car class required')
    if not isinstance(cars, list) or len(cars) != len(set(cars)) or not cars:
        raise ClubError('Select at least one distinct car')
    if cars_by_id is not None:
        for car in cars:
            if car not in cars_by_id or cars_by_id[car]['cls'] != vehicle_class:
                raise ClubError('Car does not belong to selected class: ' + str(car))
    stages = event.get('stages')
    if not isinstance(stages, list) or not 2 <= len(stages) <= 40:
        raise ClubError('Rally Weekend must contain 2-40 stages')
    for idx, stage in enumerate(stages, 1):
        if not isinstance(stage, dict):
            raise ClubError('Stage %d must be an object' % idx)
        sid = stage.get('stageId')
        if not isinstance(sid, str) or not saveslot.STAGE_RE.fullmatch(sid.encode('ascii', 'replace')):
            raise ClubError('Invalid stage ID at SS%d' % idx)
        if location_of(sid) != location:
            raise ClubError('SS%d belongs to a different Rally Weekend location' % idx)
        if stage.get('weatherGame') not in rw.WEATHERS:
            raise ClubError('Invalid weather for SS%d' % idx)
        seconds = stage.get('startSeconds')
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds < 86400:
            raise ClubError('Start time for SS%d must be 0..86399 seconds' % idx)
        if stage.get('serviceBefore', False) not in (True, False):
            raise ClubError('serviceBefore must be boolean')
    return event


def apply_club_weekend(data, event, car_id, cars_by_id=None):
    """Build complete multi-stage calendar; return new bytes, without saving.

    Does not mutate original `data`. Revalidates with rw.read_weekend().
    Writes the Rally Weekend stage calendar ONLY; leaves the game car setting
    unchanged and never requires DefaultOnlineSingleStage in the save.
    Availability of services, in-game car choice and multi-SS progression
    must be verified in ACR.
    """
    validate_event(event, cars_by_id)
    # The editor manages eligible cars in club JSON, not in the .sav.
    # When provided, car_id is checked only for consistency with club rules.
    # It is not injected into ACR; the driver must select it in the game.
    if car_id is not None and car_id not in event['allowedCars']:
        raise ClubError('Car outside the event class/list')

    try:
        current = rw.read_weekend(data)
    except SaveError as exc:
        # This exception occurs BEFORE we change the save or launch Steam.
        # Never try a guessed byte-level repair of a possibly older game layout.
        # Instead look for a backup which THIS exact upstream parser can read.
        compatible = None
        try:
            from pathlib import Path
            directory = Path(saveslot.backup_dir())
            if directory.is_dir():
                backups = sorted(directory.glob('PlayerDataSaveSlot-*.sav'), reverse=True)
                for candidate in backups[:40]:
                    if candidate.stat().st_size > 5_000_000:
                        continue
                    try:
                        rw.read_weekend(candidate.read_bytes())
                        compatible = str(candidate)
                        break
                    except (SaveError, OSError, ValueError, IndexError, struct.error):
                        continue
        except (AttributeError, OSError):
            pass
        recovery = ('Znaleziono czytelną kopię (NIE przywrócono jej automatycznie): '
                    + compatible + '. ' if compatible else 'Nie znaleziono potwierdzonej zgodnej kopii. ')
        raise SaveError('Błąd formatu ISTNIEJĄCEGO pliku .sav, przed podmianą i przed uruchomieniem gry. '
                        'Automatyczne menu nie ma z tym związku. '
                        + recovery +
                        'Zamknij ACR, zachowaj kopię obecnego .sav i przywróć POPRAWNĄ kopię zapisu '
                        'albo uruchom grę ręcznie, otwórz Rally Weekend, wyjdź z gry i sprawdź nowy zapis. '
                        'Jeśli nadal występuje: przekaż zapis .sav do analizy. '
                        'Zainstaluj aktualny launcher ACR Rally Club. Szczegóły: '+str(exc)) from exc
    if current['in_progress']:
        raise SaveError('A Rally Weekend is in progress; do not replace it.')

    stages = event['stages']
    first = stages[0]
    # Do not depend on DefaultOnlineSingleStage. This save entry is absent in
    # some ACR installs, although Rally Weekend is present and fully parsable.
    # The game selection of the car is NOT modified by the organizer editor.
    w = current
    if w['in_progress']:
        raise SaveError('Game reports Rally Weekend in progress')
    d = w['data']
    head = bytearray(data[d:d + rw.HEADER])
    rule_bytes = rw._rules(event.get('weekend'))
    for at, value in rule_bytes.items():
        head[at] = value
    struct.pack_into('<i', head, rw.OPPONENTS, 1)
    head[rw.ORDER] = 1
    struct.pack_into('<i', head, rw.START_POS, 1)

    def weather_block(stage):
        return rw._put_block(head[rw.WEATHER:rw.WEATHER + rw.BLOCK],
                             stage['weatherGame'], stage['startSeconds'])

    head[rw.WEATHER:rw.WEATHER + rw.BLOCK] = weather_block(first)
    # The original ACR Daily implementation preserves a 20-byte opaque tail,
    # replacing its first int32 with 1. We preserve the same convention, but
    # the meaning for multi-stage events is not confirmed in-game.
    tail = bytearray(data[w['tail']:w['end']])
    struct.pack_into('<i', tail, 0, 1)
    preset = rw.PRESETS.get(location_of(first['stageId']))
    if not preset:
        raise ClubError('No calendar preset for this location')
    calendar = bytearray()
    calendar += saveslot._fstring(preset)
    calendar += struct.pack('<i', len(stages))
    for idx, stage in enumerate(stages):
        blk = weather_block(stage)
        zone = 'ServiceParkDefault' if idx == 0 or stage.get('serviceBefore', False) else 'NoZone'
        # ACR Daily format: day:int32, stage:FString, two weather blocks,
        # service zone:FString. No per-stage terminator. All stages use day 0
        # until the club editor supports an explicit validated day schedule.
        calendar += struct.pack('<i', 0)
        calendar += saveslot._fstring(stage['stageId'])
        calendar += blk + blk
        calendar += saveslot._fstring(zone)
    # Exactly ONE zero terminator after the calendar, BEFORE the 20-byte tail.
    body = bytes(head[4:]) + bytes(calendar) + struct.pack('<i', 0) + bytes(tail)
    output = bytearray(data[:d]) + struct.pack('<i', len(body)) + body + data[w['end']:]
    so = saveslot._payload(data)
    struct.pack_into('<i', output, so, len(output) - so - 4)
    output = bytes(output)
    back = rw.read_weekend(output)
    if (back['in_progress'] or back['preset'] != preset or
            len(back['stages']) != len(stages) or
            back['opponents'] != 1 or back['start_position'] != 1):
        raise SaveError('Rally Weekend read-back validation failed')
    for planned, actual in zip(stages, back['stages']):
        wantzone = 'ServiceParkDefault' if (planned is stages[0] or planned.get('serviceBefore', False)) else 'NoZone'
        if (actual['stage'] != planned['stageId'] or
                actual['day'] != 0 or
                actual['weather'] != rw.WEATHERS.index(planned['weatherGame']) or
                abs(actual['start'] - planned['startSeconds']) > 0.005 or
                actual['zone'] != wantzone):
            raise SaveError('Stage read-back validation failed: ' + planned['stageId'])
    return output


def write_club_weekend(event, car_id, cars_by_id=None, *, replace_in_progress=False):
    """Write Rally Weekend calendar using ACR Daily's game-closed guard and backup.

    Does NOT configure the car; drivers select a permitted car in ACR.
    """
    validate_event(event, cars_by_id)
    if saveslot.game_running():
        raise SaveError('Close Assetto Corsa Rally before changing its save')
    if not __import__('os').path.isfile(saveslot.SAVE):
        raise SaveError('PlayerDataSaveSlot.sav not found')
    from club_local import save_layout, save_safety
    original=save_safety.preflight()
    prepared=original
    if replace_in_progress:
        try: current=rw.read_weekend(original)
        except SaveError: current=None  # apply_club_weekend retains its format recovery.
        if current and current['in_progress']:
            prepared=save_layout.park(original,rw)
    changed = apply_club_weekend(prepared, event, car_id, cars_by_id)
    save_layout.preserve_other_sections(original,changed)
    # The on-disk original is still intact here: replace() backs up the entire
    # private in-progress weekend, not just the stripped preparation buffer.
    save_safety.replace(changed,expected_source_digest=save_safety.digest(original))
    meta=save_safety.state();meta.pop('serverCopy',None);save_safety.record(meta)
    return len(event['stages'])


def result_fingerprint(e):
    """One result snapshot. Use counts, not timestamps alone; timestamps may repeat."""
    return (e['stage'].lower(), round(float(e['started']), 3),
            tuple((r['car'].lower(), round(float(r['time']), 3),
                   round(float(r['penalty']), 3)) for r in e['runs']))


def known_results(save_bytes):
    return Counter(result_fingerprint(e) for e in rw.results(save_bytes))


def official_stage_results(save_bytes, event, car_id, before):
    """Return ordered official stage records, never substitute RAW timer or guessed penalty.

    Missing stages are explicit None. Tolerates repeated stage IDs in a calendar.
    The game save's result ordering must be verified on a live multi-SS weekend.
    """
    validate_event(event)
    if car_id not in event['allowedCars']:
        raise ClubError('Car not in allowed list')
    seen = Counter()
    new_entries = []
    for e in rw.results(save_bytes):
        k = result_fingerprint(e)
        seen[k] += 1
        if seen[k] > before.get(k, 0):
            new_entries.append(e)
    ordered = []
    cursor = 0
    for st in event['stages']:
        found = None
        while cursor < len(new_entries):
            e = new_entries[cursor]
            cursor += 1
            if e['stage'].lower() != st['stageId'].lower():
                # Out-of-order results are not silently reordered.
                raise ClubError('Unexpected result order: expected %s, got %s' %
                                (st['stageId'], e['stage']))
            runs = [r for r in e['runs'] if r['car'].lower() == car_id.lower()]
            if len(runs) != 1:
                raise ClubError('Expected one player result for %s' % e['stage'])
            r = runs[0]
            found = {'stageId': st['stageId'], 'carId': car_id,
                     'timeMs': round(r['time'] * 1000),
                     'penaltyMs': round(r['penalty'] * 1000),
                     'totalMs': round((r['time'] + r['penalty']) * 1000),
                     'splits': r['splits'], 'started': e['started']}
            break
        ordered.append(found)
    return ordered


def total_result(ordered):
    """Overall is provisional until every stage has an official result."""
    complete = all(r is not None for r in ordered)
    return {'complete': complete, 'stagesCompleted': sum(r is not None for r in ordered),
            'totalMs': sum(r['totalMs'] for r in ordered if r is not None) if complete else None}
