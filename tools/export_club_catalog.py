"""Copy ACR Daily's car catalog into JSON for the standalone Windows EXE."""
import json
from pathlib import Path
import re
root = Path(__file__).resolve().parent.parent
p = root / 'server' / 'src' / 'cars.js'
if not p.exists():
    raise SystemExit('Missing original ACR Daily server/src/cars.js — merge sources first')
s = p.read_text(encoding='utf-8')
pat = re.compile(r"\{\s*id:\s*'([^']+)',\s*telemetry:\s*'([^']+)',\s*name:\s*'([^']+)',\s*cls:\s*'([^']+)',\s*group:\s*'([^']+)'", re.M)
rows = [dict(id=a, telemetry=b, name=c, cls=d, group=e) for a,b,c,d,e in pat.findall(s)]
if len(rows) < 15:
    raise SystemExit(f'Catalog parse failed. Found {len(rows)} cars, expected >= 15')
out = root / 'client' / 'club_local' / 'catalog.json'
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Exported {len(rows)} cars to {out}')
