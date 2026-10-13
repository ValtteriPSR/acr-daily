"""Bounded read of GVAS settings-map and selection; no guessed Default scan."""
import struct
import re

class InvalidSave(ValueError):pass

def integer(raw,at):
    if not 0<=at<=len(raw)-4:raise InvalidSave('Truncated integer')
    return struct.unpack_from('<i',raw,at)[0]

def text(raw,at,empty=False):
    n=integer(raw,at)
    if not 1<=n<=1024 or at+4+n>len(raw) or raw[at+3+n]!=0:raise InvalidSave('Invalid string length')
    value=raw[at+4:at+3+n]
    if (not value and not empty) or any(x<32 or x>126 for x in value):raise InvalidSave('Invalid string')
    return value.decode('ascii'),at+4+n

def payload(raw):
    if not isinstance(raw,bytes) or not 100<len(raw)<=4*1024*1024 or raw[:4]!=b'GVAS':raise InvalidSave('Invalid GVAS file')
    name=b'PlayerSaveGameData\0';at=raw.find(name)
    if at<0 or raw.find(name,at+1)>=0:raise InvalidSave('Missing or repeated game data')
    at+=len(name)
    if integer(raw,at)!=len(raw)-at-4:raise InvalidSave('Wrong game-data length')
    return at

def walk(raw,at,count):
    rows=[]
    for _ in range(count):
        begin=at;name,at=text(raw,at)
        if not re.fullmatch(r'Default[A-Za-z]+',name):raise InvalidSave('Invalid mode name')
        value=at;contexts=integer(raw,at);at+=4
        if not 0<=contexts<=8:raise InvalidSave('Invalid context count')
        for _ in range(contexts):
            context,at=text(raw,at)
            if not context.startswith('ERaceEventSerializableContext::'):raise InvalidSave('Unknown context')
            versions=integer(raw,at);at+=4
            if not 0<=versions<=32:raise InvalidSave('Invalid version count')
            at+=20*versions;parts=integer(raw,at);at+=4
            if not 0<=parts<=32:raise InvalidSave('Invalid component count')
            for _ in range(parts):
                component,at=text(raw,at)
                if not component.startswith('RaceEvent'):raise InvalidSave('Unknown component')
                size=integer(raw,at);at+=4
                if not 0<=size<=len(raw)-at:raise InvalidSave('Invalid component length')
                at+=size
        rows.append((name,begin,value,at))
    if len({r[0] for r in rows})!=len(rows):raise InvalidSave('Repeated mode')
    return rows

def inspect(raw):
    size_at=payload(raw);candidate=raw.find(b'Default',size_at+4)
    while candidate>=0:
        start=candidate-4
        try:
            count=integer(raw,start-4)
            if not 1<=count<=32:raise InvalidSave('Mode count')
            rows=walk(raw,start,count);at=rows[-1][3]
            stage,at=text(raw,at);car,at=text(raw,at)
            if not re.fullmatch(r'[A-Za-z0-9_]+(?:Forward|Reverse)',stage) or not re.fullmatch(r'[A-Za-z0-9_]+',car):raise InvalidSave('Missing stage/car selection')
            options=integer(raw,at);at+=4
            if not 0<=options<=16:raise InvalidSave('Invalid weather-option count')
            for _ in range(options):_,at=text(raw,at);_,at=text(raw,at)
            if len(raw)-at<32:raise InvalidSave('Truncated following data')
            return {'modes':rows,'selection':rows[-1][3],'selectionEnd':at,'sizeAt':size_at}
        except InvalidSave:pass
        candidate=raw.find(b'Default',candidate+1)
    raise InvalidSave('Nieprawidłowa struktura zapisu: sekcje ustawień lub wybór auta/odcinka. RUN został wstrzymany.')

def preserve_other_sections(before,after):
    a,b=inspect(before),inspect(after)
    old=[x for x in a['modes'] if x[0]=='DefaultRally'];new=[x for x in b['modes'] if x[0]=='DefaultRally']
    if len(old)!=1 or len(new)!=1:raise InvalidSave('Missing Rally Weekend')
    x,y=old[0],new[0];so=a['sizeAt']
    if b['sizeAt']!=so or before[:so]!=after[:so] or before[so+4:x[1]]!=after[so+4:y[1]] or before[x[3]:]!=after[y[3]:]:
        raise InvalidSave('Podmiana zmieniłaby dane poza Rally Weekend. Plik nie został zapisany.')

def park(raw,rw):
    layout=inspect(raw);w=rw.read_weekend(raw)
    if not w['in_progress']:return raw
    row=next((x for x in layout['modes'] if x[0]=='DefaultRally'),None)
    if row is None or integer(raw,row[2])!=2 or not row[2]<w['data']<w['end']<row[3]:raise InvalidSave('Unknown Rally state layout')
    start,end=row[2],row[3]
    out=bytearray(raw[:start]+struct.pack('<i',1)+raw[start+4:w['end']]+raw[end:])
    so=layout['sizeAt'];struct.pack_into('<i',out,so,len(out)-so-4);out=bytes(out)
    preserve_other_sections(raw,out)
    if rw.read_weekend(out)['in_progress']:raise InvalidSave('State removal failed')
    return out

def rally_report(raw):
    layout=inspect(raw);row=next((x for x in layout['modes'] if x[0]=='DefaultRally'),None)
    if row is None:raise InvalidSave('No Rally Weekend')
    needle=struct.pack('<i',43)+b'RaceEventRaceSettingsRallyWeekendComponent\0'
    i=raw.find(needle,row[2],row[3])
    if i<0:raise InvalidSave('No Rally Weekend component')
    d=i+len(needle);end=d+4+integer(raw,d)
    if end>row[3] or end-d<124:raise InvalidSave('Invalid Rally Weekend length')
    def weather(at):
        if at+42>end:raise InvalidSave('Truncated weather')
        import math
        values=struct.unpack_from('<ffff',raw,at+24)
        start,_,wet,snow=values
        if raw[at]>10 or not all(math.isfinite(v) for v in (start,wet,snow)) or not 0<=start<86400 or not 0<=wet<=1 or not 0<=snow<=1 or raw[at+40]>5 or raw[at+41]>4:raise InvalidSave('Invalid weather')
        return dict(weather=raw[at],start=start,wetness=wet,snow=snow,accel=raw[at+40],grip=raw[at+41])
    preset,at=text(raw,d+100);count=integer(raw,at);at+=4
    if not 1<=count<=40:raise InvalidSave('Invalid calendar count')
    stages=[]
    for _ in range(count):
        day=integer(raw,at);at+=4
        if day<0 or day>3:raise InvalidSave('Invalid calendar day')
        stage,at=text(raw,at);w=weather(at);weather(at+42);at+=84
        zone,at=text(raw,at);stages.append(dict(stage=stage,zone=zone,**w))
    if at+24!=end or integer(raw,at)!=0:raise InvalidSave('Invalid calendar boundary')
    rules={k:raw[d+offset] for k,offset in [('respawn',9),('damage',14),('intensity',22),('wear',23),('failures',24),('penalty',90)]}
    if rules['respawn']>1 or rules['damage']>1 or any(rules[k]>3 for k in ['intensity','wear','failures']) or rules['penalty'] not in [1,2]:raise InvalidSave('Invalid rally rules')
    done=0
    if integer(raw,row[2])==2:
        marker=b'RaceEventRallyWeekendDataComponent\0';p=raw.find(marker,end,row[3])
        if p<0 or integer(raw,p+len(marker))!=4:raise InvalidSave('Missing rally progress')
        done=integer(raw,p+len(marker)+4)
        if not 0<=done<=count:raise InvalidSave('Invalid rally progress')
    report={'version':1,'rules':rules,'preset':preset,'opponents':integer(raw,d+71),'order':raw[d+91],'start_position':integer(raw,d+92),'stages':stages}
    return report,done
