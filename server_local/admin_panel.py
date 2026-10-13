"""Local admin panel for ACR Rally Club, stdlib only.

Admin credentials live only on the server; no password is embedded in client JS.
The HTML/JS UI consumes the original ACR Daily car/stage catalogs found in
server/src and never writes ACR save files itself.
"""
from __future__ import annotations
from i18n import tr
from site_theme import admin_shell

from datetime import datetime
import hashlib
import hmac
from html import escape
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_KEY_FILE = Path(os.environ.get('ACR_ADMIN_KEY_PATH', str(PROJECT_ROOT / 'server_local' / 'admin_key.txt')))
COOKIE_NAME = 'acrclub_admin'
SESSION_TTL_SECONDS = 2 * 3600


class AdminAuth:
    def __init__(self, key_path=ADMIN_KEY_FILE):
        self.key_path = Path(key_path)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        configured_secret = os.environ.get('ACR_ADMIN_KEY', '').strip()
        if not configured_secret and not self.key_path.exists():
            # Create exclusively so an existing key is never silently overwritten.
            try:
                fd = os.open(self.key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'w', encoding='ascii') as out:
                    out.write(secrets.token_urlsafe(32) + '\n')
            except FileExistsError:
                pass
        self._secret = configured_secret or self.key_path.read_text(encoding='ascii').strip()
        if len(self._secret) < 32:
            raise RuntimeError('Admin key too short: remove/recreate server_local/admin_key.txt')
        self._lock = threading.Lock()
        self._sessions = {}  # sha256(session token) -> expiry
        self._failed = {}    # peer -> list of failed-login timestamps

    def login(self, submitted, peer='local'):
        # Rate-limit invalid logins, even for local reverse proxies.
        peer = str(peer)[:128]
        now = time.time()
        with self._lock:
            recent = [t for t in self._failed.get(peer, ()) if now - t < 900]
            self._failed[peer] = recent
            if len(recent) >= 5:
                return None
            valid_key = (isinstance(submitted, str) and
                         hmac.compare_digest(submitted.encode(), self._secret.encode()))
            if not valid_key:
                recent.append(now)
                return None
            self._failed.pop(peer, None)
            token = secrets.token_urlsafe(32)
            self._sessions[hashlib.sha256(token.encode()).digest()] = now + SESSION_TTL_SECONDS
            return token

    def valid(self, token):
        if not isinstance(token, str):
            return False
        key = hashlib.sha256(token.encode()).digest()
        with self._lock:
            exp = self._sessions.get(key)
            if not exp:
                return False
            if exp <= time.time():
                self._sessions.pop(key, None)
                return False
            return True

    def logout(self, token):
        if isinstance(token, str):
            with self._lock:
                self._sessions.pop(hashlib.sha256(token.encode()).digest(), None)

    def cookie(self, token, *, secure=False):
        return (f'{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL_SECONDS}'
                + ('; Secure' if secure else ''))

    def expired_cookie(self):
        return f'{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'


def _parse_js_catalogs(root):
    root = Path(root)
    cars_file = root / 'server' / 'src' / 'cars.js'
    stages_file = root / 'server' / 'src' / 'stages.js'
    if not (cars_file.is_file() and stages_file.is_file()):
        raise ValueError(tr('Original ACR Daily catalogs are missing: server/src/cars.js and stages.js'))
    s = cars_file.read_text(encoding='utf-8')
    car_pat = re.compile(r"\{\s*id:\s*'([^']+)',\s*telemetry:\s*'([^']+)',\s*name:\s*'([^']+)',\s*cls:\s*'([^']+)',\s*group:\s*'([^']+)'", re.M)
    cars = [dict(id=a, telemetry=b, name=c, cls=d, group=e) for a,b,c,d,e in car_pat.findall(s)]
    if len(cars) < 10:
        raise ValueError(f"{tr('Cannot read the ACR Daily car catalog: recognized ')}{len(cars)}")
    stages_text = stages_file.read_text(encoding='utf-8')
    st_pat = re.compile(r'^\s*([A-Za-z0-9]+):\s*([\'\"])(.*?)\2\s*,\s*$', re.M)
    stages = [{'id': sid, 'name': name} for sid, _, name in st_pat.findall(stages_text)
              if sid.startswith(('Greece','Alsace','Weles','MonteCarlo'))]
    if len(stages) < 20:
        raise ValueError(f"{tr('Cannot read the ACR Daily stage catalog: recognized ')}{len(stages)}")
    return {'cars': cars, 'stages': stages}


def load_catalog(root=PROJECT_ROOT):
    # Catalog is read on request, so the admin can merge the original repo even
    # after the initial first start. No module import of GUI/client dependencies.
    from integrity_rules import WEATHERS, LEVELS, PENALTIES
    out = _parse_js_catalogs(root)
    out['locations'] = ['Greece','Alsace','Wales','MonteCarlo']
    out['weathers'] = WEATHERS
    out['levels'] = list(LEVELS)
    out['penalties'] = list(PENALTIES)
    return out


def validate_catalog_event(event, catalog):
    if not isinstance(event, dict):
        raise ValueError(tr('Invalid rally object'))
    ids = {x['id']: x for x in catalog['cars']}
    if any(x not in ids or ids[x]['cls'] != event.get('carClass') for x in event.get('allowedCars', [])):
        raise ValueError(tr('Cars must belong to one selected ACR class'))
    stage_ids = {x['id'] for x in catalog['stages']}
    if any(x.get('stageId') not in stage_ids for x in event.get('stages', []) if isinstance(x, dict)):
        raise ValueError(tr('Unknown stage ID in the ACR Daily catalog'))
    if 'weekend' in event:
        r = event['weekend']
        if not isinstance(r, dict):
            raise ValueError(tr('Invalid weekend settings'))
        from integrity_rules import LEVELS, PENALTIES
        if r.get('damageIntensity') not in LEVELS or r.get('wear') not in LEVELS or r.get('failures') not in LEVELS:
            raise ValueError(tr('Invalid damage, wear or failure level'))
        if r.get('penalty') not in PENALTIES or type(r.get('respawn')) is not bool or type(r.get('damage')) is not bool:
            raise ValueError(tr('Invalid penalty, respawn or damage settings'))
    return event


PAGE = r"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR Rally Club · Administration</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0c131a;color:#eaf1f9;font:15px/1.55 system-ui,Segoe UI,sans-serif}
main{max-width:1160px;margin:32px auto;padding:0 20px}header{display:flex;align-items:center;justify-content:space-between;gap:15px;flex-wrap:wrap;margin-bottom:22px}
h1{font-size:27px;letter-spacing:-1px;margin:0}h2{font-size:19px;margin:0 0 14px}h3{font-size:15px;margin:18px 0 9px}
.card{border:1px solid #314453;background:#192631;border-radius:15px;padding:22px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}
label{font-size:13px;font-weight:650;display:block;margin-bottom:4px;color:#b9cbd9}
input,select{font:inherit;background:#0e1a24;color:#edf4fb;border:1px solid #435665;border-radius:8px;padding:10px;width:100%;min-width:0}
input:focus,select:focus{outline:2px solid #45aaf1;outline-offset:0}input[type=checkbox]{width:17px;height:17px;accent-color:#36aee8}
.check{display:inline-flex;align-items:center;gap:8px;font-weight:500;margin:4px 16px 4px 0}.check input{flex:0 0 auto}
button{border:1px solid #55758b;background:#263b4d;color:#f4faff;border-radius:9px;padding:10px 14px;font:inherit;font-weight:650;cursor:pointer}
button.primary{background:#137eb1;border-color:#1c91ca}button.danger{border-color:#9b4f55;color:#ffb3bb;background:#3e252b}button:hover{filter:brightness(1.16)}button:disabled{opacity:.45;cursor:default}
.small{font-size:13px;color:#a8bdce}a{color:#73d0fa} .muted{color:#9aaebf} .pill{font-size:12px;border-radius:99px;padding:4px 9px;background:#304757}
.hstack{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.spaced{justify-content:space-between}
.rowbox{background:#12202b;border:1px solid #354b5d;border-radius:10px;padding:13px;margin:9px 0}
.stagerow{display:grid;grid-template-columns:2.5fr 1.5fr 1fr 90px auto;gap:9px;align-items:end}
.eventrow{display:flex;justify-content:space-between;gap:12px;align-items:center;border-top:1px solid #354b5d;padding:13px 0;flex-wrap:wrap}
#notice{padding:11px 13px;border-radius:9px;white-space:pre-wrap;margin:10px 0}#notice:empty{display:none}.error{background:#4f262b;color:#ffd5d9}.success{background:#143e32;color:#c6ffe6}
#cars{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:3px}#cars .check{font-size:14px}.hide{display:none!important}
@media(max-width:850px){.stagerow{grid-template-columns:1fr 1fr}.grid3{grid-template-columns:1fr 1fr}}@media(max-width:580px){.grid,.grid3,.stagerow{grid-template-columns:1fr} main{padding:0 12px}}
</style></head><body><main>
<header><div><h1>ACR Rally Club <span class="pill">ADMIN</span></h1><span class="small">Rally configuration and Rally Weekend rules</span></div><div class="hstack"><a href="/admin/seasons">Seasons, divisions and teams →</a><a href="/">Results page ↗</a><button id="logout" class="hide">Sign out</button></div></header>
<section id="login" class="card"><h2>Administrator sign-in</h2><p class="small">Find the key in the file <code>server_local\admin_key.txt</code> on the server computer. In cloud mode, use the ACR_ADMIN_KEY environment variable.</p><div class="hstack"><input id="adminKey" style="max-width:520px" type="password" placeholder="Administrator key" autocomplete="off"><button id="loginBtn" class="primary">Sign in</button></div></section>
<div id="workspace" class="hide">
<section class="card"><h2>Discord notifications</h2><p class="small">Create a webhook in your Discord text channel: Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL. A server invite does not allow posting messages.</p><label for="discordWebhook">Discord channel webhook URL (secret)</label><input id="discordWebhook" type="password" autocomplete="off" placeholder="Paste a webhook URL; leave blank to keep the saved URL"><div class="hstack"><label class="check"><input id="discordEnabled" type="checkbox">Enable Discord notifications</label><label class="check"><input id="discordLive" type="checkbox" checked>Live standings</label><label class="check"><input id="discordSummaries" type="checkbox" checked>Rally summaries</label><label for="discordLanguage">Message language</label><select id="discordLanguage"><option value="pl">Polski</option><option value="en">English</option></select></div><div class="hstack"><button id="discordSave">Save Discord settings</button><button id="discordTest">Send test message</button></div><p id="discordStatus" role="status"></p><p class="small">One live table per rally updates within about 15 seconds while the service is running. Telemetry is marked unverified. Summaries follow the closing time once active attempts finish. A sleeping free hosting service sends pending updates when it wakes up.</p></section>

<section class="card"><div class="hstack spaced"><h2>Server rallies</h2><button id="newEvent">+ New rally</button></div><div id="events"></div></section>
<section id="editor" class="card hide"><div class="hstack spaced"><h2 id="editTitle">New rally</h2><button id="closeEditor">Close editor</button></div>
<div id="notice" role="status"></div>
<div class="grid"><div><label for="name">Rally name</label><input id="name" maxlength="120" placeholder="Greece Rally – Rally2"></div><div><label for="eventId">Rally ID (generated automatically)</label><input id="eventId" readonly placeholder="The server assigns the ID when saving"></div></div>
<div class="grid" style="margin-top:14px"><div><label for="opensAt">Rally opens (UTC+2)</label><input id="opensAt" type="datetime-local"></div><div><label for="closesAt">Rally closes (UTC+2)</label><input id="closesAt" type="datetime-local"></div></div>
<div class="grid" style="margin-top:14px"><div><label for="location">Location (all stages from the same location)</label><select id="location"></select></div><div><label for="carClass">Car class</label><select id="carClass"></select></div></div>
<h3>Allowed cars</h3><div id="cars" class="rowbox"></div>
<h3>Rally Weekend settings</h3><div class="rowbox"><div class="hstack"><label class="check"><input id="damage" type="checkbox" checked>Damage</label><label class="check"><input id="respawn" type="checkbox" checked>Allow car respawn</label></div><div class="grid3" style="margin-top:9px"><div><label>Damage intensity</label><select id="damageIntensity"></select></div><div><label>Wear</label><select id="wear"></select></div><div><label>Mechanical failures</label><select id="failures"></select></div></div><div style="max-width:370px;margin-top:9px"><label>Penalty mode</label><select id="penalty"></select></div></div>
<div class="hstack spaced"><h3>Stage schedule (2–40)</h3><button id="addStage">+ Add stage</button></div><p class="small">Each stage has its own route, weather and start time. Use ↑ ↓ to change the order.</p><div id="stages"></div>
<div class="hstack" style="margin-top:20px"><button id="save" class="primary">Save rally to server</button><button id="export">Export JSON</button></div>
<p class="small">Configuration is locked after the first participant registers. Changing settings during a rally could invalidate attempts.</p>
</section></div>
<footer class="small">Keep the backend port private. Public hosting requires HTTPS and the protected reverse proxy.</footer>
</main>
<script>
'use strict';
const $ = id => document.getElementById(id);
let catalog = null, allEvents = [], editing = null, stageRows = [];
const ehtml = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const elOpt = (value,label,selected) => `<option value="${ehtml(value)}" ${selected?'selected':''}>${ehtml(label)}</option>`;
const notify = (text,err=true) => { const n=$('notice'); n.textContent=text; n.className=err?'error':'success'; };
const isoLocal = utc => {let d=new Date(utc); if(!Number.isFinite(d.getTime()))return '';return new Date(d.getTime()+2*3600000).toISOString().slice(0,16)};
const toUtc = value => {const date=new Date(value+':00+02:00');if(!value||!Number.isFinite(date.getTime()))throw Error('Enter valid UTC+2 dates');return date.toISOString()};
const choices = (node, values, current) => {node.innerHTML=values.map(x=>elOpt(x,x,x===current)).join('')};
async function request(url, method='GET', data=undefined){
 const init={method, credentials:'same-origin', headers: {'X-ACR-Admin':'1'}};
 if(data!==undefined){init.headers['Content-Type']='application/json';init.body=JSON.stringify(data)}
 const response=await fetch(url,init); const json=await response.json().catch(()=>({error:'Response error'}));
 if(!response.ok)throw Error(json.error||'HTTP '+response.status);return json;
}
async function refresh(){
 try{const [cat,events]=await Promise.all([request('/api/admin/catalog'),request('/api/admin/events')]);catalog=cat;allEvents=events.events;
 $('workspace').classList.remove('hide');$('login').classList.add('hide');$('logout').classList.remove('hide');renderEvents();await loadDiscord();}
 catch(ex){$('workspace').classList.add('hide');$('login').classList.remove('hide');$('logout').classList.add('hide');if(ex.message!=='No administrator session')alert(ex.message)}
}
function renderEvents(){
 $('events').innerHTML=allEvents.length?allEvents.map(ev=>`<div class="eventrow"><div><strong>${ehtml(ev.name)}</strong> <span class="pill">${ehtml(ev.location)}</span><div class="small">${ehtml(ev.id)} · ${ev.stages.length} SS · ${ehtml(ev.carClass)} · ${ev.participantCount||0} participants · ${ehtml(new Date(ev.opensAt).toLocaleString(document.documentElement.lang,{timeZone:'Etc/GMT-2'})+' UTC+2')} — ${ehtml(new Date(ev.closesAt).toLocaleString(document.documentElement.lang,{timeZone:'Etc/GMT-2'})+' UTC+2')}</div></div><div class="hstack"><a href="/rally/${encodeURIComponent(ev.id)}">Results</a><button data-edit="${ehtml(ev.id)}" ${ev.participantCount?'disabled title="The rally has participants"':''}>Edit</button><button class="danger" data-delete="${ehtml(ev.id)}" ${ev.participantCount?'disabled title="The rally has participants"':''}>Delete</button></div></div>`).join(''):'<p class="muted">No rallies yet. Click “New rally”.</p>';
 $('events').querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openEditor(allEvents.find(e=>e.id===b.dataset.edit)));
 $('events').querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>removeEvent(b.dataset.delete));
}
function applyCatalog(){
 choices($('location'),catalog.locations,'Greece');
 choices($('carClass'),[...new Set(catalog.cars.map(c=>c.cls))].sort(),'Rally2/R5');
 for(const k of ['damageIntensity','wear','failures'])choices($(k),catalog.levels,k==='failures'?'off':'light');
 choices($('penalty'),catalog.penalties,'light');
}
function renderCars(selected){
 const cars=catalog.cars.filter(c=>c.cls===$('carClass').value);
 $('cars').innerHTML=cars.map(c=>`<label class="check"><input type="checkbox" data-car="${ehtml(c.id)}" ${selected.has(c.id)?'checked':''}>${ehtml(c.name)}</label>`).join('')||'No cars in this class';
}
function stageOptions(location, current){
 let prefix={Greece:'Greece',Alsace:'Alsace',Wales:'Weles',MonteCarlo:'MonteCarlo'}[location];
 return catalog.stages.filter(s=>s.id.startsWith(prefix)).map(s=>elOpt(s.id,s.name+' ('+s.id+')',s.id===current)).join('');
}
function renderStages(){
 $('stages').innerHTML=stageRows.map((s,i)=>`<div class="rowbox stagerow" data-row="${i}"><div><label>SS ${i+1} · Route</label><select data-field="stageId">${stageOptions($('location').value,s.stageId)}</select></div><div><label>Weather</label><select data-field="weatherGame">${catalog.weathers.map(w=>elOpt(w,w,w===s.weatherGame)).join('')}</select></div><div><label>In-game time</label><input data-field="startTime" type="time" value="${ehtml(secToTime(s.startSeconds))}"></div><div><label class="check"><input data-field="serviceBefore" type="checkbox" ${s.serviceBefore?'checked':''}>Service</label></div><div class="hstack"><button data-act="up" ${i===0?'disabled':''} title="Move up">↑</button><button data-act="down" ${i===stageRows.length-1?'disabled':''} title="Move down">↓</button><button data-act="remove" class="danger" title="Remove stage">×</button></div></div>`).join('');
 $('stages').querySelectorAll('[data-row]').forEach(row=>{const i=+row.dataset.row;
 row.querySelectorAll('[data-field]').forEach(input=>{let f=input.dataset.field; input.onchange=()=>{stageRows[i][f]=f==='startTime'?timeToSec(input.value):f==='serviceBefore'?input.checked:input.value};});
 row.querySelectorAll('[data-act]').forEach(btn=>btn.onclick=()=>{const a=btn.dataset.act;if(a==='remove')stageRows.splice(i,1);else{const j=i+(a==='up'?-1:1);[stageRows[i],stageRows[j]]=[stageRows[j],stageRows[i]];}renderStages();});
 });
}
const secToTime = value => {const v=Math.floor(Number(value)||0);return String(Math.floor(v/3600)).padStart(2,'0')+':'+String(Math.floor(v%3600/60)).padStart(2,'0')};
const timeToSec = str => {const [h,m]=str.split(':').map(Number);return h*3600+m*60};
function blankStage(){let location=$('location').value;let prefix={Greece:'Greece',Alsace:'Alsace',Wales:'Weles',MonteCarlo:'MonteCarlo'}[location];let stage=catalog.stages.find(s=>s.id.startsWith(prefix));if(!stage)throw Error('No stages for '+location);return {stageId:stage.id,weatherGame:'WT_CLEAR',startSeconds:43200,serviceBefore:stageRows.length===0};}
function openEditor(ev=null){
 editing=ev?.id||null;applyCatalog();
 $('editor').classList.remove('hide');$('notice').textContent='';$('editTitle').textContent=editing?'Edit rally':'Create a rally';
 $('name').value=ev?.name||'';$('eventId').value=ev?.id||'';$('eventId').readOnly=true;
 $('opensAt').value=ev?isoLocal(ev.opensAt):isoLocal(new Date(Date.now()+5*60000));
 $('closesAt').value=ev?isoLocal(ev.closesAt):isoLocal(new Date(Date.now()+4*86400000));
 if(ev){$('location').value=ev.location;$('carClass').value=ev.carClass;}
 renderCars(new Set(ev?.allowedCars||catalog.cars.filter(c=>c.cls===$('carClass').value).map(c=>c.id)));
 const r=ev?.weekend||{};
 $('damage').checked=r.damage??true;$('respawn').checked=r.respawn??true;
 $('damageIntensity').value=r.damageIntensity||'light';$('wear').value=r.wear||'light';$('failures').value=r.failures||'off';$('penalty').value=r.penalty||'light';
 stageRows=ev?ev.stages.map(s=>({...s})):[];if(!ev){stageRows.push(blankStage());stageRows.push(blankStage())}renderStages();
 $('editor').scrollIntoView({behavior:'smooth'});
}
function collect(){
 const raw = {schemaVersion:1,name:$('name').value.trim(),location:$('location').value,
 opensAt:toUtc($('opensAt').value),closesAt:toUtc($('closesAt').value),carClass:$('carClass').value,
 allowedCars:[...$('cars').querySelectorAll('[data-car]:checked')].map(x=>x.dataset.car),
 stages:stageRows.map(s=>({...s})),weekend:{damage:$('damage').checked,respawn:$('respawn').checked,
 damageIntensity:$('damageIntensity').value,wear:$('wear').value,failures:$('failures').value,penalty:$('penalty').value}};
 if(raw.stages.length<2||raw.stages.length>40)throw Error('A rally must have 2–40 stages');if(editing)raw.id=editing;return raw;
}
async function save(){try{const ev=collect();const path=editing?'/api/admin/events/'+encodeURIComponent(editing):'/api/admin/events';const answer=await request(path,'POST',ev);await refresh();editing=answer.id;$('eventId').value=answer.id;notify('Rally saved. ID: '+answer.id,false);renderEvents();}
 catch(ex){notify('Save error: '+ex.message)}}
async function removeEvent(id){if(!confirm('Delete '+id+'? A rally with participants cannot be deleted.'))return;
 try{await request('/api/admin/events/'+encodeURIComponent(id)+'/delete','POST',{});await refresh();$('editor').classList.add('hide')}catch(ex){alert(ex.message)} }
$('loginBtn').onclick=async()=>{try{await request('/api/admin/login','POST',{key:$('adminKey').value});$('adminKey').value='';await refresh()}catch(ex){alert('Sign-in: '+ex.message)}};
$('adminKey').onkeydown=e=>{if(e.key==='Enter')$('loginBtn').click()};
$('logout').onclick=async()=>{await request('/api/admin/logout','POST',{});location.reload()};
$('newEvent').onclick=()=>openEditor();$('closeEditor').onclick=()=>$('editor').classList.add('hide');
$('carClass').onchange=()=>renderCars(new Set(catalog.cars.filter(c=>c.cls===$('carClass').value).map(c=>c.id)));
$('location').onchange=()=>{stageRows=[];renderStages()};
$('addStage').onclick=()=>{if(stageRows.length>=40)return alert('Maximum 40 stages');try{stageRows.push(blankStage());renderStages()}catch(ex){alert(ex.message)}};
$('save').onclick=save;
$('export').onclick=()=>{try{if(!editing)throw Error('Save the rally to the server first to receive its generated ID');const json=JSON.stringify(collect(),null,2);const blob=new Blob([json],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=$('eventId').value+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}catch(ex){notify(ex.message)}};
function showDiscord(d){
 $('discordEnabled').checked=d.enabled;$('discordLive').checked=d.live;$('discordSummaries').checked=d.summaries;$('discordLanguage').value=d.language;
 $('discordStatus').textContent=(d.configured?'Webhook saved. ':'Webhook not configured. ')+(d.enabled?'Notifications enabled. ':'Notifications disabled. ')+(d.lastSent?'Last delivery: '+new Date(d.lastSent*1000).toLocaleString(document.documentElement.lang)+'. ':'')+(d.lastError||'');
}
async function loadDiscord(){showDiscord(await request('/api/admin/discord'));}
$('discordSave').onclick=async()=>{try{showDiscord(await request('/api/admin/discord','POST',{webhook:$('discordWebhook').value,enabled:$('discordEnabled').checked,live:$('discordLive').checked,summaries:$('discordSummaries').checked,language:$('discordLanguage').value}));$('discordWebhook').value='';}catch(ex){$('discordStatus').textContent=ex.message}};
$('discordTest').onclick=async()=>{try{await request('/api/admin/discord/test','POST',{});await loadDiscord();}catch(ex){$('discordStatus').textContent=ex.message}};
refresh();
</script></body></html>"""


def html():
    from admin_customization import enhance
    from admin_penalties import enhance as penalty_tools
    return admin_shell(penalty_tools(enhance(tr(PAGE))))
