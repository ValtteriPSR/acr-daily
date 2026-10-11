"""Unified presentation layer for local ACR Rally Club web pages. No JS frameworks."""
from i18n import tr
from html import escape
from club_settings import brand_html, invite_html

CSS = r"""
:root{color-scheme:dark;--bg:#141d30;--surface:#111827;--surface2:#19243a;--line:#343b48;--text:#f2f5f8;--muted:#a4afbd;--accent:#ed4703;--accent2:#ed4703;--cyan:#87e3de;--green:#7be0b2;--radius:0px}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0!important;color:var(--text)!important;font:15px/1.6 'Segoe UI',Inter,system-ui,sans-serif!important;background:var(--bg)!important;min-height:100vh}
body::before{content:'';position:fixed;inset:0;pointer-events:none;opacity:.05;z-index:0;background:repeating-linear-gradient(125deg,transparent 0 18px,#fff 19px,transparent 20px 36px)}
a{color:#ed4703;text-decoration:none}a:hover{color:#fff;text-decoration:none}a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid var(--cyan);outline-offset:3px}
p,small{color:var(--muted)}p{margin-top:8px}h1,h2,h3{color:var(--text);line-height:1.2}h1{letter-spacing:-1.2px;font-size:clamp(30px,4vw,52px);font-weight:850}h2{font-size:clamp(20px,2.4vw,26px);letter-spacing:-.4px}h3{font-size:17px}
main{max-width:1280px!important;margin:30px auto 0!important;padding:0 24px 65px!important;position:relative;z-index:1}
.sitebar{position:relative;z-index:2;background:#11151df2;border-bottom:1px solid #343a45}
.sitebar-in{max-width:1280px;margin:auto;min-height:76px;padding:0 24px;display:flex;align-items:center;justify-content:space-between;gap:22px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:13px;font-weight:900;letter-spacing:.02em;color:white!important;font-size:16px;white-space:nowrap}
.brand-symbol{width:43px;height:43px;display:grid;place-items:center;background:#ed4703;font:900 22px/1 system-ui;color:white}
.brand-sub{display:block;text-transform:uppercase;font-size:10px;letter-spacing:.22em;color:var(--muted);font-weight:700;margin-top:-4px}
.site-nav{display:flex;align-items:center;gap:4px;flex-wrap:wrap}.site-nav a{display:inline-flex;gap:8px;align-items:center;padding:10px 13px;border-radius:7px;color:#c7cdd7;font-size:13px;font-weight:750;text-transform:uppercase;letter-spacing:.05em}.site-nav a:hover,.site-nav a[aria-current='page']{background:#242a35;color:#fff}
.site-nav .nav-admin{border:1px solid #525768;margin-left:9px}
main>header:not(.sitebar),.hero{border:1px solid #303845;background:linear-gradient(120deg,#111827 0%,#0f1725 70%);border-radius:var(--radius);padding:clamp(26px,4vw,44px)!important;margin:25px 0!important;position:relative;overflow:hidden;display:block}
.hero::before,main>header:not(.sitebar)::before{content:'';position:absolute;right:-160px;top:-110px;height:350px;width:460px;transform:rotate(-24deg);background:linear-gradient(90deg,transparent,#ec57540a 50%,#ec57541a 51%,transparent 52%,transparent 58%,#ec575414 59%,transparent 60%);pointer-events:none}
.hero h1,main>header h1{margin:6px 0 12px}.hero p{font-size:16px;max-width:700px}.eyebrow{color:var(--accent2);font-size:12px;letter-spacing:.23em;text-transform:uppercase;font-weight:850}
.hero-inline{display:flex;gap:18px;justify-content:space-between;align-items:center;flex-wrap:wrap}.hero-inline h1{font-size:clamp(31px,4vw,46px)}
.stats{display:flex;gap:26px;flex-wrap:wrap;margin-top:22px}.stat{padding-right:30px;border-right:1px solid var(--line)}.stat:last-child{border:0}.stat strong{display:block;font-size:22px;color:var(--text);font-weight:850}.stat span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.12em;font-weight:750}
.card,.pane,.rally-card,.feature-card{background:var(--surface)!important;border:1px solid var(--line)!important;border-radius:var(--radius)!important;padding:clamp(18px,2.4vw,27px)!important;margin:16px 0!important;box-shadow:0 8px 25px #00000018}
.card h2,.pane h3{margin-top:0}.card-head{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:17px}
.section-kicker{display:block;color:var(--accent2);text-transform:uppercase;font-size:11px;letter-spacing:.14em;font-weight:850;margin-bottom:5px}
.grid-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:14px}.rally-card{margin:0!important;display:flex;flex-direction:column;min-height:205px}.rally-card h2{margin:16px 0 10px;font-size:23px}.rally-card .rally-foot{margin-top:auto;border-top:1px solid var(--line);padding-top:15px;display:flex;align-items:center;justify-content:space-between}.rally-card:hover{border-color:#d06b66!important;transform:translateY(-1px);transition:.2s}
.chip,.pill,.status-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px!important;border-radius:4px!important;background:#303642!important;color:#dce3ec;font-size:11px;text-transform:uppercase;letter-spacing:.08em;font-weight:800;line-height:1.5}
.chip-active,.status-done{background:#15332d!important;color:var(--green)!important}.chip-upcoming{background:#253449!important;color:#b3daff!important}.chip-ended,.status-dnf{background:#4a2329!important;color:#ffa1a1!important}
.table-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:9px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:13px 16px;text-align:left;border-bottom:1px solid #343c49!important;vertical-align:middle}th{background:#222934;color:#bbc5d3!important;font-size:11px;letter-spacing:.1em;text-transform:uppercase;font-weight:850;white-space:nowrap}tbody tr:hover{background:#202834}tbody tr:last-child td{border-bottom:0!important}.rank-col{width:60px;font-weight:900;color:#9facbd}.podium{color:#fedc9a}.points-strong{font-weight:900;font-size:17px;color:var(--text)}.table-meta{font-size:12px;color:#9ba6b5}
.mono,.number,td[data-time]{font-variant-numeric:tabular-nums;font-family:'Cascadia Mono',Consolas,'Segoe UI',monospace;white-space:nowrap}.good{color:var(--green)!important}.bad{color:#f59898!important}.muted{color:var(--muted)!important}
.toolbar{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin:18px 0}.toolbar input,.toolbar select{flex:1 1 220px;min-width:130px;max-width:340px}
input,select,textarea{background:#0e141c!important;border:1px solid #535d6e!important;border-radius:7px!important;color:var(--text)!important;font:inherit;padding:10px 12px;min-height:42px}input::placeholder{color:#9ba5b4}label{color:#c4cdd7;font-size:13px;font-weight:750}
button,.btn-link{background:#293746;color:#ecf3f7;border:1px solid #4f5b6b;border-radius:7px;padding:10px 16px;font:inherit;cursor:pointer;display:inline-flex;align-items:center;gap:8px;justify-content:center;font-size:13px;font-weight:800;transition:background .16s}
button:hover,.btn-link:hover{background:#354554;color:#fff}button.primary,button.run,.btn-primary{background:#ed4703!important;color:#101522!important;border:1px solid #ed4703!important;font-weight:900!important;box-shadow:0 8px 19px #e94d4320}button.primary:hover,button.run:hover,.btn-primary:hover{filter:brightness(1.13)}button:disabled{opacity:.4;cursor:not-allowed}
button.tab{border-radius:7px;background:transparent;border:1px solid #3c4654;font-size:12px;padding:10px 14px;white-space:nowrap}button.tab[aria-selected=true]{background:#ed4703;border-color:#ed4703;color:#101522}
.tabs{display:flex;gap:8px;flex-wrap:wrap;padding-bottom:16px}.classification-panel[hidden]{display:none!important}
.stage-schedule{max-height:380px}.stage-schedule th{position:sticky;top:0;z-index:1}.stage-schedule td,.stage-schedule th{padding:9px 11px}.stage-schedule th{letter-spacing:.02em}.stage-schedule td:first-child{min-width:145px}.stage-number{display:block;color:var(--accent2);font-size:11px;font-weight:800}.stage-schedule small{display:block;font-size:11px}.service-cell{color:var(--green);text-align:center}.rally-side,.split>.card{min-width:0}.conditions-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px;margin:0}.conditions-grid dt{color:var(--muted);font-size:12px}.conditions-grid dd{margin:1px 0 0;color:var(--text);font-size:13px;font-weight:750}.rally-conditions h2{margin-bottom:15px}
.split{min-width:0;align-items:start;display:grid;grid-template-columns:1.2fr .8fr;gap:16px}.rally-meta{color:#b5c0cd}.rally-meta strong{color:#f1f5f8}.empty{border:1px dashed #4a5262;border-radius:10px;padding:26px;color:var(--muted);text-align:center}.backlink{background:#111827;margin:20px 0;display:inline-flex;align-items:center;gap:10px}
details.round{border-top:1px solid var(--line);padding:12px 0}details.round summary{display:flex;justify-content:space-between;align-items:center;cursor:pointer;gap:15px;list-style:none;font-weight:750}details.round summary::-webkit-details-marker{display:none}details.round summary::after{content:'+';font-size:24px;color:var(--accent2)}details.round[open] summary::after{content:'−'}details.round .table-scroll{margin-top:16px}
footer,.site-footer{color:#8995a5;margin:40px 0 0;padding:25px 0 10px;border-top:1px solid #353d4a;font-size:12px}footer a{color:#b4c2ce}
.hide{display:none!important}.hrow{border-top:1px solid #343e49}.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
body.acr-admin main{max-width:1280px!important}body.acr-admin main>header{display:flex!important;align-items:center;justify-content:space-between;flex-wrap:wrap}body.acr-admin main>header::before{display:none}body.acr-admin .pane{background:#10161f!important}body.acr-admin #notice{border-radius:7px}
@media(max-width:760px){.sitebar-in{padding:12px 16px}.site-nav{width:100%;overflow:auto;flex-wrap:nowrap}.site-nav a{font-size:11px;padding:8px 9px}.brand{font-size:14px}main{margin:10px auto!important;padding:0 13px 50px!important}.hero{padding:25px 20px!important}.stat{min-width:90px;padding-right:12px}.stats{gap:14px}.split,.grid{grid-template-columns:1fr!important}.card,.pane{padding:17px!important}td,th{padding:11px 12px}.site-footer{line-height:1.7}}
*{border-radius:0!important}.brand-logo{object-fit:contain;background:transparent;flex-shrink:0}.brand{white-space:normal;min-width:0}.brand>span{overflow-wrap:anywhere}.brand-sub{overflow-wrap:anywhere;letter-spacing:.12em}.discord-invite{border:1px solid #626e85;margin-left:auto}.archive{margin-top:24px}.site-nav{max-width:100%}.site-nav a{flex-shrink:0}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
"""

# Only search the DOM that belongs to a result panel. User data are text nodes,
# never interpolated into JS. A non-JS browser sees all standings.
FILTER_JS = r"""
<script>
(function(){
  const search = document.getElementById('driver-search');
  const tabs = Array.from(document.querySelectorAll('[data-target-panel]'));
  const panels = Array.from(document.querySelectorAll('.classification-panel'));
  function apply(){
    const text = (search && search.value || '').trim().toLocaleLowerCase(document.documentElement.lang);
    document.querySelectorAll('tr[data-driver]').forEach(row=>{
      row.hidden = !!text && !row.dataset.driver.toLocaleLowerCase(document.documentElement.lang).includes(text);
    });
  }
  tabs.forEach(btn=>btn.addEventListener('click',()=>{
    tabs.forEach(t=>t.setAttribute('aria-selected',t===btn?'true':'false'));
    panels.forEach(p=>p.hidden=(p.id!==btn.dataset.targetPanel));
    apply();
  }));
  if (search) search.addEventListener('input',apply);
})();
</script>
"""

RALLY_FILTER_JS = r"""<script>
(function(){const input=document.getElementById('driver-search');if(!input)return;
input.addEventListener('input',()=>{const val=input.value.toLocaleLowerCase(document.documentElement.lang);
document.querySelectorAll('tr[data-driver]').forEach(tr=>tr.hidden=!tr.dataset.driver.toLocaleLowerCase(document.documentElement.lang).includes(val))})})();
</script>"""

def shell(title, content, *, active='rallies', footer=True, scripts=''):
    nav = [('rallies','/',tr('Rallies')),('seasons','/seasons',tr('Results and standings')),('club','/club',tr('My profile')),('launcher','/launcher','Launcher'),('guide','/guide',tr('Getting started'))]
    links = ''.join('<a href="'+href+'"'+(' aria-current="page"' if active==ident else '')+'>'+escape(label)+'</a>' for ident,href,label in nav)
    heading = ('<!doctype html><html lang="pl"><head><meta charset="utf-8">'
               '<meta name="viewport" content="width=device-width,initial-scale=1">'
               '<title>'+escape(title)+'</title><style>'+CSS+'</style></head><body><div class="sitebar"><div class="sitebar-in">'+brand_html()
               +'<nav class="site-nav" aria-label="'+escape(tr('Main navigation'))+'">'+links+invite_html()+'</nav></div></div><main id="main">')
    tail=(tr('<footer class="site-footer">ACR Rally Club · Results subject to verification · DNF = 0 points</footer>') if footer else '')
    from public_security import DOWNLOAD_URL, launcher_release_page
    download=launcher_release_page(DOWNLOAD_URL or 'https://github.com/ValtteriPSR/acr-daily/releases/latest')
    document=heading+content+tail+'</main>'+tr(scripts)+'</body></html>'
    return document.replace('href="/download"','href="'+escape(download,quote=True)+'"')


def admin_shell(page, active='admin'):
    """Inject uniform top navigation and theme, preserving all V5 admin forms and JS."""
    links = (tr('<a href="/">Rallies</a><a href="/seasons">Results and standings</a><a href="/club">My profile</a><a href="/guide">Guide</a><a class="nav-admin" href="/admin">Rally administration</a><a class="nav-admin" href="/admin/seasons">Season administration</a>'))
    bar = ('<div class="sitebar"><div class="sitebar-in">'+brand_html(True)+'<nav class="site-nav" aria-label="'+escape(tr('Main navigation'))+'">'+links+invite_html()+'</nav></div></div>')
    return page.replace('</head>', '<style>'+CSS+'</style></head>', 1).replace(
        '<body>', '<body class="acr-admin">'+bar, 1)
