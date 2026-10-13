"""Synthetic saves only; no user-provided files or personal data in tests."""
import struct
import json

def string(value):
    value=value.encode();return struct.pack('<i',len(value)+1)+value+b'\0'

def make_save(event,done=1):
    header=bytearray(100)
    rules=event.get('weekend',{})
    levels={'off':0,'light':1,'severe':2,'realistic':3}
    for at,value in [(9,int(rules.get('respawn',True))),(14,int(rules.get('damage',True))),(22,levels[rules.get('damageIntensity','light')]),(23,levels[rules.get('wear','light')]),(24,levels[rules.get('failures','off')]),(90,1 if rules.get('penalty','light')=='light' else 2),(91,1)]:header[at]=value
    struct.pack_into('<i',header,71,1);struct.pack_into('<i',header,92,1)
    weathers=['WT_CLEAR','WT_LIGHT_CLOUDS','WT_HEAVY_CLOUDS','WT_LIGHT_FOG','WT_HEAVY_FOG','WT_LIGHT_RAIN','WT_HEAVY_RAIN','WT_STORM','WT_LIGHT_SNOW','WT_HEAVY_SNOW','WT_BLIZZARD']
    def weather(st):
        b=bytearray(42);b[0]=weathers.index(st['weatherGame']);struct.pack_into('<f',b,24,st['startSeconds']);b[41]=4
        struct.pack_into('<f',b,32,{'WT_LIGHT_RAIN':.2,'WT_HEAVY_RAIN':.25,'WT_STORM':.25}.get(st['weatherGame'],0));return bytes(b)
    header[25:67]=weather(event['stages'][0])
    calendar=string({'Greece':'GreeceWeekendShort','Wales':'WalesWeekendShort','Alsace':'AlsaceWeekendShort','MonteCarlo':'MontecarloWeekendShort'}[event['location']])+struct.pack('<i',len(event['stages']))
    for idx,st in enumerate(event['stages']):calendar+=struct.pack('<i',0)+string(st['stageId'])+weather(st)*2+string('ServiceParkDefault' if idx==0 or st.get('serviceBefore') else 'NoZone')
    body=bytes(header[4:])+calendar+struct.pack('<i',0)+bytes(20)
    component=string('RaceEventRaceSettingsRallyWeekendComponent')+struct.pack('<i',len(body))+body
    settings=string('ERaceEventSerializableContext::RaceEventSettings')+struct.pack('<ii',0,1)+component
    state=string('ERaceEventSerializableContext::RaceEventState')+struct.pack('<ii',0,1)+string('RaceEventRallyWeekendDataComponent')+struct.pack('<ii',4,done)
    modes=struct.pack('<i',1)+string('DefaultRally')+struct.pack('<i',2 if done else 1)+settings+(state if done else b'')
    selection=string(event['stages'][0]['stageId'])+string(event['allowedCars'][0])+struct.pack('<i',0)
    # A synthetic retained suffix containing a later Default key exercises the
    # legacy scanner bug without importing the affected user's data.
    suffix=bytes(4)+string('DefaultTimeAttack')+struct.pack('<ii',0,0)+bytes(32)
    payload=b'SYNTHETIC-PREFERENCES'+bytes(32)+modes+selection+suffix
    prefix=b'GVAS'+bytes(16)+b'PlayerSaveGameData\0'
    return prefix+struct.pack('<i',len(payload))+payload
