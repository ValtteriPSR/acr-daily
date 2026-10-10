"""Generate open two-stage Greece Zeli demo matching the verified ACR save."""
import datetime as dt
import json
from pathlib import Path
root = Path(__file__).resolve().parent.parent
now = dt.datetime.now(dt.timezone.utc)
data = {
    'schemaVersion':1, 'id':'grecja-zeli-local-demo', 'name':'ACR Rally Club — Grecja / test lokalny',
    'location':'Greece',
    'opensAt':(now-dt.timedelta(minutes=5)).isoformat(timespec='seconds'),
    'closesAt':(now+dt.timedelta(days=4)).isoformat(timespec='seconds'),
    'carClass':'Rally2/R5',
    'allowedCars':['VWPoloGTIR5','HyundaiI20NRally2','SkodaFabiaRSRally2'],
    'stages':[
        {'stageId':'GreeceS3ElatiaCut2Reverse','weatherGame':'WT_CLEAR','startSeconds':36000,'serviceBefore':True},
        {'stageId':'GreeceS3ElatiaCut2Forward','weatherGame':'WT_CLEAR','startSeconds':42000,'serviceBefore':False}
    ],
    'weekend':{'penalty':'light','respawn':True,'damage':True,'damageIntensity':'light','wear':'light','failures':'off'}
}
out = root / 'examples' / 'grecja-local-demo.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Zapisano:',out)
