from i18n import tr
from site_theme import admin_shell
"""Standalone administrator's season editor; served alongside the original rally editor."""
PAGE = r"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ACR Rally Club — Seasons</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{font:15px/1.5 system-ui,Segoe UI,sans-serif;color:#eaf2fa;background:#0b131c;margin:0}
main{max-width:1220px;margin:25px auto;padding:0 17px}h1{font-size:28px;letter-spacing:-.7px}h2{font-size:20px}h3{font-size:17px}
a{color:#80d6fa}.card{background:#172532;border:1px solid #35495a;border-radius:13px;padding:22px;margin:16px 0}
button{background:#25485c;color:#fff;border:1px solid #486980;border-radius:7px;font:inherit;padding:9px 13px;cursor:pointer}
button.primary{background:#187cae}button:disabled{opacity:.45;cursor:default}
input,select{background:#101c28;color:#fff;border:1px solid #556a7a;border-radius:7px;padding:9px;font:inherit;width:100%;min-width:0}
label{display:block;color:#b5c8d5;margin:10px 0 4px;font-size:13px;font-weight:600}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}small,.muted{color:#a3b8c7}
.hrow{border-top:1px solid #34485a;padding:9px 0;display:flex;gap:10px;align-items:center;justify-content:space-between}
#notice{padding:12px;white-space:pre-wrap}.danger{color:#ffa2a2}.hide{display:none!important}.pane{border:1px solid #334859;background:#0f1c28;padding:15px;border-radius:10px;margin:14px 0}
.pill{display:inline-block;background:#274455;border-radius:10px;padding:2px 8px;font-size:12px}.compact{width:auto;min-width:120px}
@media(max-width:650px){.grid{grid-template-columns:1fr}}
</style></head><body><main>
<header class="row" style="justify-content:space-between"><div><h1>ACR Rally Club — seasons</h1><small>Up to 100 rallies · 10 divisions · 10 drivers per team</small></div><div><a href="/admin">← Rally administration</a> · <a href="/">Results</a></div></header>
<div id="notice"></div>
<section id="login" class="card"><h2>Administrator sign-in</h2><div class="row"><input id="key" type="password" placeholder="Administrator key" style="max-width:480px"><button id="loginBtn">Sign in</button></div></section>
<div id="workspace" class="hide">
<section class="card"><div class="row" style="justify-content:space-between"><h2>Seasons</h2><button class="primary" id="newSeason">+ New season</button></div><div id="seasonList"></div></section>
<section id="editor" class="card hide"><h2 id="editTitle">Create a season</h2>
<div class="grid"><div><label>Season name</label><input id="name" placeholder="ACR Rally Club — Season 2027"></div>
<div><label>Team scoring mode</label><select id="teamMode"><option value="combined">Overall + division + Power Stage</option><option value="general">Overall + Power Stage</option><option value="division">Division points only</option></select></div>
<div><label>Season opens (UTC+2)</label><input id="opens" type="datetime-local"></div><div><label>Season closes (UTC+2)</label><input id="closes" type="datetime-local"></div>
<div><label>Overall points — positions 1, 2, 3…</label><input id="general" placeholder="35,25,20,16,13,11,9,7,5,3,2"></div>
<div><label>Division points — positions 1, 2, 3…</label><input id="division" placeholder="30,20,15,12,10,8,6,4,3,2"></div>
<div><label>Power Stage — final stage (positions 1, 2, 3…)</label><input id="powerStage" placeholder="5,4,3,2,1" value="5,4,3,2,1"></div></div>
<p class="muted">Quick scoring: comma-separated values. Each classified driver below the last listed position receives 1 point. DNF = 0 points. <strong>Power Stage</strong>: 5,4,3,2,1 for the final stage; other drivers = 0 PS points, DNF = 0. An empty PS table disables the bonus. Points can also be overridden per rally. Points are awarded after the rally closes.</p>
<div class="row"><button class="primary" id="saveSeason">Save season settings</button><button id="closeEditor">Close</button></div>
<div id="seasonExtra" class="hide">
<div class="pane"><h3>Season rallies — up to 100</h3><p class="muted">Create rallies first in the <a href="/admin">rally panel</a>. Select events in season order, then save the calendar. Rally dates must fall within the season window.</p>
<div id="rallies"></div><div class="row"><button id="saveRallies">Save calendar</button><small id="rallyCount"></small></div></div>
<div class="grid"><div class="pane"><h3>Divisions (up to 10)</h3><div id="divisions"></div><div class="row"><input id="newDivision" placeholder="e.g. Division 3"><button id="addDivision">Add</button></div></div>
<div class="pane"><h3>Teams (up to 10 drivers each)</h3><div id="teams"></div><div class="row"><input id="newTeam" placeholder="e.g. ACR Team Poland"><button id="addTeam">Add</button></div></div></div>
<div class="pane"><h3>Driver assignments</h3><p class="muted">Assign each club member to a division and an optional team. A driver's assignment is locked after their first rally start.</p>
<div id="assignments"></div></div>
<p><a id="standings" href="/">Open season standings →</a></p>
</div></section></div>
<script>
'use strict';
const $=id=>document.getElementById(id);
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let seasons=[],events=[],members=[],current=null,detail=null;
function notify(text,error=false){$('notice').textContent=text;$('notice').style.color=error?'#ffaaaa':'#92efbf'}
async function api(path,method='GET',body){const init={method,credentials:'same-origin',headers:{'X-ACR-Admin':'1'}};
 if(body!==undefined){init.headers['Content-Type']='application/json';init.body=JSON.stringify(body)}
 const r=await fetch(path,init);const val=await r.json().catch(()=>({error:'Invalid server response'}));
 if(!r.ok)throw Error(val.error||('HTTP '+r.status));return val}
const localISO=iso=>{let d=new Date(iso);if(isNaN(d))return '';return new Date(d.getTime()+2*3600000).toISOString().slice(0,16)};
const utc=txt=>{let d=new Date(txt+':00+02:00');if(isNaN(d))throw Error('Niepoprawna data UTC+2');return d.toISOString()};
const powerPoints=str=>{const trimmed=str.trim();if(!trimmed)return [];const a=trimmed.split(',').map(s=>Number(s.trim()));if(a.length>100||a.some(v=>!Number.isInteger(v)||v<0||v>1000))throw Error('Power Stage: 0–1000 points per position, up to 100 positions');return a};
const points=str=>{const a=str.split(',').map(s=>Number(s.trim()));if(!a.length||a.length>100||a.some(v=>!Number.isInteger(v)||v<1||v>1000))throw Error('Points: comma-separated integers from 1 to 1000');return a};
async function refresh(){const [s,e,m]=await Promise.all([api('/api/admin/seasons'),api('/api/admin/events'),api('/api/admin/club-members')]);
 seasons=s.seasons;events=e.events;members=m.members;$('workspace').classList.remove('hide');$('login').classList.add('hide');renderSeasons()}
function renderSeasons(){$('seasonList').innerHTML=seasons.length?seasons.map(s=>`<div class="hrow"><div><b>${safe(s.name)}</b><div class="muted">${s.rallyCount} rallies · ${safe(new Date(s.opensAt).toLocaleDateString(document.documentElement.lang,{timeZone:'Etc/GMT-2'}))} — ${safe(new Date(s.closesAt).toLocaleDateString(document.documentElement.lang,{timeZone:'Etc/GMT-2'}))}</div></div><div class="row"><a href="/season/${encodeURIComponent(s.id)}">Results</a><button data-open="${safe(s.id)}">Edit</button></div></div>`).join(''):'<p>No seasons yet.</p>';
 $('seasonList').querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>openSeason(b.dataset.open))}
function defaults(){current=null;detail=null;$('editor').classList.remove('hide');$('seasonExtra').classList.add('hide');$('editTitle').textContent='New season';$('name').value='';
 $('opens').value=localISO(new Date());$('closes').value=localISO(new Date(Date.now()+180*86400000));$('general').value='35,25,20,16,13,11,9,7,5,3,2';$('division').value='30,20,15,12,10,8,6,4,3,2';$('powerStage').value='5,4,3,2,1';$('teamMode').value='combined';$('editor').scrollIntoView()}
async function openSeason(id){current=id;detail=await api('/api/admin/seasons/'+encodeURIComponent(id));$('editor').classList.remove('hide');$('seasonExtra').classList.remove('hide');$('editTitle').textContent='Edit season: '+detail.name;
 $('name').value=detail.name;$('opens').value=localISO(detail.opensAt);$('closes').value=localISO(detail.closesAt);$('general').value=detail.generalPoints.join(',');$('division').value=detail.divisionPoints.join(',');$('powerStage').value=detail.powerStagePoints.join(',');$('teamMode').value=detail.teamMode;
 $('standings').href='/season/'+encodeURIComponent(id);renderRallies();renderGroups();renderAssignments();$('editor').scrollIntoView()}
function payload(){return {name:$('name').value.trim(),opensAt:utc($('opens').value),closesAt:utc($('closes').value),generalPoints:points($('general').value),divisionPoints:points($('division').value),powerStagePoints:powerPoints($('powerStage').value),teamMode:$('teamMode').value}}
async function saveSeason(){try{const out=await api(current?'/api/admin/seasons/'+encodeURIComponent(current)+'/config':'/api/admin/seasons','POST',payload());await refresh();await openSeason(out.id);notify('Saved season '+out.id)}catch(e){notify(e.message,true)}}
function renderRallies(){const set=new Set(detail.events.map(e=>e.id));const ordered=[...detail.events.map(e=>events.find(r=>r.id===e.id)).filter(Boolean),...events.filter(e=>!set.has(e.id))];
 $('rallies').innerHTML=ordered.map(e=>{const cfg=detail.events.find(x=>x.id===e.id);
 const points=cfg&&(cfg.generalPoints||cfg.divisionPoints||cfg.powerStagePoints!==null)?'• Custom points':'Default points';
 return `<div class="hrow" data-eid="${safe(e.id)}"><label class="row" style="font-size:14px"><input class="evcheck" style="width:18px" type="checkbox" ${set.has(e.id)?'checked':''}><span>${safe(e.name)} <small>${safe(e.id)} · ${points}</small></span></label><div class="row"><button data-points ${!cfg?'disabled title="Save the calendar first"':''}>Rally points</button><button data-up>↑</button><button data-down>↓</button></div></div>`}).join('');
 $('rallies').querySelectorAll('[data-up]').forEach(b=>b.onclick=()=>move(b.closest('[data-eid]'),-1));$('rallies').querySelectorAll('[data-down]').forEach(b=>b.onclick=()=>move(b.closest('[data-eid]'),1));
 $('rallies').querySelectorAll('[data-points]').forEach(b=>b.onclick=()=>editRallyPoints(b.closest('[data-eid]').dataset.eid));countRallies();
 $('rallies').querySelectorAll('.evcheck').forEach(x=>x.onchange=countRallies)}
function move(row,dir){const other=dir<0?row.previousElementSibling:row.nextElementSibling;if(!other)return;
 if(dir<0)other.before(row);else other.after(row)}
function countRallies(){$('rallyCount').textContent=$('rallies').querySelectorAll('.evcheck:checked').length+' / 100'}
async function editRallyPoints(eid){
 const ev=detail.events.find(e=>e.id===eid);if(!ev)return alert('Save the rally calendar before changing points');
 const g=prompt('OVERALL points for positions 1,2,3… Separate with commas. EMPTY = season defaults.',
                 ev.generalPoints?ev.generalPoints.join(','):'');if(g===null)return;
 const d=prompt('DIVISION points for positions 1,2,3… Separate with commas. EMPTY = season defaults.',
                 ev.divisionPoints?ev.divisionPoints.join(','):'');if(d===null)return;
 const p=prompt('Power Stage — final stage: points for positions 1,2,3… (default 5,4,3,2,1). EMPTY = season defaults; enter 0 to disable bonuses for this round.',
                 ev.powerStagePoints===null?'':ev.powerStagePoints.join(','));if(p===null)return;
 try{await api('/api/admin/seasons/'+current+'/rally-points','POST',
        {eventId:eid,generalPoints:g.trim()?points(g):null,divisionPoints:d.trim()?points(d):null,powerStagePoints:p.trim()?powerPoints(p):null});
      await openSeason(current);notify('Saved rally points for '+eid)}catch(ex){notify(ex.message,true)}
}
async function saveRallies(){try{const ids=[...$('rallies').querySelectorAll('[data-eid]')].filter(e=>e.querySelector('.evcheck').checked).map(e=>e.dataset.eid);
 if(ids.length>100)throw Error('Maximum 100 rallies');await api('/api/admin/seasons/'+encodeURIComponent(current)+'/rallies','POST',{eventIds:ids});await openSeason(current);notify('Calendar saved')}catch(e){notify(e.message,true)}}
function renderGroups(){for(const [kind,container] of [['division','divisions'],['team','teams']]){
 const group=kind==='division'?detail.divisions:detail.teams;
 $(container).innerHTML=group.map(g=>`<div class="hrow"><span>${safe(g.name)} ${kind==='team'?`<small>Limit ${g.capacity}/10</small>`:''}</span><div class="row">${kind==='team'?`<button data-cap="${g.id}">Member limit</button>`:''}<button data-ren="${g.id}">Rename</button><button data-del="${g.id}">Delete</button></div></div>`).join('');
 $(container).querySelectorAll('[data-cap]').forEach(b=>b.onclick=()=>editCapacity(+b.dataset.cap));
 $(container).querySelectorAll('[data-ren]').forEach(b=>b.onclick=()=>editGroup(kind,+b.dataset.ren));
 $(container).querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>delGroup(kind,+b.dataset.del))}}
async function editCapacity(id){const team=detail.teams.find(t=>t.id===id);
 const value=prompt('Maximum team members (1–10)',String(team.capacity));
 if(value===null)return;const capacity=Number(value);
 if(!Number.isInteger(capacity)||capacity<1||capacity>10)return notify('Team limit: a number from 1 to 10',true);
 try{await api('/api/admin/seasons/'+current+'/groups','POST',{action:'capacity',kind:'team',id,capacity});
 await openSeason(current);notify('Team capacity updated')}catch(e){notify(e.message,true)}
}
async function editGroup(kind,id){const group=(kind==='division'?detail.divisions:detail.teams).find(x=>x.id===id);const name=prompt('New name',group.name);if(!name||name===group.name)return;
 try{await api('/api/admin/seasons/'+current+'/groups','POST',{action:'rename',kind,id,name});await openSeason(current);notify('Name updated')}catch(e){notify(e.message,true)}}
async function delGroup(kind,id){if(!confirm('Delete the group? Remove all assignments first.'))return;
 try{await api('/api/admin/seasons/'+current+'/groups','POST',{action:'delete',kind,id});await openSeason(current);notify('Group deleted')}catch(e){notify(e.message,true)}}
async function addGroup(kind){const input=$(kind==='division'?'newDivision':'newTeam');
 let capacity=10;if(kind==='team'){
 const answer=prompt('Maximum drivers in the new team (1–10)','10');if(answer===null)return;
 capacity=Number(answer);if(!Number.isInteger(capacity)||capacity<1||capacity>10)return notify('Team limit: 1–10',true)}
 try{await api('/api/admin/seasons/'+current+'/groups','POST',{action:'add',kind,name:input.value,capacity});
 await openSeason(current);notify('Group added')}catch(e){notify(e.message,true)}}
function options(items,chosen,placeholder){return `<option value="">${placeholder}</option>`+items.map(item=>`<option value="${item.id}" ${item.id===chosen?'selected':''}>${safe(item.name)}</option>`).join('')}
function renderAssignments(){const assigned=new Map(detail.assignments.map(x=>[x.member_id,x]));
 $('assignments').innerHTML=members.length?members.map(m=>{const a=assigned.get(m.id)||{};return `<div class="hrow" data-member="${m.id}"><b style="min-width:120px">${safe(m.nickname)}</b><div class="row"><select class="compact" data-div>${options(detail.divisions,a.division_id,'No division')}</select><select class="compact" data-team>${options(detail.teams,a.team_id,'No team')}</select><button data-save>Assign</button></div></div>`}).join(''):'<p>No one has joined the club yet.</p>';
 $('assignments').querySelectorAll('[data-save]').forEach(b=>b.onclick=()=>assign(b.closest('[data-member]')))}
async function assign(row){const id=+row.dataset.member;const div=row.querySelector('[data-div]').value,team=row.querySelector('[data-team]').value;
 try{await api('/api/admin/seasons/'+current+'/assign','POST',{memberId:id,divisionId:div?+div:null,teamId:team?+team:null});await openSeason(current);notify('Driver assigned')}catch(e){notify(e.message,true)}}
$('loginBtn').onclick=async()=>{try{await api('/api/admin/login','POST',{key:$('key').value});$('key').value='';await refresh()}catch(e){notify(e.message,true)}};
$('key').onkeydown=e=>{if(e.key==='Enter')$('loginBtn').click()};$('newSeason').onclick=defaults;$('saveSeason').onclick=saveSeason;$('closeEditor').onclick=()=>$('editor').classList.add('hide');$('saveRallies').onclick=saveRallies;$('addDivision').onclick=()=>addGroup('division');$('addTeam').onclick=()=>addGroup('team');
refresh().catch(()=>{});
</script></main></body></html>"""


def html():
    return admin_shell(enhance_deletion(tr(PAGE)))


def enhance_deletion(page):
    import json
    page=page.replace('<button data-open="${safe(s.id)}">','<button data-delete-season="${safe(s.id)}">'+tr('Delete')+'</button><button data-open="${safe(s.id)}">')
    needle=" $('seasonList').querySelectorAll('[data-open]')"
    warning=json.dumps(tr('Permanently delete the season, groups and assignments? Type the season ID:'),ensure_ascii=False)
    cascade=json.dumps(tr('Also permanently delete all rallies in this season, including entries and results? Cancel keeps the rallies as standalone events.'),ensure_ascii=False)
    js=" $('seasonList').querySelectorAll('[data-delete-season]').forEach(b=>b.onclick=async()=>{const id=b.dataset.deleteSeason;if(prompt("+warning+",'')!==id)return;try{await api('/api/admin/seasons/'+encodeURIComponent(id)+'/delete','POST',{confirmId:id,deleteRallies:confirm("+cascade+")});$('editor').classList.add('hide');await refresh()}catch(e){notify(e.message,true)}});\n"
    return page.replace(needle,js+needle)
