"""Shared protocol for per-stage Rally Weekend integrity checks.

Only interprets a narrow, documented subset of the ACR Daily save format.
The server validates structured declarations from the client, NOT the player's
actual local .sav. A modified client can forge these declarations.
"""
import math

LEVELS = {'off': 0, 'light': 1, 'severe': 2, 'realistic': 3}
PENALTIES = {'light': 1, 'realistic': 2}
WEATHERS = ['WT_CLEAR', 'WT_LIGHT_CLOUDS', 'WT_HEAVY_CLOUDS',
            'WT_LIGHT_FOG', 'WT_HEAVY_FOG', 'WT_LIGHT_RAIN',
            'WT_HEAVY_RAIN', 'WT_STORM', 'WT_LIGHT_SNOW',
            'WT_HEAVY_SNOW', 'WT_BLIZZARD']
WETNESS = {'WT_LIGHT_RAIN': .2, 'WT_HEAVY_RAIN': .25, 'WT_STORM': .25}
DEFAULT_RULES = {'penalty':'light', 'respawn':True, 'damage':True,
                 'damageIntensity':'light','wear':'light','failures':'off'}
PRESETS = {'Alsace':'AlsaceWeekendShort','Greece':'GreeceWeekendShort',
           'MonteCarlo':'MontecarloWeekendShort','Wales':'WalesWeekendShort'}


def expected_settings(event):
    r = dict(DEFAULT_RULES)
    r.update(event.get('weekend') or {})
    rules = {
        'respawn': int(bool(r['respawn'])),
        'damage': int(bool(r['damage'])),
        'intensity': LEVELS[r['damageIntensity']],
        'wear': LEVELS[r['wear']],
        'failures': LEVELS[r['failures']],
        'penalty': PENALTIES[r['penalty']],
    }
    stages=[]
    for idx, st in enumerate(event['stages']):
        weather=st['weatherGame']
        stages.append({
            'stage':st['stageId'], 'weather':WEATHERS.index(weather),
            'start':float(st['startSeconds']),
            'wetness':WETNESS.get(weather,0.0),
            'snow':0.0, 'accel':0, 'grip':4,
            'zone':'ServiceParkDefault' if idx == 0 or st.get('serviceBefore',False) else 'NoZone',
        })
    return {'version':1, 'rules':rules,'preset':PRESETS[event['location']],
            'opponents':1,'order':1,'start_position':1, 'stages':stages}


def compare(event, reported):
    """Return differences. Any incomplete/malformed report is a mismatch.

    In particular a client MUST NOT send a raw save hash as evidence: ACR
    naturally updates results, weather rolls and Rally Weekend progress.
    """
    exp = expected_settings(event)
    if not isinstance(reported,dict) or type(reported.get('version')) is not int or reported['version'] != 1:
        return ['Brak/nieobsługiwana wersja kontroli integralności']
    problems=[]
    rules=reported.get('rules')
    if not isinstance(rules,dict):
        return ['Brak ustawień Rally Weekend w raporcie']
    translated={
        'damage':'Uszkodzenia', 'intensity':'Intensywność uszkodzeń',
        'wear':'Zużycie', 'failures':'Awarie mechaniczne',
        'penalty':'Tryb kar', 'respawn':'Przywracanie samochodu',
    }
    for key,value in exp['rules'].items():
        if type(rules.get(key)) is not int or rules[key]!=value:
            problems.append(f'{translated[key]}: oczekiwano {value}, otrzymano {rules.get(key)}')
    for key,label in (('preset','Lokalizacja'),('opponents','Liczba przeciwników'),
                      ('order','Kolejność startowa'),('start_position','Pozycja startowa')):
        if reported.get(key)!=exp[key] or (key!='preset' and type(reported.get(key)) is not int):
            problems.append(f'{label}: oczekiwano {exp[key]}, otrzymano {reported.get(key)}')
    stages=reported.get('stages')
    if not isinstance(stages,list) or len(stages)!=len(exp['stages']):
        problems.append('Liczba odcinków lub kalendarz Rally Weekend została zmieniona')
        return problems
    for ix,(expected,actual) in enumerate(zip(exp['stages'],stages),1):
        if not isinstance(actual,dict):
            problems.append(f'OS {ix}: brak ustawień'); continue
        for key in ('stage','weather','zone','accel','grip'):
            if actual.get(key)!=expected[key]:
                problems.append(f'OS {ix}: zmieniono {key}')
        for key in ('start','wetness','snow'):
            value=actual.get(key)
            if type(value) not in (int,float) or not math.isfinite(value) or abs(value-expected[key])>.05:
                problems.append(f'OS {ix}: zmieniono {key}')
    return problems
