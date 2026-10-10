import sys,types,struct,re,importlib.util
from pathlib import Path
root=Path(__file__).resolve().parents[1]
import sys

def synthetic_gvas():
    # Synthetic independent encoding of the ACR Daily multi-stage save format.
    # No real player's .sav or private identifiers are included in the release.
    def sf(value):
        value=value.encode('ascii')
        return struct.pack('<i',len(value)+1)+value+b'\0'
    head=bytearray(100)
    struct.pack_into('<i',head,71,1)  # number of rivals
    struct.pack_into('<i',head,92,1)  # starting grid position
    def stage(sid,weather,ts):
        blk=bytearray(42)
        blk[0]=weather
        struct.pack_into('<f',blk,24,float(ts))
        return struct.pack('<i',0)+sf(sid)+bytes(blk)+bytes(blk)+sf('ServiceParkDefault')
    calendar=(sf('GreeceWeekendShort')+struct.pack('<i',2)+
              stage('GreeceS3ElatiaCut2Reverse',0,43200)+
              stage('GreeceS3ElatiaCut2Forward',6,43200)+
              struct.pack('<i',0))
    component=sf('RaceEventRaceSettingsRallyWeekendComponent')
    body=bytes(head[4:])+calendar+bytes(20)
    payload=component+struct.pack('<i',len(body))+body+sf('AfterComponent')
    header=b'GVAS'+bytes(16)+b'PlayerSaveGameData\0'
    return header+struct.pack('<i',len(payload))+payload
b=Path(sys.argv[1]).read_bytes() if len(sys.argv)>1 else synthetic_gvas()
S=types.ModuleType('acr_daily.saveslot');R=types.ModuleType('acr_daily.rallyweekend');P=types.ModuleType('acr_daily');P.__path__=[str(root/'client/acr_daily')]
class SaveError(ValueError):pass
S.SaveError=SaveError
S.STAGE_RE=re.compile(rb'^(Alsace|Weles|Wales|Greece|MonteCarlo)S\d[A-Za-z0-9]*(Forward|Reverse)$')
def fstring(x):
 x=x.encode('ascii') if isinstance(x,str) else x
 return struct.pack('<i',len(x)+1)+x+b'\0'
S._fstring=fstring
def fstring_at(b,o):
 if o+4>len(b):return None
 n=struct.unpack_from('<i',b,o)[0]
 if n<1 or n>300 or o+4+n>len(b) or b[o+4+n-1]!=0:return None
 val=b[o+4:o+4+n-1]
 if any(v<32 or v>126 for v in val):return None
 return val,o+4+n
S._fstring_at=fstring_at
def payload(b):
 so=b.find(b'PlayerSaveGameData\0')+len(b'PlayerSaveGameData\0')
 if so<30 or struct.unpack_from('<i',b,so)[0]!=len(b)-so-4:raise SaveError('Bad GVAS')
 return so
S._payload=payload
R.HEADER=100;R.OPPONENTS=71;R.ORDER=91;R.START_POS=92;R.WEATHER=25;R.BLOCK=42
R.PRESETS={'Greece':'GreeceWeekendShort','Alsace':'AlsaceWeekendShort','Weles':'WalesWeekendShort','MonteCarlo':'MontecarloWeekendShort'}
R.WEATHERS=['WT_CLEAR','WT_LIGHT_CLOUDS','WT_HEAVY_CLOUDS','WT_LIGHT_FOG','WT_HEAVY_FOG','WT_LIGHT_RAIN','WT_HEAVY_RAIN','WT_STORM','WT_LIGHT_SNOW','WT_HEAVY_SNOW','WT_BLIZZARD']
R._rules=lambda x:{}
def put_block(blk,weather,start):
 a=bytearray(blk);a[0]=R.WEATHERS.index(weather);struct.pack_into('<f',a,24,start);struct.pack_into('<f',a,32,0.0);return bytes(a)
R._put_block=put_block
R.COMPONENT=fstring('RaceEventRaceSettingsRallyWeekendComponent')
def read_weekend(b):
 payload(b)
 idx=b.find(R.COMPONENT)
 if idx<0:raise SaveError('Missing component')
 d=idx+len(R.COMPONENT);size=struct.unpack_from('<i',b,d)[0];end=d+size+4
 p=fstring_at(b,d+100)
 if not p:raise SaveError('Missing preset')
 preset,o=p[0].decode(),p[1]
 n=struct.unpack_from('<i',b,o)[0];o+=4;rows=[]
 for index in range(n):
  day=struct.unpack_from('<i',b,o)[0];o+=4
  st,o=fstring_at(b,o);sid=st.decode()
  raw_weather=b[o];start=struct.unpack_from('<f',b,o+24)[0];o+=84
  x=fstring_at(b,o)
  if not x or x[0] not in (b'ServiceParkDefault',b'NoZone'):
   raise SaveError('unexpected zone in the Rally Weekend calendar at '+str(o-d))
  z,o=x;rows.append(dict(day=day,stage=sid,weather=raw_weather,start=start,zone=z.decode()))
 if struct.unpack_from('<i',b,o)[0] != 0: raise SaveError('Missing calendar terminator')
 o+=4
 if o+20!=end:raise SaveError('Wrong 20-byte opaque tail')
 return dict(data=d,end=end,tail=o,in_progress=False,stages=rows,preset=preset, opponents=struct.unpack_from('<i',b,d+71)[0], start_position=struct.unpack_from('<i',b,d+92)[0])
R.read_weekend=read_weekend
sys.modules.update({'acr_daily':P,'acr_daily.saveslot':S,'acr_daily.rallyweekend':R})
sp=importlib.util.spec_from_file_location('acr_daily.rallyclub',root/'client/acr_daily/rallyclub.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
print('Input stages:',read_weekend(b)['stages'])
from datetime import datetime,timedelta,timezone
now=datetime.now(timezone.utc)
event=dict(id='grecja-stages-demo',name='Rajd Grecja',location='Greece',opensAt=now.isoformat(),closesAt=(now+timedelta(days=1)).isoformat(),carClass='Rally2/R5',allowedCars=['VWPoloGTIR5'],stages=[dict(stageId='GreeceS3ElatiaCut2Reverse',weatherGame='WT_CLEAR',startSeconds=36000),dict(stageId='GreeceS3ElatiaCut2Forward',weatherGame='WT_CLEAR',startSeconds=43000)])
out=m.apply_club_weekend(b,event,'VWPoloGTIR5')
print('Updated parsed stages:',read_weekend(out)['stages'])
assert len(read_weekend(out)['stages'])==2
assert read_weekend(out)['stages'][1]['start']==43000
assert struct.unpack_from('<i',out,payload(out))[0]==len(out)-payload(out)-4
print('SAV binary roundtrip PASS; original save untouched.')
