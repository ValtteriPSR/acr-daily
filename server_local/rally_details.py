"""Compact public rally configuration, derived from the launcher's actual settings."""
from html import escape

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
    names = {stage['id']: stage['name'] for stage in load_catalog()['stages']}
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


def rally_conditions(event):
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
    ]
    return ('<section class="card rally-conditions"><span class="section-kicker">Rally Weekend</span><h2>'
            + escape(tr('Conditions')) + '</h2><dl class="conditions-grid">'
            + ''.join('<div><dt>' + escape(tr(label)) + '</dt><dd>' + escape(value) + '</dd></div>'
                      for label, value in fields) + '</dl></section>')
