"""Wyniki ACR w formacie arkuszy dla projectsimracing.pl/wyniki.html.

Strona ligi czyta wyniki z Apps Script jako {title, updated, sheets:[{name,
headers, rows}]} i sama rozpoznaje kolumny po nagłówkach (Kierowca, Czas,
Punkty, Samochód, Zespół, Dywizja). Ten moduł podaje dokładnie ten format,
więc na stronie wystarczy wpisać adres w assets/js/zrodla.js → sources.acr:

    https://ADRES-SERWERA-ACR/api/ps/wyniki

Parametry: ?season=<id> (domyślnie najnowszy sezon z rajdami), ?meta=1
(tylko {title, updated} — strona pyta tak co minutę i pobiera całość tylko
po zmianie). Odczyt jest publiczny i tylko do odczytu; dane to te same
wyniki, które widać na /season/<id>.
"""
import hashlib
import json
import os

from public_security import PUBLIC_URL

DEFAULT_ORIGINS = 'https://projectsimracing.pl,https://www.projectsimracing.pl'
LOCAL_ORIGINS = ('http://localhost:8000', 'http://127.0.0.1:8000')


def allowed_origins():
    raw = os.environ.get('ACR_CORS_ORIGINS', DEFAULT_ORIGINS)
    origins = {o.strip().rstrip('/') for o in raw.split(',') if o.strip()}
    if not PUBLIC_URL:
        origins.update(LOCAL_ORIGINS)  # podgląd strony ligi: buduj.py --serwuj
    return origins


def cors_headers(origin):
    if origin and origin in allowed_origins():
        return {'Access-Control-Allow-Origin': origin, 'Vary': 'Origin'}
    return {'Vary': 'Origin'}


def _fmt(ms):
    ms = int(ms or 0)
    hours, rest = divmod(ms, 3600000)
    minutes, rest = divmod(rest, 60000)
    sec, millis = divmod(rest, 1000)
    return (f'{hours}:{minutes:02d}' if hours else f'{minutes:02d}') + f':{sec:02d}.{millis:03d}'


def pick_season(store, season_id=None):
    from seasons import list_seasons
    seasons = list_seasons(store)
    if season_id:
        return season_id if any(s['id'] == season_id for s in seasons) else None
    with_rallies = [s for s in seasons if s['rallyCount']]
    chosen = (with_rallies or seasons or [None])[0]
    return chosen['id'] if chosen else None


def sheets(store, season_id=None):
    from seasons import scoring
    from rally_details import car_label
    ident = pick_season(store, season_id)
    if ident is None:
        return {'title': 'Assetto Corsa Rally', 'updated': '0', 'sheets': []}
    data = scoring(store, ident)
    season = data['season']
    divisions = {d['id']: d['name'] for d in season['divisions']}
    teams = {t['id']: t['name'] for t in season['teams']}
    team_of = {d['memberId']: teams.get(d['teamId'], '') for d in data['drivers']}

    general = {'name': 'Klasyfikacja generalna',
               'headers': ['Poz', 'Kierowca', 'Zespół', 'Dywizja', 'Rajdy', 'Gen.', 'Dyw.', 'PS', 'Punkty'],
               'rows': [[str(n), d['nickname'], team_of.get(d['memberId'], ''), divisions.get(d['divisionId'], ''),
                         str(d['finishes']), str(d['general']), str(d['division']), str(d['powerStage']), str(d['total'])]
                        for n, d in enumerate(data['drivers'], 1)]}
    out = [general]
    if data['teams']:
        roster = {}
        for d in data['drivers']:
            roster.setdefault(d['teamId'], []).append(d['nickname'])
        out.append({'name': 'Klasyfikacja zespołów', 'headers': ['Poz', 'Zespół', 'Kierowcy', 'Punkty'],
                    'rows': [[str(n), t['name'], ' · '.join(roster.get(t['id'], [])), str(t['points'])]
                             for n, t in enumerate(data['teams'], 1)]})
    with store.lock:
        cars = {(r['event_id'], r['club_member_id']): r['car_id'] for r in store.db.execute(
            'SELECT event_id,club_member_id,car_id FROM players WHERE club_member_id IS NOT NULL')}
    for n, rally in enumerate(data['rallies'], 1):
        rows = []
        for e in rally['results']:
            points = e['pointsGeneral'] + e['pointsDivision'] + e['pointsPowerStage']
            # Rajd jeszcze trwa: czasy są, punkty dopiero po zamknięciu.
            pts = (lambda v: str(v)) if rally['closed'] else (lambda v: '')
            rows.append([str(e['rankGeneral']), e['nickname'], car_label(cars.get((rally['id'], e['memberId']))),
                         team_of.get(e['memberId'], ''), divisions.get(e['divisionId'], ''),
                         pts(e['pointsGeneral']), pts(e['pointsDivision']), pts(e['pointsPowerStage']),
                         _fmt(e['totalMs']), pts(points)])
        out.append({'name': f'{n}. {rally["name"]}',
                    'headers': ['Poz', 'Kierowca', 'Samochód', 'Zespół', 'Dywizja', 'Gen.', 'Dyw.', 'PS', 'Czas', 'Punkty'],
                    'rows': rows})
    digest = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return {'title': season['name'], 'updated': digest, 'sheets': out}


def events(store):
    """Lista rajdów dla kalendarza strony ligi (narzedzia/buduj.py)."""
    from rally_details import location_label
    from seasons import list_seasons, season_config
    position = {}
    for s in list_seasons(store):
        for n, ev in enumerate(season_config(store, s['id'])['events'], 1):
            position[ev['id']] = (s['name'], n)
    rallies = []
    for ev in sorted(store.listing(), key=lambda e: e['opensAt']):
        season, n = position.get(ev['id'], ('', None))
        rallies.append({'id': ev['id'], 'name': ev['name'], 'round': n, 'season': season,
                        'location': location_label(ev['location']), 'opensAt': ev['opensAt'],
                        'closesAt': ev['closesAt'], 'stages': len(ev['stages']), 'carClass': ev['carClass'],
                        'resultsTab': f'{n}. {ev["name"]}' if n else '', 'path': '/rally/' + ev['id']})
    return {'events': rallies}
