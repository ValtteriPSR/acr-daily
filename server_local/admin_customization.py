"""Additional admin tools; translate static labels before inserting user data."""
import json
from i18n import tr


def enhance(page):
    block='''<section class="card"><h2>'''+tr('Club appearance')+'''</h2><div class="grid">'''
    for ident,label,limit in [('brandTitle','Main title',80),('brandSubtitle','Subtitle',100),('brandTagline','Home page tagline',180),('brandDiscord','Public Discord invite',200)]:
        block+='<div><label for="'+ident+'">'+tr(label)+'</label><input id="'+ident+'" maxlength="'+str(limit)+'"></div>'
    block+='</div><p><label for="brandLogo">'+tr('Logo: PNG, up to 256 KB, at most 2048 × 2048')+'</label><input id="brandLogo" type="file" accept="image/png"><label class="check"><input id="removeLogo" type="checkbox">'+tr('Restore the default logo')+'</label></p><button id="saveBrand">'+tr('Save appearance')+'</button><p id="brandStatus" role="status"></p></section>'
    block+='<details class="card round"><summary>'+tr('Cars and stages catalog')+'</summary><p>'+tr('Edit the JSON catalog below. Keep the existing IDs; use the game’s internal IDs for new content, not display names. Car telemetry must match the car name reported by the game. Back up the JSON before editing. New location formats require a launcher update.')+'</p><label for="catalogEditor">JSON</label><textarea id="catalogEditor" rows="16" style="width:100%;font-family:Consolas,monospace" spellcheck="false"></textarea><div class="row"><button id="catalogExport">'+tr('Download catalog backup')+'</button><button id="catalogSave">'+tr('Save catalog')+'</button></div><p id="catalogStatus" role="status"></p><p>'+tr('Discover an ID: finish a short custom stage in the updated game. The launcher log prints new stage IDs and car IDs found in the save, plus the telemetry car name. Copy the matching IDs into this catalog. Never test or change weekend settings during a club attempt.')+'</p></details>'
    page=page.replace('<div id="workspace" class="hide">','<div id="workspace" class="hide">'+block,1)
    page=page.replace('<select id="penalty"></select></div></div>','<select id="penalty"></select></div><p><label for="allowBreaks">'+tr('Breaks between stages')+'</label><select id="allowBreaks"><option value="true">'+tr('Allow exit at service and resume')+'</option><option value="false">'+tr('Complete in one sitting: do not close the game')+'</option></select></p></div>')
    # Both language variants share these JS expressions and HTML attributes.
    page=page.replace('<button class="danger" data-delete="${ehtml(ev.id)}" ${ev.participantCount?\'disabled title="The rally has participants"\':\'\'}>', '<button class="danger" data-delete="${ehtml(ev.id)}">')
    page=page.replace('<button class="danger" data-delete="${ehtml(ev.id)}" ${ev.participantCount?\'disabled title="Rajd ma uczestników"\':\'\'}>', '<button class="danger" data-delete="${ehtml(ev.id)}">')
    # Remove the restriction irrespective of the translated title.
    import re
    page=re.sub(r'(<button class="danger" data-delete="\$\{ehtml\(ev.id\)\}") \$\{ev.participantCount\?.*?:\'\'\}',r'\1',page)
    page=page.replace(" editing=ev?.id||null;applyCatalog();", " editing=ev?.id||null;applyCatalog();$('allowBreaks').value=String(ev?.allowBreaks??true);")
    page=page.replace("const raw = {schemaVersion:1,", "const raw = {schemaVersion:1,launcherProtocol:'0.2.4',allowBreaks:$('allowBreaks').value==='true',")
    start=page.index('async function removeEvent(id)');end=page.index("$('loginBtn').onclick",start)
    warning=json.dumps(tr('Permanently delete this rally, all entries and results? Type the rally ID to confirm:'),ensure_ascii=False)
    page=page[:start]+"async function removeEvent(id){if(prompt("+warning+",'')!==id)return;try{await request('/api/admin/events/'+encodeURIComponent(id)+'/delete','POST',{confirmId:id});await refresh();$('editor').classList.add('hide')}catch(ex){alert(ex.message)}}\n"+page[end:]
    page=page.replace('renderEvents();await loadDiscord();','renderEvents();await loadDiscord();await loadBrand();')
    js=r'''
async function loadBrand(){const b=await request('/api/admin/branding');for(const [id,key] of Object.entries({brandTitle:'title',brandSubtitle:'subtitle',brandTagline:'tagline',brandDiscord:'discordInvite'}))$(id).value=b[key]||'';$('catalogEditor').value=JSON.stringify({cars:catalog.cars,stages:catalog.stages},null,2);}
$('saveBrand').onclick=async()=>{try{const b={title:$('brandTitle').value,subtitle:$('brandSubtitle').value,tagline:$('brandTagline').value,discordInvite:$('brandDiscord').value,removeLogo:$('removeLogo').checked};const f=$('brandLogo').files[0];if(f){if(f.size>262144)throw Error('PNG: maximum 256 KB');b.logo=await new Promise((ok,bad)=>{const r=new FileReader();r.onload=()=>ok(r.result);r.onerror=bad;r.readAsDataURL(f)})}await request('/api/admin/branding','POST',b);location.reload()}catch(e){$('brandStatus').textContent=e.message}};
$('catalogSave').onclick=async()=>{try{await request('/api/admin/catalog','POST',JSON.parse($('catalogEditor').value));await refresh();$('catalogStatus').textContent=CATALOG_SAVED;}catch(e){$('catalogStatus').textContent=e.message}};
$('catalogExport').onclick=()=>{const b=new Blob([$('catalogEditor').value],{type:'application/json'}),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download='acr-catalog-backup.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
'''.replace('CATALOG_SAVED',json.dumps(tr('Catalog saved. New launchers use this catalog automatically.'),ensure_ascii=False))
    page=page.replace('refresh();\n</script>',js+'\nrefresh();\n</script>')
    return page
