"""Auditable additive sanctions; game-official result rows remain immutable."""
import secrets,time
from i18n import tr

def install(store):
    store.db.execute('''CREATE TABLE IF NOT EXISTS admin_time_penalties (
      id TEXT PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id),
      stage_index INTEGER NOT NULL, amount_ms INTEGER NOT NULL, reason TEXT NOT NULL,
      created REAL NOT NULL, voided INTEGER NOT NULL DEFAULT 0)''')
    store.db.execute('CREATE INDEX IF NOT EXISTS idx_admin_penalty_player ON admin_time_penalties(player_id,stage_index)')

def totals(store,event_id):
    rows=store.db.execute('''SELECT a.* FROM admin_time_penalties a JOIN players p ON p.id=a.player_id
      WHERE p.event_id=? AND a.voided=0 ORDER BY a.created,a.id''',(event_id,)).fetchall()
    result={}
    for row in rows:
        key=(row['player_id'],row['stage_index']);item=result.setdefault(key,{'amount':0,'reasons':[]})
        item['amount']+=row['amount_ms'];item['reasons'].append(row['reason'])
    return result

def listing(store,event_id):
    with store.lock:
        _,ev=store.event(event_id)
        players=[dict(r) for r in store.db.execute('SELECT id,nickname,status,stage_index FROM players WHERE event_id=? ORDER BY nickname',(event_id,))]
        records=[dict(r) for r in store.db.execute('''SELECT a.*,p.nickname FROM admin_time_penalties a
          JOIN players p ON p.id=a.player_id WHERE p.event_id=? ORDER BY a.created DESC''',(event_id,))]
        return {'event':ev,'players':players,'penalties':records}

def add(store,data,actor='admin'):
    from server import Fault
    with store.lock:
        store._begin()
        try:
            event_id=data.get('eventId');store.event(event_id)
            player=data.get('playerId');idx=data.get('stageIndex');amount=data.get('amountMs');reason=data.get('reason')
            if type(player) is not int or type(idx) is not int or type(amount) is not int or not 1<=amount<=3600000 or not isinstance(reason,str) or not 1<=len(reason.strip())<=160:
                raise Fault(400,tr('Enter a stage, a positive penalty up to one hour and a reason (160 characters maximum)'))
            p=store.db.execute('SELECT * FROM players WHERE id=? AND event_id=?',(player,event_id)).fetchone()
            if not p or not 0<=idx<p['stage_index'] or not store.db.execute('SELECT 1 FROM provisional WHERE player_id=? AND stage_index=?',(player,idx)).fetchone():
                raise Fault(409,tr('A penalty can be added only to a finished stage of this rally'))
            ident=secrets.token_hex(12)
            store.db.execute('INSERT INTO admin_time_penalties(id,player_id,stage_index,amount_ms,reason,created) VALUES(?,?,?,?,?,?)',(ident,player,idx,amount,reason.strip(),time.time()))
            store.audit(actor,'time_penalty_add',event_id,{'id':ident,'playerId':player,'stageIndex':idx,'amountMs':amount,'reason':reason.strip()})
            store.db.execute('COMMIT');return {'ok':True,'id':ident}
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise

def revoke(store,data,actor='admin'):
    from server import Fault
    with store.lock:
        store._begin()
        try:
            row=store.db.execute('''SELECT a.id,p.event_id FROM admin_time_penalties a JOIN players p ON p.id=a.player_id WHERE a.id=?''',(data.get('id'),)).fetchone()
            if not row or row['event_id']!=data.get('eventId'):raise Fault(404,tr('Penalty not found in this rally'))
            store.db.execute('UPDATE admin_time_penalties SET voided=1 WHERE id=?',(row['id'],))
            store.audit(actor,'time_penalty_revoke',row['event_id'],{'id':row['id']})
            store.db.execute('COMMIT');return {'ok':True}
        except Exception:
            if store.db.in_transaction:store.db.execute('ROLLBACK')
            raise


def enhance(page):
    import json
    labels={k:tr(v) for k,v in {'title':'Administrator time penalties','load':'Load drivers','driver':'Driver','stage':'SS number','seconds':'Penalty in seconds','reason':'Reason','add':'Add penalty','revoke':'Revoke','void':'Revoked','select':'Select a rally','choose':'Select a driver','empty':'No administrator penalties'}.items()}
    block='<details class="card round"><summary>'+labels['title']+'</summary><p>'+tr('Penalties change rally and season standings. Game-official times remain unchanged; additions are shown beneath the time.')+'</p><div class="grid"><label>'+labels['select']+'<select id="apEvent"></select></label><button id="apLoad">'+labels['load']+'</button><label>'+labels['driver']+'<select id="apPlayer"></select></label><label>'+labels['stage']+'<input id="apStage" type="number" min="1" max="40" value="1"></label><label>'+labels['seconds']+'<input id="apSeconds" type="number" min="0.001" max="3600" step="0.001"></label><label>'+labels['reason']+'<input id="apReason" maxlength="160"></label></div><button id="apAdd">'+labels['add']+'</button><p id="apStatus" role="status"></p><div id="apHistory"></div></details>'
    page=page.replace('<div id="workspace" class="hide">','<div id="workspace" class="hide">'+block,1)
    js=r'''
const apLabels=LABELS;
function apEvents(){const current=$('apEvent').value;$('apEvent').innerHTML='<option value="">'+ehtml(apLabels.select)+'</option>'+allEvents.map(e=>elOpt(e.id,e.name,e.id===current)).join('')}
async function apLoad(){try{const id=$('apEvent').value;if(!id)return;const data=await request('/api/admin/time-penalties?eventId='+encodeURIComponent(id));$('apPlayer').innerHTML='<option value="">'+ehtml(apLabels.choose)+'</option>'+data.players.filter(p=>p.stage_index>0).map(p=>elOpt(p.id,p.nickname+' · '+p.stage_index+' SS',false)).join('');$('apHistory').innerHTML=data.penalties.map(p=>'<p>'+ehtml(p.nickname)+' · SS '+(p.stage_index+1)+' · +'+(p.amount_ms/1000).toFixed(3)+' s · '+ehtml(p.reason)+' '+(p.voided?ehtml(apLabels.void):'<button data-ap-revoke="'+ehtml(p.id)+'">'+ehtml(apLabels.revoke)+'</button>')+'</p>').join('')||'<p>'+ehtml(apLabels.empty)+'</p>';$('apStatus').textContent=''}catch(e){$('apStatus').textContent=e.message}}
$('apLoad').onclick=apLoad;
$('apEvent').onchange=apLoad;
$('apAdd').onclick=async()=>{try{const seconds=Number($('apSeconds').value);if(!Number.isFinite(seconds)||seconds<=0)throw Error(apLabels.seconds);await request('/api/admin/time-penalties','POST',{eventId:$('apEvent').value,playerId:Number($('apPlayer').value),stageIndex:Number($('apStage').value)-1,amountMs:Math.round(seconds*1000),reason:$('apReason').value});await apLoad();$('apSeconds').value='';$('apReason').value=''}catch(e){$('apStatus').textContent=e.message}};
$('apHistory').onclick=async e=>{const b=e.target.closest('[data-ap-revoke]');if(!b)return;try{await request('/api/admin/time-penalties/revoke','POST',{eventId:$('apEvent').value,id:b.dataset.apRevoke});await apLoad()}catch(err){$('apStatus').textContent=err.message}};
'''.replace('LABELS',json.dumps(labels,ensure_ascii=False))
    page=page.replace('renderEvents();await loadDiscord();','renderEvents();apEvents();await loadDiscord();')
    return page.replace('refresh();\n</script>',js+'\nrefresh();\n</script>')
