"""Read ACR Daily's verified Rally Weekend fields from the player's own save.

No game memory injection; does not change the save. This protects against
accidental/in-game rule edits that have been persisted to .sav, not a forged
client or settings held only in the running game's RAM.
"""
from pathlib import Path
from acr_daily import rallyweekend, saveslot
from .integrity_rules import compare

class IntegrityError(ValueError):
    pass

def report_from_save(save_bytes):
    w = rallyweekend.read_weekend(save_bytes)
    return {
        'version':1,
        'rules':{key:int(w[key]) for key in ('respawn','damage','intensity','wear','failures','penalty')},
        'preset':w['preset'],'opponents':int(w['opponents']),
        'order':int(w['order']),'start_position':int(w['start_position']),
        'stages':[{key:st[key] for key in
            ('stage','weather','start','wetness','snow','accel','grip','zone')}
             for st in w['stages']],
    }

def read_and_check(event, save_path=None):
    path = Path(save_path or saveslot.SAVE)
    report = report_from_save(path.read_bytes())
    problems = compare(event,report)
    if problems:
        raise IntegrityError('; '.join(problems[:5]))
    return report
