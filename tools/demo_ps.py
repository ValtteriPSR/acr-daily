"""Lokalne dane pokazowe dla podglądu strony (NIGDY na serwerze produkcyjnym).

Tworzy osobną bazę SQLite z sezonem, dywizjami, zespołami, dwoma zakończonymi
rajdami z wynikami, jednym trwającym i jednym zapowiedzianym. Kierowcy i czasy
są zmyśleni. Uruchomienie:

    python tools/demo_ps.py                 # tworzy server_local/demo.sqlite3
    python tools/demo_ps.py --db inna.db    # inna ścieżka

Potem serwer z tą bazą:  python server_local/server.py --db server_local/demo.sqlite3
"""
from __future__ import annotations
import argparse
import json
import random
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'server_local'))

from server import Store  # noqa: E402
from integrity_rules import expected_settings  # noqa: E402
from seasons import (steam_finish, club_join, save_season, add_group, assign_member,  # noqa: E402
                     set_rallies, mint_club_ticket, season_config)
from steam_auth import digest  # noqa: E402
from web_launcher import redeem_ticket  # noqa: E402
import club_settings  # noqa: E402
import timing_guard  # noqa: E402

DRIVERS = [
    ('Kamyk_PL', 'PSR1', 'Szuter Team'), ('Wiraż', 'PSR1', 'Szuter Team'),
    ('BłotnyBartek', 'PSR1', 'Hopa Racing'), ('Mgła77', 'PSR1', 'Hopa Racing'),
    ('Ostry_Nawrot', 'PSR2', 'Kontra Rally'), ('Hamulec_Ręczny', 'PSR2', 'Kontra Rally'),
    ('Pilot_Zośka', 'PSR2', None), ('Koleina', 'PSR2', 'Hopa Racing'),
    ('Nowy_Na_OS', 'Rookie', None), ('Rookie_Rysiek', 'Rookie', 'Szuter Team'),
    ('Ślizg', 'Rookie', 'Kontra Rally'), ('Długa_Prosta', 'Rookie', None),
]
CARS = ['SkodaFabiaRSRally2', 'HyundaiI20NRally2', 'VWPoloGTIR5']
WEEKEND = {'penalty': 'light', 'respawn': True, 'damage': True,
           'damageIntensity': 'light', 'wear': 'light', 'failures': 'off'}


def iso(dt):
    return dt.isoformat(timespec='seconds')


def rally(ident, name, location, stages, opens, closes, weathers=None):
    weathers = weathers or ['WT_CLEAR'] * len(stages)
    return {'schemaVersion': 1, 'launcherProtocol': '0.2.4', 'allowBreaks': True,
            'id': ident, 'name': name, 'location': location,
            'opensAt': iso(opens), 'closesAt': iso(closes),
            'carClass': 'Rally2/R5', 'allowedCars': CARS, 'weekend': WEEKEND,
            'stages': [{'stageId': s, 'weatherGame': w, 'startSeconds': 32400 + 2700 * i,
                        'serviceBefore': i in (0, 2)} for i, (s, w) in enumerate(zip(stages, weathers))]}


def member(store, nick):
    pending = secrets.token_urlsafe(32)
    steam_id = str(76561198000000000 + secrets.randbelow(999999999))
    store.db.execute('INSERT INTO steam_pending_sessions(session_hash,steam_id,expires) VALUES(?,?,?)',
                     (digest(pending), steam_id, time.time() + 60))
    return steam_finish(store, pending, nick)['memberId']


def drive(store, ev, member_id, skill, rng, stages_to_drive=None, dnf_at=None):
    club_join(store, ev['id'], member_id)
    launch = redeem_ticket(store, mint_club_ticket(store, ev['id'], member_id))
    token, player_id = launch['token'], launch['playerId']
    settings = expected_settings(ev)
    car = rng.choice(CARS)
    rows = []
    count = len(ev['stages']) if stages_to_drive is None else stages_to_drive
    for i in range(count):
        store.start(token, ev['id'], i, car, settings)
        if dnf_at == i:
            store.dnf(token, 'Uszkodzone zawieszenie — wycofanie na OS %d' % (i + 1))
            return
        base = [312000, 268000, 401000, 233000, 355000, 290000][i % 6]
        raw = int(base * skill * rng.uniform(.985, 1.03))
        pen = rng.choice([0, 0, 0, 0, 5000, 10000])
        # Demo „przejeżdża” OS natychmiast — cofamy serwerowy START o czas przejazdu,
        # żeby kontrola zegara (timing_guard) widziała realistyczny przebieg.
        timing_guard.record_start(store, player_id, i, time.time() - raw / 1000 - 4)
        store.stage_end(token, ev['id'], i, raw, settings, pen or None)
        rows.append({'stageIndex': i, 'stageId': ev['stages'][i]['stageId'], 'carId': car,
                     'rawMs': raw, 'penaltyMs': pen, 'totalMs': raw + pen,
                     'acrStarted': time.time() - 30 + i})
    if count == len(ev['stages']):
        store.finalize(token, {'stages': rows, 'settings': settings})


def shift(store, ev, opens, closes):
    ev = dict(ev, opensAt=iso(opens), closesAt=iso(closes))
    store.db.execute('UPDATE events SET config=?,opens=?,closes=? WHERE id=?',
                     (json.dumps(ev, ensure_ascii=False), opens.timestamp(), closes.timestamp(), ev['id']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=str(ROOT / 'server_local' / 'demo.sqlite3'))
    args = ap.parse_args()
    db = Path(args.db)
    for suffix in ('', '-wal', '-shm'):
        Path(str(db) + suffix).unlink(missing_ok=True)
    store = Store(db)
    rng = random.Random(15)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    club_settings.write(store, 'branding', {
        'title': 'ACR RALLY', 'subtitle': 'Project Simracing · Sezon 1',
        'tagline': 'Rajdy Assetto Corsa Rally z pomiarem czasu przez launcher.',
        'discordInvite': 'https://discord.gg/R3Tu68jWwK', 'logo': ''})

    season = save_season(store, {'name': 'Assetto Corsa Rally · Sezon 1',
                                 'opensAt': iso(now - timedelta(days=40)),
                                 'closesAt': iso(now + timedelta(days=90))})['id']
    divisions = {d: add_group(store, season, 'division', d)['id'] for d in ('PSR1', 'PSR2', 'Rookie')}
    teams = {t: add_group(store, season, 'team', t, 4)['id'] for t in ('Szuter Team', 'Hopa Racing', 'Kontra Rally')}

    soon = now + timedelta(minutes=1)
    events = [
        rally('acr-s1-r1-grecja', 'Rajd Grecji', 'Greece',
              ['GreeceS3ElatiaCut2Reverse', 'GreeceS3ElatiaCut2Forward', 'GreeceS4LoutrakiCut1Forward', 'GreeceS4LoutrakiCut2Reverse'],
              now - timedelta(hours=1), soon + timedelta(days=1)),
        rally('acr-s1-r2-alzacja', 'Rajd Alzacji', 'Alsace',
              ['AlsaceS2MunsterShort1Forward', 'AlsaceS2MunsterShort2Reverse', 'AlsaceS4SaverneShort1Forward', 'AlsaceS2MunsterFullForward'],
              now - timedelta(hours=1), soon + timedelta(days=1), ['WT_LIGHT_CLOUDS', 'WT_LIGHT_RAIN', 'WT_LIGHT_RAIN', 'WT_HEAVY_CLOUDS']),
        rally('acr-s1-r3-walia', 'Rajd Walii', 'Wales',
              ['WelesS3HafrenNorthCut1Forward', 'WelesS3HafrenNorthCut2Reverse', 'WelesS4HafrenSouthFullForward'],
              now - timedelta(hours=1), now + timedelta(days=5), ['WT_LIGHT_FOG', 'WT_HEAVY_CLOUDS', 'WT_LIGHT_RAIN']),
        rally('acr-s1-r4-monte-carlo', 'Rajd Monte Carlo', 'MonteCarlo',
              ['MonteCarloS1BolleneCut1Forward', 'MonteCarloS1BolleneCut2Forward', 'MonteCarloS2SisteronCut1Forward', 'MonteCarloS1BolleneFullReverse'],
              now + timedelta(days=12), now + timedelta(days=19), ['WT_CLEAR', 'WT_LIGHT_SNOW', 'WT_CLEAR', 'WT_HEAVY_SNOW']),
    ]
    for ev in events:
        store.import_event(ev)
    set_rallies(store, season, [ev['id'] for ev in events])

    ids = {}
    for nick, div, team in DRIVERS:
        ids[nick] = member(store, nick)
        assign_member(store, season, ids[nick], divisions[div], teams.get(team))

    skill = {nick: 1 + i * .012 for i, (nick, _, _) in enumerate(DRIVERS)}
    for r, ev in enumerate(events[:2]):
        for nick, _, _ in DRIVERS:
            dnf = 2 if (r, nick) in {(0, 'Mgła77'), (1, 'Ślizg')} else None
            drive(store, ev, ids[nick], skill[nick] * rng.uniform(.99, 1.01), rng, dnf_at=dnf)
    # Trwający rajd: część skończyła, część w trakcie, część tylko zapisana
    for k, (nick, _, _) in enumerate(DRIVERS):
        if k < 5:
            drive(store, events[2], ids[nick], skill[nick], rng)
        elif k < 8:
            drive(store, events[2], ids[nick], skill[nick], rng, stages_to_drive=k - 4)
        elif k < 10:
            club_join(store, events[2]['id'], ids[nick])
    for nick in ('Kamyk_PL', 'Wiraż', 'Pilot_Zośka'):
        club_join(store, events[3]['id'], ids[nick])

    # Zakończone rajdy przenosimy w przeszłość (zamknięte = punkty naliczone).
    shift(store, events[0], now - timedelta(days=30), now - timedelta(days=23))
    shift(store, events[1], now - timedelta(days=16), now - timedelta(days=9))
    store.db.execute('UPDATE players SET last_seen=? WHERE status IN (\'active\',\'ready\')', (time.time(),))
    print('Gotowe:', db)
    print('Sezon:', season, '·', len(season_config(store, season)['events']), 'rajdy')
    store.db.close()


if __name__ == '__main__':
    main()
