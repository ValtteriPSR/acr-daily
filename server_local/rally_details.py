"""Compact public rally configuration, derived from the launcher's actual settings."""
from html import escape
import json

from admin_panel import load_catalog
from i18n import tr
from integrity_rules import DEFAULT_RULES, expected_settings


WEATHER_LABELS = {
    'WT_CLEAR': 'Clear', 'WT_LIGHT_CLOUDS': 'Light clouds',
    'WT_HEAVY_CLOUDS': 'Heavy clouds', 'WT_LIGHT_FOG': 'Light fog',
    'WT_HEAVY_FOG': 'Heavy fog', 'WT_LIGHT_RAIN': 'Light rain',
    'WT_HEAVY_RAIN': 'Heavy rain', 'WT_STORM': 'Storm',
    'WT_LIGHT_SNOW': 'Light snow', 'WT_HEAVY_SNOW': 'Heavy snow',
    'WT_BLIZZARD': 'Blizzard',
}
LEVEL_LABELS = {'off': 'Off', 'light': 'Light', 'severe': 'Severe', 'realistic': 'Realistic'}


def stage_schedule(event):
    from club_settings import branding
    names = {stage['id']: stage['name'] for stage in (branding().get('catalog') or load_catalog())['stages']}
    settings = expected_settings(event)
    rows = []
    for index, (stage, actual) in enumerate(zip(event['stages'], settings['stages']), 1):
        seconds = int(actual['start'])
        clock = f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}'
        if seconds % 60:
            clock += f':{seconds % 60:02d}'
        weather = escape(tr(WEATHER_LABELS.get(stage['weatherGame'], stage['weatherGame'])))
        if actual['wetness']:
            weather += '<small>' + escape(tr('Road wetness')) + ': ' + f"{actual['wetness']:.0%}" + '</small>'
        service = tr('Yes') if actual['zone'] == 'ServiceParkDefault' else '—'
        rows.append('<tr><td><span class="stage-number">' + escape(tr('SS')) + ' ' + str(index)
                    + '</span><strong>' + escape(names.get(stage['stageId'], stage['stageId']))
                    + '</strong></td><td>' + weather + '</td><td class="mono">' + clock
                    + '</td><td class="service-cell">' + escape(service) + '</td></tr>')
    return ('<h3>' + escape(tr('Special stages')) + ' · ' + str(len(rows)) + '</h3>'
            '<div class="table-scroll stage-schedule" tabindex="0" role="region" aria-label="'
            + escape(tr('Stage schedule'), quote=True) + '"><table><thead><tr><th>'
            + escape(tr('Route')) + '</th><th>' + escape(tr('Weather')) + '</th><th>'
            + escape(tr('In-game time')) + '</th><th>' + escape(tr('Service before'))
            + '</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')


def rally_conditions(event, store=None):
    rules = {**DEFAULT_RULES, **(event.get('weekend') or {})}
    actual = expected_settings(event)
    level = lambda key: tr(LEVEL_LABELS[rules[key]])
    fields = [
        ('Damage', level('damageIntensity') if rules['damage'] else tr('Off')),
        ('Wear', level('wear')), ('Mechanical failures', level('failures')),
        ('Penalty mode', level('penalty')),
        ('Car respawn', tr('Allowed') if rules['respawn'] else tr('Disabled')),
        ('Starting position', str(actual['start_position'])),
        ('Road grip', tr('Optimal')),
        ('Road wetness', tr('By stage weather')),
        ('Starting snow cover', f"{actual['stages'][0]['snow']:.0%}"),
        ('Time progression', tr('Fixed')),
        ('Breaks', (tr('Exiting the game at service or before SS start is allowed') if event.get('allowBreaks',True) else tr('One sitting; do not close the game')) if event.get('launcherProtocol')=='0.2.4' else tr('At service: server backup with launcher 0.2.6; otherwise unchanged local save')),
    ]
    return ('<section class="card rally-conditions"><span class="section-kicker">Rally Weekend</span><h2>'
            + escape(tr('Conditions')) + '</h2><dl class="conditions-grid">'
            + ''.join('<div><dt>' + escape(tr(label)) + '</dt><dd>' + escape(value) + '</dd></div>'
                      for label, value in fields) + '</dl>'
            + (season_rules(store, event['id']) if store is not None else '') + '</section>')


# ---- Czytelne nazwy zamiast identyfikatorów gry (strony publiczne) ----
LOCATION_LABELS = {'Greece': 'Greece', 'Alsace': 'Alsace', 'Wales': 'Wales', 'MonteCarlo': 'Monte Carlo'}


def _catalog():
    from club_settings import branding
    try:
        return branding().get('catalog') or load_catalog()
    except (ValueError, OSError):
        return {'cars': [], 'stages': []}


def car_label(car_id):
    """'HyundaiI20NRally2' -> 'Hyundai i20 N Rally2' (gdy auto jest w katalogu)."""
    if not car_id:
        return '—'
    return next((c['name'] for c in _catalog().get('cars', []) if c.get('id') == car_id), car_id)


def stage_label(stage_id):
    return next((s['name'] for s in _catalog().get('stages', []) if s.get('id') == stage_id), stage_id)


def location_label(location):
    return tr(LOCATION_LABELS.get(location, location))


def season_rules(store, event_id):
    """Public scoring metadata only; use round overrides exactly as scoring() does."""
    with store.lock:
        row = store.db.execute("""SELECT s.id,s.name,s.team_mode,
            s.general_points AS season_general,s.division_points AS season_division,
            s.power_points AS season_power,se.general_points AS rally_general,
            se.division_points AS rally_division,se.power_points AS rally_power,
            (SELECT COUNT(*) FROM season_teams t WHERE t.season_id=s.id) AS team_count
            FROM season_events se JOIN seasons s ON s.id=se.season_id
            WHERE se.event_id=?""", (event_id,)).fetchone()
        if row is None:
            return ''
        divisions = [d['name'] for d in store.db.execute(
            'SELECT name FROM season_divisions WHERE season_id=? ORDER BY sort_index', (row['id'],))]
        # Empty Power Stage overrides disable the bonus; never fall back via truthiness.
        points = {kind: json.loads(row['rally_' + kind] if row['rally_' + kind] is not None
                                  else row['season_' + kind])
                  for kind in ('general', 'division', 'power')}
    def text(value):
        return escape(tr(value))
    def scale(values):
        return ', '.join(str(value) for value in values)
    from urllib.parse import quote
    lines = [('<strong>' + text('Season') + ':</strong> <a href="/season/'
              + quote(row['id'], safe='') + '">' + escape(row['name']) + '</a>'),
             '<strong>' + text('Overall points') + ':</strong> '
             + text('Positions from 1:') + ' ' + scale(points['general']) + '. '
             + text('Other classified finishers: 1 point.')]
    if divisions:
        lines.append('<strong>' + text('Division points') + ':</strong> '
                     + text('Positions from 1:') + ' ' + scale(points['division']) + '. '
                     + text('Other classified finishers: 1 point.'))
    power = (text('Final SS, among rally finishers:') + ' ' + scale(points['power']) + '. '
             + text('Other places: 0 points.')) if any(points['power']) else text('Disabled')
    lines += ['<strong>Power Stage:</strong> ' + power,
              '<strong>' + text('Who scores') + ':</strong> '
              + text('Season entrants with a club account who finish every SS. DNF: 0 points. Points are awarded after the rally closes.')]
    mode = {'combined': 'Overall + division + Power Stage',
            'general': 'Overall + Power Stage', 'division': 'Division points only'}[row['team_mode']]
    team = text('Sum of points from all assigned team drivers:') + ' ' + text(mode) + '.'
    if not row['team_count']:
        team = text('No teams configured.') + ' ' + team
    lines.append('<strong>' + text('Team scoring') + ':</strong> ' + team)
    lines.append('<strong>' + text('Divisions') + ':</strong> '
                 + (', '.join(escape(name) for name in divisions) if divisions else text('Not configured')))
    return '<div class="season-rules" aria-label="' + text('Season scoring rules') + '">' + ''.join(
        '<p>' + line + '</p>' for line in lines) + '</div>'
