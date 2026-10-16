"""Bounded live trace review. Client-reported telemetry is evidence, not attestation."""
import base64,hashlib,json,math,time,zlib
from html import escape
from i18n import tr
RETENTION=30*86400
ARCHIVE_RETENTION=7*86400
MAX_STAGE_POINTS=16000
MAX_EVENT_POINTS=200000
MAX_TOTAL_POINTS=1000000

# A registration or RUN alone is not a driven stage. The start history survives
# DNF and service breaks, unlike players.started (the current stage timer).
_STARTED_SQL='''(p.started IS NOT NULL OR p.car_id IS NOT NULL OR p.stage_index>0
    OR EXISTS (SELECT 1 FROM stage_starts s WHERE s.player_id=p.id)
    OR EXISTS (SELECT 1 FROM telemetry_runs h WHERE h.player_id=p.id))'''


def _progress(status):
    css,text={
        'dnf':('trace-bad','DNF — the driver did not finish the rally.'),
        'completed':('trace-good','Rally completed.'),
        'awaiting_results':('trace-warn','All stages driven — awaiting official result confirmation.'),
    }.get(status,('trace-warn','The driver has not finished all stages yet.'))
    return '<span class="small trace-progress '+css+'">'+escape(tr(text))+'</span>'


def install(store):
    store.db.execute('''CREATE TABLE IF NOT EXISTS telemetry_runs (
      player_id INTEGER NOT NULL REFERENCES players(id), stage_index INTEGER NOT NULL,
      point_count INTEGER NOT NULL, last_seq INTEGER NOT NULL, summary TEXT NOT NULL,
      updated REAL NOT NULL, PRIMARY KEY(player_id,stage_index))''')
    store.db.execute('''CREATE TABLE IF NOT EXISTS telemetry_chunks (
      player_id INTEGER NOT NULL REFERENCES players(id), stage_index INTEGER NOT NULL,
      seq INTEGER NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL,
      received REAL NOT NULL, PRIMARY KEY(player_id,stage_index,seq))''')


def expire(store,now):
    if now-getattr(store,'_trace_cleanup_at',0)<30:return
    store._trace_cleanup_at=now
    for table in ('telemetry_chunks','telemetry_runs'):
        store.db.execute('DELETE FROM '+table+''' WHERE player_id IN (
          SELECT p.id FROM players p JOIN events e ON e.id=p.event_id WHERE
          (e.closes<=? AND NOT EXISTS (SELECT 1 FROM season_events se WHERE se.event_id=e.id)) OR
          (e.closes<=? AND EXISTS (SELECT 1 FROM season_events se JOIN seasons s ON s.id=se.season_id
             WHERE se.event_id=e.id AND s.closes<=?)))''', (now-RETENTION,now-ARCHIVE_RETENTION,now))


def expired(store,event_id,closes,now):
    season=store.db.execute('''SELECT s.closes FROM seasons s JOIN season_events se ON se.season_id=s.id
      WHERE se.event_id=?''',(event_id,)).fetchone()
    return (now>=closes+ARCHIVE_RETENTION and now>=season['closes']) if season else now>=closes+RETENTION


def pack_payload(payload):
    packed='z1:'+base64.b64encode(zlib.compress(payload.encode(),6)).decode()
    return packed if len(packed)<len(payload) else payload


def unpack_payload(payload):
    if not payload.startswith('z1:'):
        return json.loads(payload)
    decoder=zlib.decompressobj()
    raw=decoder.decompress(base64.b64decode(payload[3:],validate=True),65537)
    if len(raw)>65536 or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid compressed telemetry')
    return json.loads(raw)


def expired_message():
    return tr('Telemetry expired; results and penalties remain.')


def _point(p):
    if not isinstance(p,list) or len(p)!=10 or type(p[0]) is not int or not 0<=p[0]<=14400000:return False
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in p[1:4]):return False
    if any(abs(v)>1000000 for v in p[1:3]) or not 0<=p[3]<=600:return False
    for i,lo,hi in [(4,0,1),(5,0,1),(6,-2,2),(7,-1,12),(8,0,20000)]:
        if p[i] is not None and (type(p[i]) not in (int,float) or not math.isfinite(p[i]) or not lo<=p[i]<=hi):return False
    return p[9] is None or type(p[9]) is bool


def submit(store,token,data):
    from server import Fault
    if not store.lock.acquire(blocking=False):
        raise Fault(429,tr('Telemetry deferred while timing or administration is busy'))
    try:return _submit_locked(store,token,data)
    finally:store.lock.release()


def _submit_locked(store,token,data):
    from server import Fault
    with store.lock:
        store._begin()
        try:
            p=store._auth(token);row,ev=store.event(p['event_id']);now=time.time()
            if expired(store,p['event_id'],row['closes'],now):raise Fault(410,tr('Telemetry retention has expired'))
            idx=data.get('stageIndex');seq=data.get('seq');points=data.get('points');dropped=data.get('dropped',0)
            if data.get('eventId')!=p['event_id'] or type(idx) is not int or not 0<=idx<len(ev['stages']) or type(seq) is not int or not 0<=seq<=6000 or type(dropped) is not int or not 0<=dropped<=1000000 or not isinstance(points,list) or not 1<=len(points)<=12 or not all(_point(x) for x in points):
                raise Fault(400,tr('Invalid live telemetry batch'))
            prov=store.db.execute('SELECT finished FROM provisional WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
            active=p['status']=='active' and idx==p['stage_index']
            recent_finish=prov is not None and now-prov['finished']<=60
            recent_dnf=p['status']=='dnf' and idx==p['stage_index'] and p['last_seen'] is not None and now-p['last_seen']<=60
            if not (active or recent_finish or recent_dnf):raise Fault(409,tr('Telemetry has no active or just-finished stage'))
            payload=json.dumps({'points':points,'dropped':dropped},separators=(',',':'));digest=hashlib.sha256(payload.encode()).hexdigest()
            old=store.db.execute('SELECT digest FROM telemetry_chunks WHERE player_id=? AND stage_index=? AND seq=?',(p['id'],idx,seq)).fetchone()
            if old:
                if old['digest']!=digest:raise Fault(409,tr('A received telemetry batch is immutable'))
                store.db.execute('COMMIT');return {'ok':True,'duplicate':True}
            run=store.db.execute('SELECT * FROM telemetry_runs WHERE player_id=? AND stage_index=?',(p['id'],idx)).fetchone()
            if seq!=(run['last_seq']+1 if run else 0):raise Fault(409,tr('Telemetry batch order differs'))
            count=run['point_count'] if run else 0
            usage=store.db.execute('SELECT COALESCE(SUM(t.point_count),0) AS total_points,COALESCE(SUM(CASE WHEN p.event_id=? THEN t.point_count ELSE 0 END),0) AS event_points FROM telemetry_runs t JOIN players p ON p.id=t.player_id',(p['event_id'],)).fetchone()
            total,event_count=usage['total_points'],usage['event_points']
            if count+len(points)>MAX_STAGE_POINTS or event_count+len(points)>MAX_EVENT_POINTS or total+len(points)>MAX_TOTAL_POINTS:raise Fault(507,tr('Telemetry storage limit reached; racing times remain unaffected'))
            s=json.loads(run['summary']) if run else {'first_ms':points[0][0],'last_ms':points[0][0],'distance_m':0,'max_speed':0,'gaps':0,'jumps':0,'severe':0,'dropped':0,'gas_total':0,'gas_n':0,'brake_total':0,'brake_n':0,'air_n':0,'air_total':0,'last_point':None}
            for point in points:
                previous=s['last_point']
                if previous:
                    delta=point[0]-previous[0]
                    if delta<=0:raise Fault(409,tr('Telemetry clock must increase within a stage'))
                    distance=math.hypot(point[1]-previous[1],point[2]-previous[2])
                    s['distance_m']+=distance
                    if delta>8000:s['gaps']+=1
                    allowance=max(150,max(previous[3],point[3])/3.6*(delta/1000)*3+30)
                    if distance>allowance:s['jumps']+=1
                    if delta<=3000 and distance>1000:s['severe']+=1
                if point[3]>350:s['severe']+=1
                s['max_speed']=max(s['max_speed'],point[3]);s['last_ms']=point[0];s['last_point']=point
                for index,key in [(4,'gas'),(5,'brake')]:
                    if point[index] is not None:s[key+'_total']+=point[index];s[key+'_n']+=1
                if point[9] is not None:s['air_n']+=1;s['air_total']+=int(point[9])
            s['dropped']=max(s['dropped'],dropped)
            store.db.execute('INSERT INTO telemetry_chunks(player_id,stage_index,seq,payload,digest,received) VALUES(?,?,?,?,?,?)',(p['id'],idx,seq,pack_payload(payload),digest,now))
            store.db.execute('''INSERT INTO telemetry_runs(player_id,stage_index,point_count,last_seq,summary,updated) VALUES(?,?,?,?,?,?)
              ON CONFLICT(player_id,stage_index) DO UPDATE SET point_count=excluded.point_count,last_seq=excluded.last_seq,summary=excluded.summary,updated=excluded.updated''',(p['id'],idx,count+len(points),seq,json.dumps(s,separators=(',',':')),now))
            store.db.execute('COMMIT');return {'ok':True}
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def evaluate(run,raw_ms=None,clock_ms=None,live=False):
    if not run:return 1,[tr('No retained telemetry')]
    s=json.loads(run['summary']);notes=[];level=0
    if s['severe']:level=2;notes.append(tr('Large position jump or extreme speed: review required'))
    if s['jumps']:level=max(level,1);notes.append(tr('Position discontinuities; respawn may also cause these'))
    if s['gaps'] or s['dropped']:level=max(level,1);notes.append(tr('Gaps or dropped samples'))
    if run['point_count']>=10 and s['last_ms']-s['first_ms']>=8000 and s['distance_m']<10 and s['max_speed']>20:
        level=max(level,1);notes.append(tr('Position may be frozen despite reported speed'))
    if raw_ms is not None and clock_ms is not None:
        diff=abs(raw_ms-clock_ms)
        if diff>250:level=max(level,2 if diff>5000 else 1);notes.append(tr('RAW vs finish telemetry difference')+': '+str(diff)+' ms')
        if run['point_count']<10 or (s['last_ms']-s['first_ms'])<raw_ms*.75:level=max(level,1);notes.append(tr('Incomplete stage coverage'))
    elif not live:level=max(level,1);notes.append(tr('Official result not confirmed'))
    if live:level=max(level,1);notes.append(tr('Recording in progress'))
    if not notes:notes=[tr('No detected signals in recorded data; not proof against cheating')]
    return level,notes


def summaries(store,event_id):
    from server import Fault
    with store.lock:
        row,ev=store.event(event_id)
        if expired(store,event_id,row['closes'],time.time()):return '<p class="muted">'+escape(expired_message())+'</p>'
        rows=store.db.execute('''SELECT p.id,p.nickname,p.status,p.stage_index,t.stage_index AS recorded_stage,t.point_count,t.summary,t.updated,
          t.last_seq,r.raw_ms,v.clock_ms FROM players p LEFT JOIN telemetry_runs t ON t.player_id=p.id
          LEFT JOIN results r ON r.player_id=p.id AND r.stage_index=t.stage_index
          LEFT JOIN provisional v ON v.player_id=p.id AND v.stage_index=t.stage_index WHERE p.event_id=? AND '''+_STARTED_SQL+''' ORDER BY p.nickname,t.stage_index''',(event_id,)).fetchall()
        groups={}
        for r in rows:groups.setdefault(r['id'],[]).append(r)
        if not groups:return '<p class="muted">'+escape(tr('No drivers have started a stage yet.'))+'</p>'
        out='<p class="muted">'+escape(tr('Review signals, not a cheating verdict. Client telemetry can be forged. The path is a world-coordinate projection, not an official road map.'))+'</p>'
        for pid,group in groups.items():
            levels=[];notes=[];count=0
            for r in group:
                live=r['status']=='active' and r['recorded_stage']==r['stage_index']
                level,detail=evaluate(r if r['point_count'] is not None else None,r['raw_ms'],r['clock_ms'],live)
                levels.append(level);count+=r['point_count'] or 0
                notes.extend(detail)
            expected=group[0]['stage_index']+(1 if group[0]['status']=='active' else 0)
            if sum(r['point_count'] is not None for r in group)<expected:
                levels.append(1);notes.append(tr('Some driven stages have no retained samples'))
            if group[0]['status']=='dnf':levels.append(2);notes.append(tr('DNF; inspect the recorded stage and reason'))
            import timing_guard
            timing=timing_guard.flags(store,pid)
            if timing:levels.append(1);notes.extend(timing)
            level=max(levels);css=['trace-good','trace-warn','trace-bad'][level]
            title=[tr('No detected signals'),tr('Review / incomplete data'),tr('Significant signal / DNF')][level]
            out+='<details class="round trace-driver" data-src="/api/telemetry/'+escape(event_id,quote=True)+'/driver/'+str(pid)+'"><summary><span>'+escape(group[0]['nickname'])+' · <span class="'+css+'">'+escape(title)+'</span>'+_progress(group[0]['status'])+'</span><span>'+str(count)+' '+escape(tr('samples'))+'</span></summary>'+'<p class="small '+css+'">'+escape('; '.join(dict.fromkeys(notes)))+'</p><div class="trace-content"></div></details>'
        return out or '<p>'+escape(tr('No retained telemetry'))+'</p>'


def _route(points):
    if len(points)<2:return '<p>'+escape(tr('Not enough points to draw a path'))+'</p>'
    stride=max(1,math.ceil(len(points)/1000));selected=points[::stride]
    if selected[-1]!=points[-1]:selected.append(points[-1])
    xs=[p[1] for p in points];zs=[p[2] for p in points];minx,maxx=min(xs),max(xs);minz,maxz=min(zs),max(zs)
    scale=min(900/max(maxx-minx,1),390/max(maxz-minz,1))
    def xy(p):return 50+(p[1]-minx)*scale,420-(p[2]-minz)*scale
    path=' '.join('%.1f,%.1f'%xy(p) for p in selected)
    svg='<svg class="trace-map" viewBox="0 0 1000 460" role="img" aria-label="'+escape(tr('Recorded driving path'),quote=True)+'"><rect width="1000" height="460" fill="#0e1728"/><polyline points="'+path+'" fill="none" stroke="#87e3de" stroke-width="3"/>'
    for p,color in [(points[0],'#7be0b2'),(points[-1],'#ff7038')]:
        x,y=xy(p);svg+='<circle cx="%.1f" cy="%.1f" r="7" fill="%s"/>'%(x,y,color)
    for p in selected[::max(1,len(selected)//80)]:
        x,y=xy(p);text='%.3f s · %.1f km/h'%(p[0]/1000,p[3])
        if p[4] is not None:text+=' · '+tr('gas')+' %.0f%%'%(p[4]*100)
        if p[5] is not None:text+=' · '+tr('brake')+' %.0f%%'%(p[5]*100)
        if p[7] is not None:text+=' · '+tr('gear')+' '+str(p[7])
        svg+='<circle cx="%.1f" cy="%.1f" r="4" fill="transparent"><title>%s</title></circle>'%(x,y,escape(text))
    svg+='</svg><p class="muted">'+escape(tr('Green: first sample. Orange: last sample. Hover on the path for speed and inputs.'))+'</p>'
    duration=max(1,points[-1][0]-points[0][0]);speedmax=max(1,max(p[3] for p in points))
    speedpath=' '.join('%.1f,%.1f'%(50+(p[0]-points[0][0])/duration*900,160-p[3]/speedmax*130) for p in selected)
    svg+='<svg class="trace-speed" viewBox="0 0 1000 190" role="img" aria-label="'+escape(tr('Speed over stage time'),quote=True)+'"><path d="M50 20 V160 H950" fill="none" stroke="#626e85"/><polyline points="'+speedpath+'" fill="none" stroke="#ff7038" stroke-width="2"/><text x="55" y="18" fill="#f2f5f8">%.1f km/h</text><text x="870" y="183" fill="#f2f5f8">%.1f s</text></svg>'%(speedmax,duration/1000)
    return svg


def driver(store,event_id,player_id):
    from server import Fault
    with store.lock:
        row,ev=store.event(event_id)
        p=store.db.execute('SELECT p.nickname,p.status,'+_STARTED_SQL+' AS has_started FROM players p WHERE p.id=? AND p.event_id=?',(player_id,event_id)).fetchone()
        if not p:raise Fault(404,tr('Driver does not belong to this rally'))
        if not p['has_started']:return ''
        if expired(store,event_id,row['closes'],time.time()):return '<p>'+escape(expired_message())+'</p>'
        runs=store.db.execute('SELECT * FROM telemetry_runs WHERE player_id=? ORDER BY stage_index',(player_id,)).fetchall()
        out=''
        for run in runs:
            points=[]
            for chunk in store.db.execute('SELECT payload FROM telemetry_chunks WHERE player_id=? AND stage_index=? ORDER BY seq',(player_id,run['stage_index'])):
                points.extend(unpack_payload(chunk['payload'])['points'])
            s=json.loads(run['summary']);out+='<details class="round" data-trace-stage="'+str(run['stage_index'])+'"><summary>'+escape(tr('SS '))+str(run['stage_index']+1)+' · '+escape(ev['stages'][run['stage_index']]['stageId'])+'</summary>'
            info=[str(run['point_count'])+' '+tr('samples'),'%.2f km'%(s['distance_m']/1000),tr('Maximum speed')+': %.1f km/h'%s['max_speed']]
            if s['gas_n']:info.append(tr('Average gas')+': %.0f%%'%(s['gas_total']/s['gas_n']*100))
            if s['brake_n']:info.append(tr('Average brake')+': %.0f%%'%(s['brake_total']/s['brake_n']*100))
            out+='<p>'+escape(' · '.join(info))+'</p>'+_route(points)+'</details>'
        return _progress(p['status'])+(out or '<p>'+escape(tr('No retained telemetry'))+'</p>')


def section(event_id):
    import json
    html='<section class="card" id="rally-telemetry"><details class="round trace-root" data-src="/api/telemetry/'+escape(event_id,quote=True)+'"><summary>'+escape(tr('Telemetry'))+'</summary><div class="trace-content"><p>'+escape(tr('Open a driver to inspect the recorded path and speed.'))+'</p></div></details></section>'
    script=r'''<script>(()=>{let busy=new WeakSet(),states=new Map();async function update(d){if(!d.open||busy.has(d))return;busy.add(d);try{const r=await fetch(d.dataset.src,{credentials:'same-origin',cache:'no-store'});if(!r.ok)return;const box=d.querySelector(':scope > .trace-content');if(!box)return;for(const driver of box.querySelectorAll('.trace-driver')){const content=driver.querySelector('.trace-content');if(content?.querySelector('[data-trace-stage]'))states.set(driver.dataset.src,[...content.querySelectorAll('[data-trace-stage][open]')].map(x=>x.dataset.traceStage))}if(box.querySelector('[data-trace-stage]'))states.set(d.dataset.src,[...box.querySelectorAll('[data-trace-stage][open]')].map(x=>x.dataset.traceStage));const opened=[...box.querySelectorAll('details[open]')].map(x=>x.dataset.src).filter(Boolean);box.innerHTML=await r.text();for(const x of box.querySelectorAll('[data-trace-stage]'))x.open=(states.get(d.dataset.src)||[]).includes(x.dataset.traceStage);for(const x of box.querySelectorAll('details[data-src]'))if(opened.includes(x.dataset.src)){x.open=true;update(x)}}catch(_){}finally{busy.delete(d)}}document.addEventListener('toggle',e=>{if(e.target.matches?.('details[data-src]')&&e.target.open)update(e.target)},true);setInterval(()=>{const root=document.querySelector('.trace-root');if(root?.open)update(root)},5000)})();</script>'''
    return html,script
