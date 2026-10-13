"""Launch tickets stay in an in-page dialog, never in rally URLs."""
import json
from html import escape
from i18n import tr


def section():
    labels = {
        'starting': tr('Preparing the launcher…'),
        'ready': tr('If prompted, select “Open ACR Club Launcher”.'),
        'expired': tr('The ticket has expired. Close this window and click RUN again.'),
        'error': tr('Could not start the launcher. Please try RUN again.'),
    }
    html = ('<dialog id="run-dialog" aria-labelledby="run-title"><h2 id="run-title">' + escape(tr('Starting the rally')) +
            '</h2><p id="run-message" role="status" aria-live="polite"></p><p><a id="run-open" class="run" hidden>' +
            escape(tr('▶ OPEN LAUNCHER')) + '</a></p><p><small>' + escape(tr('Close ACR before RUN. Allow your browser to open the launcher. The ticket expires after 60 seconds.')) +
            '</small></p><button type="button" id="run-close">' + escape(tr('Close')) + '</button></dialog>' +
            '<noscript><p class="recovery-warning">' + escape(tr('Enable JavaScript to open the launcher from this rally page.')) + '</p></noscript>')
    script = '<style>#run-dialog{color:var(--text,#e6edf7);background:#141d30;border:1px solid #ff7038;border-radius:10px;width:min(440px,calc(100vw - 32px));max-height:85vh;overflow:auto;padding:24px}#run-dialog::backdrop{background:#0009}#run-open[hidden]{display:none}#run-open{display:inline-block}</style><script>'
    script += 'const runLabels=' + json.dumps(labels, ensure_ascii=False).replace('<', '\\u003c') + ';'
    script += r'''
(()=>{
 const dialog=document.getElementById('run-dialog');
 if(!dialog)return;
 const message=document.getElementById('run-message'),open=document.getElementById('run-open');
 let busy=false,timer=null,originButton=null;
 document.getElementById('run-close').onclick=()=>dialog.close();
 dialog.addEventListener('close',()=>{if(originButton)originButton.focus();});
 document.addEventListener('submit',async event=>{
   const form=event.target;
   if(!(form instanceof HTMLFormElement)||new URL(form.action).pathname!='/web/run')return;
   event.preventDefault();
   if(busy)return;
   busy=true;originButton=form.querySelector('button[type="submit"]');
   if(originButton)originButton.disabled=true;
   clearTimeout(timer);open.hidden=true;open.removeAttribute('href');message.textContent=runLabels.starting;
   if(!dialog.open)dialog.showModal();
   try{
     const response=await fetch(form.action,{method:'POST',credentials:'same-origin',
       headers:{'Accept':'application/json'},body:new URLSearchParams(new FormData(form))});
     const data=await response.json();
     if(!response.ok)throw new Error(data.error||runLabels.error);
     if(!/^acrclub:\/\/start\?ticket=[A-Za-z0-9_-]{40,128}$/.test(data.protocol))throw new Error(runLabels.error);
     message.textContent=runLabels.ready;open.href=data.protocol;open.hidden=false;
     timer=setTimeout(()=>{open.hidden=true;open.removeAttribute('href');message.textContent=runLabels.expired;},60000);
     if(dialog.open){open.focus();open.click();}
   }catch(error){message.textContent=error.message||runLabels.error;}
   finally{busy=false;if(originButton)originButton.disabled=false;}
 });
})();
</script>'''
    return html, script
