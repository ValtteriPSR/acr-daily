"""Warstwa wyglądu w stylu Project Simracing (projectsimracing.pl). Bez frameworków.

Wszystkie strony publiczne przechodzą przez shell(): ten sam pasek górny co
główna strona ligi (logo, nawigacja do projectsimracing.pl, PL/EN, motyw,
Discord), pod nim pasek serii ACR z nawigacją po klubie i wspólna stopka.

Tokeny kolorów i kroje są skopiowane z assets/css/style.css strony głównej.
Pliki czcionek i logo leżą w server_local/static/ps/ i są serwowane pod
/static/ps/... z tego samego serwera (bez zależności od Google Fonts).
"""
import os
from html import escape

from i18n import tr
from club_settings import branding

# Adres strony głównej ligi — odnośniki w pasku górnym i stopce.
PS_SITE = os.environ.get('ACR_PS_SITE_URL', 'https://projectsimracing.pl').rstrip('/')
PS_DISCORD = 'https://discord.gg/R3Tu68jWwK'
STATIC = '/static/ps/'

FONTS = [('Saira Condensed', 'saira-condensed', (500, 600, 700, 800)),
         ('Barlow', 'barlow', (400, 500, 600)),
         ('IBM Plex Mono', 'plex-mono', (400, 500))]
FONT_CSS = ''.join(
    "@font-face{font-family:'%s';src:url('%s%s-%d.woff2') format('woff2');font-weight:%d;font-style:normal;font-display:swap}"
    % (family, STATIC, stem, weight, weight) for family, stem, weights in FONTS for weight in weights)

CSS = FONT_CSS + r"""
/* ---------- 1. tokeny (jak na projectsimracing.pl) ---------- */
:root{
  --orange:#ED4703;--orange-hi:#FF6A2B;--amber:#E9B949;--amber-ink:#E9B949;--green:#3FBF7F;--red:#E0553B;
  --silver:#AEB6C6;--bronze:#B07B4B;--seria:#C99A3E;
  --bg:#0D1320;--bg-outer:#080C15;--surface:#141D30;--panel:#1A2438;
  --line:rgba(239,233,222,.13);--line-strong:rgba(239,233,222,.26);
  --text:#EFE9DE;--dim:#8C95A8;--dimmer:#626B7C;--on-orange:#FFFFFF;
  --f-disp:'Saira Condensed','Barlow Condensed','Arial Narrow',sans-serif;
  --f-body:'Barlow',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  --f-mono:'IBM Plex Mono',ui-monospace,'SFMono-Regular',Consolas,monospace;
  --shell:1400px;--gutter:clamp(16px,3.4vw,40px);--topbar-h:62px;
  /* zgodność ze starszymi modułami (okno RUN, telemetria) */
  --accent:var(--orange);--accent2:var(--orange);--muted:var(--dim);--cyan:var(--orange);
  color-scheme:dark;
}
:root[data-theme="light"]{
  --bg:#EFE9DE;--bg-outer:#E1D9C9;--surface:#FBF8F2;--panel:#FFFFFF;
  --line:rgba(19,26,46,.16);--line-strong:rgba(19,26,46,.32);
  --text:#131A2E;--dim:#5C6478;--dimmer:#7B8395;--silver:#7E869A;--bronze:#8A5E33;
  --green:#1F8A57;--amber-ink:#93650F;--seria:#8C6516;color-scheme:light;
}

/* ---------- 2. podstawy ---------- */
*,*::before,*::after{box-sizing:border-box;border-radius:0!important}
html{scroll-behavior:smooth;scroll-padding-top:calc(var(--topbar-h) + 60px)}
html,body{overflow-x:clip}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--f-body);font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
img,svg{display:block;max-width:100%}
a{color:var(--orange);text-decoration:none}
a:hover{color:var(--orange-hi)}
:focus-visible{outline:2px solid var(--orange);outline-offset:3px}
h1,h2,h3{font-family:var(--f-disp);text-transform:uppercase;font-weight:800;line-height:.98;letter-spacing:-.004em;color:var(--text);text-wrap:balance;margin:0}
h1{font-size:clamp(34px,5vw,58px);font-style:italic}
h2{font-size:clamp(24px,2.8vw,32px)}
h3{font-size:19px;margin:22px 0 12px}
p{margin:10px 0 0}
p,small{color:var(--dim)}
strong{color:var(--text);font-weight:600}
.shell{width:100%;max-width:var(--shell);margin-inline:auto;padding-inline:var(--gutter)}
.skip{position:absolute;left:12px;top:-60px;z-index:200;background:var(--orange);color:var(--on-orange);padding:10px 16px;font-family:var(--f-disp);text-transform:uppercase;letter-spacing:.06em;transition:top .18s}
.skip:focus{top:12px}
.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}
.hide{display:none!important}

/* ---------- 3. pasek górny Project Simracing ---------- */
.topbar{position:sticky;top:0;z-index:60;background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.topbar__in{display:flex;align-items:center;gap:clamp(14px,2.4vw,34px);height:var(--topbar-h)}
.ps-brand{flex:none;display:block}
.ps-brand img{height:21px;width:auto}
:root[data-theme="light"] .ps-brand img,:root[data-theme="light"] .foot__logo img{filter:invert(1) hue-rotate(180deg) saturate(1.7)}
.nav{display:flex;gap:clamp(14px,1.8vw,26px)}
.nav a{font-family:var(--f-disp);text-transform:uppercase;font-weight:600;font-size:15px;letter-spacing:.06em;color:var(--dim);padding:4px 0;border-bottom:2px solid transparent;transition:.16s}
.nav a:hover,.nav a:focus-visible{color:var(--text);border-bottom-color:var(--orange)}
.nav a.is-on{color:var(--text);border-bottom-color:var(--seria)}
.topbar__tools{margin-left:auto;display:flex;align-items:center;gap:8px}
.language-switch{display:flex!important;gap:0!important;margin:0!important;border:1px solid var(--line)}
.language-switch a{font-family:var(--f-mono)!important;font-size:10.5px!important;font-weight:400!important;letter-spacing:.14em;color:var(--dim)!important;padding:6px 9px!important;border:0!important;background:transparent!important;transition:.16s}
.language-switch a:hover{color:var(--text)!important}
.language-switch a[aria-current=true]{color:var(--text)!important;background:var(--panel)!important}
.icobtn{width:34px;height:32px;display:grid;place-items:center;border:1px solid var(--line);color:var(--dim);background:none;cursor:pointer;padding:0;transition:.16s}
.icobtn:hover{color:var(--text);border-color:var(--line-strong)}
.icobtn svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.icobtn .ico-sun{display:none}
:root[data-theme="light"] .icobtn .ico-sun{display:block}
:root[data-theme="light"] .icobtn .ico-moon{display:none}
.burger{display:none}
.mobnav{display:flex;flex-direction:column;border-top:1px solid var(--line);background:var(--surface)}
.mobnav[hidden]{display:none}
.mobnav a{padding:13px var(--gutter);border-bottom:1px solid var(--line);color:var(--text);font-family:var(--f-disp);text-transform:uppercase;font-weight:600;letter-spacing:.06em}
.mobnav__cat{padding:12px var(--gutter) 6px;font-family:var(--f-mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--dim)}

/* ---------- 4. przyciski (skośne cięcia jak na stronie ligi) ---------- */
.btn,.btn-link,button,.run{--skew:11px;position:relative;display:inline-flex;align-items:center;justify-content:center;gap:8px;font-family:var(--f-disp);text-transform:uppercase;font-weight:700;letter-spacing:.06em;font-size:15px;line-height:1.2;padding:10px 20px;cursor:pointer;border:0;background:none;color:var(--text);transition:background .16s,color .16s;text-decoration:none}
.btn--primary,button.run,button.primary,a.run,.btn-primary,.hero p>.btn-link:first-child,a.btn-link[href='/auth/steam']{background:var(--orange)!important;color:var(--on-orange)!important;padding-right:calc(20px + var(--skew));clip-path:polygon(0 0,100% 0,calc(100% - var(--skew)) 100%,0 100%)}
.btn--primary:hover,button.run:hover,button.primary:hover,a.run:hover,.btn-primary:hover,.hero p>.btn-link:first-child:hover,a.btn-link[href='/auth/steam']:hover{background:var(--orange-hi)!important;color:var(--on-orange)!important}
.btn--sm{font-size:13px;padding:7px 14px;--skew:9px}
.btn--sm.btn--primary{padding-right:calc(14px + var(--skew))}
.btn-link,button:not(.run):not(.primary):not(.icobtn):not(.tab){color:var(--text);padding-left:calc(20px + var(--skew));clip-path:polygon(var(--skew) 0,100% 0,100% 100%,0 100%);background:linear-gradient(var(--line-strong),var(--line-strong)) 0 0/100% 1px no-repeat,linear-gradient(var(--line-strong),var(--line-strong)) 0 100%/100% 1px no-repeat,linear-gradient(var(--line-strong),var(--line-strong)) 100% 0/1px 100% no-repeat}
.btn-link::after,button:not(.run):not(.primary):not(.icobtn):not(.tab)::after{content:"";position:absolute;inset:0;background:var(--line-strong);clip-path:polygon(var(--skew) 0,calc(var(--skew) + 1.5px) 0,1.5px 100%,0 100%);pointer-events:none}
.btn-link:hover,button:not(.run):not(.primary):not(.icobtn):not(.tab):hover{--line-strong:var(--orange);color:var(--orange)}
button:disabled{opacity:.4;cursor:not-allowed}
.discord-invite{font-size:13px!important;padding:7px calc(14px + 9px) 7px 14px!important;--skew:9px}

/* ---------- 5. pasek serii ACR ---------- */
.sitebar{background:var(--surface);border-bottom:1px solid var(--line);position:relative}
.sitebar::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--seria)}
.sitebar-in{display:flex;align-items:center;gap:clamp(14px,2.4vw,30px);min-height:54px;flex-wrap:wrap;padding-block:6px}
.brand{display:flex;align-items:center;gap:11px;color:var(--text)!important;min-width:0}
.brand:hover{color:var(--text)}
.brand-mark{flex:none;width:12px;height:18px;background:var(--seria);clip-path:polygon(30% 0,100% 0,70% 100%,0 100%)}
.brand-logo{width:30px;height:30px;object-fit:contain;flex:none}
.brand-name{font-family:var(--f-disp);font-style:italic;font-weight:800;font-size:21px;line-height:1;text-transform:uppercase;letter-spacing:.01em}
.brand-sub{display:block;font-family:var(--f-mono);font-style:normal;font-weight:400;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--dim);margin-top:4px}
.site-nav{display:flex;align-items:center;gap:2px;margin-left:auto;overflow-x:auto;scrollbar-width:none}
.site-nav::-webkit-scrollbar{display:none}
.site-nav a{flex:none;font-family:var(--f-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);padding:10px 13px;border-bottom:2px solid transparent;transition:.16s;white-space:nowrap}
.site-nav a:hover{color:var(--text)}
.site-nav a[aria-current=page]{color:var(--text);background:var(--panel);border-bottom-color:var(--orange)}
.site-nav a[href='/guide']{color:var(--orange)}
.site-nav .nav-admin{border:1px solid var(--line);margin-left:6px}

/* ---------- 6. treść ---------- */
main{display:block;padding-top:clamp(14px,2.4vw,26px);padding-bottom:clamp(44px,6vw,72px);min-height:60vh}
.backlink{display:inline-flex;align-items:center;gap:8px;font-family:var(--f-mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin:0 0 6px}
.backlink:hover{color:var(--orange)}
.backlink+.hero,div:has(>.backlink)+.hero{padding-top:12px}
.hero,main>header:not(.topbar){position:relative;overflow:hidden;padding:clamp(18px,3vw,36px) 0 clamp(22px,3vw,34px);margin:0 0 clamp(18px,2.6vw,28px);border-bottom:1px solid var(--line)}
.hero::after{content:"";position:absolute;right:-6%;top:0;bottom:0;width:46%;pointer-events:none;opacity:.5;background:repeating-linear-gradient(115deg,transparent 0 22px,color-mix(in srgb,var(--seria) 14%,transparent) 22px 23px);mask-image:linear-gradient(90deg,transparent,#000 60%)}
.hero>*{position:relative;z-index:1}
.eyebrow,.section-kicker{display:block;font-family:var(--f-mono);font-size:11px;font-weight:500;letter-spacing:.16em;text-transform:uppercase;color:var(--orange);margin-bottom:10px}
.hero h1{margin:4px 0 14px}
.hero p{font-size:17px;max-width:72ch}
.hero p:has(.btn-link){display:flex;flex-wrap:wrap;gap:8px;margin-top:22px}
.stats{display:flex;gap:0;flex-wrap:wrap;margin-top:26px;border:1px solid var(--line);width:max-content;max-width:100%;background:var(--surface)}
.stat{padding:12px 22px;border-right:1px solid var(--line);min-width:110px}
.stat:last-child{border-right:0}
.stat strong{display:block;font-family:var(--f-disp);font-weight:800;font-size:30px;line-height:1}
.stat span{display:block;margin-top:6px;font-family:var(--f-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.card,.pane,.feature-card{background:var(--surface);border:1px solid var(--line);padding:clamp(18px,2.4vw,28px);margin:0 0 16px;min-width:0}
.card>h1:first-child,.card>h2:first-child{margin-bottom:12px}
main>h1{font-family:var(--f-mono);font-style:normal;font-weight:500;font-size:11px;letter-spacing:.16em;color:var(--dim);margin:0 0 12px}
.card>h2{margin-bottom:16px}
.card h2+p,.card h2+.muted{margin-top:12px}
.card-head{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;flex-wrap:wrap;margin:0 0 18px}
main>.card-head{margin-top:clamp(28px,4vw,44px)}
.split{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,.75fr);gap:16px;align-items:start}
.rally-side{min-width:0}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.muted{color:var(--dim)!important}
.good{color:var(--green)!important}
.bad{color:var(--red)!important}
.empty{border:1px dashed var(--line-strong);padding:30px 18px;text-align:center;color:var(--dim);margin-top:12px}
.rally-meta{color:var(--dim);margin:6px 0 0}
.rally-meta strong{font-family:var(--f-mono);font-weight:500;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dimmer);margin-right:6px}
main p a:not(.btn-link):not(.run),main li a:not(.btn-link){color:var(--orange);border-bottom:1px solid color-mix(in srgb,var(--orange) 40%,transparent)}
main p a:not(.btn-link):not(.run):hover,main li a:not(.btn-link):hover{border-bottom-color:var(--orange)}
main ol,main ul{color:var(--dim);padding-left:22px}
main li{margin:6px 0}
code{font-family:var(--f-mono);font-size:.9em;background:var(--panel);padding:1px 5px}

/* karty rajdów i sezonów */
.grid-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}
.rally-card{background:var(--surface);border:1px solid var(--line);padding:20px 22px;display:flex;flex-direction:column;min-height:220px;position:relative;transition:background .16s}
.rally-card::before{content:"";position:absolute;left:0;top:0;width:100%;height:3px;background:var(--seria);transform:scaleX(.18);transform-origin:left;transition:transform .25s}
.rally-card:hover{border-color:var(--line-strong)}
.rally-card:hover::before{transform:scaleX(1)}
.rally-card h2{margin:14px 0 6px;font-size:28px;font-style:italic}
.rally-card h2 a{color:var(--text)}
.rally-card h2 a:hover{color:var(--orange)}
.rally-card p{margin:4px 0 0}
.rally-foot{margin-top:auto;padding-top:16px;border-top:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.rally-foot small{font-family:var(--f-mono);font-size:11.5px;letter-spacing:.04em;color:var(--dim)}
.rally-foot .btn-link{font-size:13px;padding:7px 14px 7px 23px;--skew:9px}
.hero-inline{display:flex;gap:12px;justify-content:space-between;align-items:center;flex-wrap:wrap}
.hero-inline .muted{font-family:var(--f-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase}

/* plakietki */
.chip,.pill,.status-pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);padding:3px 8px;font-family:var(--f-mono);font-size:10px;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);white-space:nowrap;line-height:1.5;background:transparent}
.chip-active,.status-done{color:var(--green)!important;border-color:color-mix(in srgb,var(--green) 55%,transparent)!important}
.chip-active::before{content:"";width:7px;height:7px;border-radius:50%!important;background:var(--green);animation:pulse 2.4s infinite}
.chip-upcoming{color:var(--seria)!important;border-color:color-mix(in srgb,var(--seria) 60%,transparent)!important}
.chip-ended{color:var(--dimmer)!important}
.status-dnf{color:var(--red)!important;border-color:color-mix(in srgb,var(--red) 55%,transparent)!important;white-space:normal;text-align:left}
.status-warning{color:var(--amber-ink)!important;border-color:var(--amber-ink)!important}
@keyframes pulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--green) 55%,transparent)}70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}

/* tabele (jak tabela wyników na stronie ligi) */
.table-scroll{overflow-x:auto;border:1px solid var(--line);background:var(--bg)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th{background:var(--surface);text-align:left;padding:11px 12px;border-bottom:1px solid var(--line);white-space:nowrap;font-family:var(--f-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);font-weight:500}
td{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
tbody tr:last-child td{border-bottom:0}
tbody tr:nth-child(even) td{background:color-mix(in srgb,var(--surface) 45%,transparent)}
tbody tr:hover td{background:var(--panel)}
.rank-col{width:58px;text-align:center;font-family:var(--f-disp);font-weight:800;font-size:20px;line-height:1;color:var(--dim)}
tbody tr:nth-child(1) td.rank-col{color:var(--orange);box-shadow:inset 4px 0 0 var(--orange)}
tbody tr:nth-child(2) td.rank-col{color:var(--silver);box-shadow:inset 4px 0 0 var(--silver)}
tbody tr:nth-child(3) td.rank-col{color:var(--bronze);box-shadow:inset 4px 0 0 var(--bronze)}
tbody tr:nth-child(1):has(td.rank-col) td{background:color-mix(in srgb,var(--orange) 8%,var(--bg))}
.points-strong{font-family:var(--f-disp);font-weight:800;font-size:20px}
.mono,.number,td[data-time]{font-family:var(--f-mono);font-variant-numeric:tabular-nums;font-size:13.5px;white-space:nowrap}
td.mono strong{font-weight:500}
.table-meta{font-family:var(--f-mono);font-size:11px;letter-spacing:.06em;color:var(--dim);margin-top:12px}
.admin-penalty-note{display:block;color:var(--amber-ink);font-size:11px;line-height:1.4;margin-top:4px;white-space:normal}
.car-name{color:var(--dim);font-size:14px}

/* harmonogram OS i warunki */
.stage-schedule{max-height:420px}
.stage-schedule th{position:sticky;top:0;z-index:1}
.stage-number{display:block;font-family:var(--f-mono);font-size:10px;letter-spacing:.14em;color:var(--orange)}
.stage-schedule td:first-child strong{font-family:var(--f-disp);text-transform:uppercase;font-weight:700;font-size:17px;letter-spacing:.02em}
.stage-schedule small{display:block;font-size:11px;color:var(--dim)}
.service-cell{color:var(--green);text-align:center}
.conditions-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);margin:16px 0 0}
.conditions-grid>div{background:var(--bg);padding:10px 12px}
.conditions-grid>div:last-child:nth-child(odd){grid-column:1/-1}
.season-rules{font-size:12px;line-height:1.6;color:var(--muted);margin-top:16px;padding-top:12px;border-top:1px solid var(--line);overflow-wrap:anywhere}
.season-rules p{margin:5px 0}
.season-rules strong{font-weight:600;color:var(--text)}
.season-id{font-size:12px;overflow-wrap:anywhere;user-select:all}
.conditions-grid dt{font-family:var(--f-mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.conditions-grid dd{margin:3px 0 0;font-weight:600;font-size:14px;color:var(--text)}

/* rozwijane sekcje */
details.round{border:1px solid var(--line);background:var(--bg);margin:0 0 8px}
details.round summary{display:flex;justify-content:space-between;align-items:center;gap:14px;cursor:pointer;list-style:none;padding:13px 16px;font-family:var(--f-disp);text-transform:uppercase;font-weight:700;font-size:17px;letter-spacing:.03em;color:var(--text)}
details.round summary::-webkit-details-marker{display:none}
details.round summary>span:first-child{flex:1;min-width:0;overflow-wrap:anywhere}
.season-round .round-status{white-space:normal;text-transform:none;letter-spacing:.03em;max-width:75%}
details.round summary::after{content:"+";font-family:var(--f-mono);font-size:20px;color:var(--orange);line-height:1}
details.round[open] summary::after{content:"−"}
details.round[open] summary{border-bottom:1px solid var(--line);background:var(--surface)}
details.round>*:not(summary){margin:14px 16px}
details.round>.table-scroll{margin:0;border:0}
details.round>.grid-cards{margin:14px 16px 16px}
.archive{margin-top:24px}

/* zakładki dywizji = przełącznik serii ze strony wyników */
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 16px}
button.tab{--skew:11px;background:var(--panel);color:var(--dim);font-size:15px;padding:9px calc(16px + var(--skew));clip-path:polygon(var(--skew) 0,100% 0,calc(100% - var(--skew)) 100%,0 100%)}
button.tab:hover{color:var(--text)}
button.tab[aria-selected=true]{background:var(--seria);color:#fff}
.classification-panel[hidden]{display:none!important}

/* formularze */
.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 14px}
label{font-family:var(--f-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
input,select,textarea{font:inherit;font-family:var(--f-body);color:var(--text);background:transparent;border:1px solid var(--line-strong);padding:9px 12px;min-height:40px}
input::placeholder{color:var(--dimmer)}
input:focus-visible,select:focus-visible,textarea:focus-visible{border-color:var(--orange);outline:none}
select option{background:var(--surface);color:var(--text)}
.toolbar input{flex:1 1 220px;max-width:340px}

/* ostrzeżenia */
.recovery-warning{color:var(--text);background:color-mix(in srgb,var(--amber) 10%,transparent);border-left:3px solid var(--amber);padding:12px 14px;margin:0 0 16px}
.notice{border-left:2px solid var(--amber);padding:6px 0 6px 12px;color:var(--dim)}

/* telemetria i okno RUN (moduły z własnymi klasami) */
.nickname-saved{font-size:12px;margin:8px 0}
.trace-progress{display:block;font-size:12px;margin:4px 0;line-height:1.5;font-family:var(--f-body);font-weight:400;text-transform:none;letter-spacing:normal}
.trace-good{color:var(--green)!important}.trace-warn{color:var(--amber-ink)!important}.trace-bad{color:var(--red)!important}
.trace-map,.trace-speed{display:block;width:100%;max-height:520px;border:1px solid var(--line);margin:12px 0;background:var(--bg)}
.trace-content{min-width:0}
#run-dialog{color:var(--text)!important;background:var(--surface)!important;border:1px solid var(--line-strong)!important;border-top:3px solid var(--orange)!important}
#run-dialog::backdrop{background:#000a}

/* ---------- 7. stopka ---------- */
.foot{background:var(--bg);border-top:1px solid var(--line)}
.foot__in{display:flex;align-items:center;gap:20px;flex-wrap:wrap;padding-block:24px 34px}
.foot__logo img{height:18px;width:auto;opacity:.85}
.foot__copy{margin:0 auto 0 0;font-family:var(--f-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.foot__social{display:flex;gap:8px;flex-wrap:wrap}
.foot__social a{border:1px solid var(--line);padding:6px 12px;font-family:var(--f-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);transition:.16s}
.foot__social a:hover{color:var(--text);border-color:var(--orange)}
.foot__note{flex-basis:100%;margin:0;font-family:var(--f-mono);font-size:10.5px;letter-spacing:.08em;color:var(--dimmer)}

/* ---------- 8. panel administratora (zawsze ciemny) ---------- */
body.acr-admin main{max-width:var(--shell);margin-inline:auto;padding-inline:var(--gutter)}
body.acr-admin main>header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
body.acr-admin main>header::after{display:none}
body.acr-admin .pane{background:var(--surface)!important}
body.acr-admin input,body.acr-admin select,body.acr-admin textarea{background:var(--bg)}

/* ---------- 9. responsywność ---------- */
@media (max-width:1100px){.nav{display:none}.burger{display:grid}}
@media (max-width:860px){.split,.grid{grid-template-columns:1fr}}
@media (max-width:720px){
  .season-round>summary{flex-wrap:wrap}
  .season-round>summary>span:first-child{flex-basis:100%}
  .topbar__cta,.discord-invite{display:none!important}
  .topbar__in{gap:10px}
  .topbar__tools{gap:6px}
  .ps-brand img{height:16px}
  .sitebar-in{gap:4px;padding-block:10px 0}
  .site-nav{margin-left:calc(-1 * var(--gutter));margin-right:calc(-1 * var(--gutter));padding-inline:var(--gutter);width:calc(100% + 2 * var(--gutter))}
  .site-nav a{padding:10px 10px}
  .stats{width:100%}
  .stat{flex:1 1 0;min-width:0;padding:10px 12px}
  .stat strong{font-size:24px}
  .conditions-grid{grid-template-columns:1fr}
  td,th{padding:10px 9px}
  .rank-col{width:42px;font-size:18px}
  .rally-card h2{font-size:25px}
  .language-switch a{padding:6px 7px!important}
}
@media (min-width:1560px){body{background:var(--bg-outer)}main.shell,.foot{background:var(--bg)}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
@media print{.topbar,.sitebar,.foot,#run-dialog{display:none}}
"""

# Ustawienie motywu przed pierwszym malowaniem — ten sam klucz co na
# projectsimracing.pl, więc wybór jest pamiętany niezależnie na każdej domenie.
THEME_BOOT = ("<script>(function(){try{var t=localStorage.getItem('ps-theme');"
              "if(!t)t=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';"
              "document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>")

UI_JS = r"""<script>
(function(){
  var root=document.documentElement,btn=document.getElementById('themeBtn');
  if(btn)btn.addEventListener('click',function(){
    var next=root.getAttribute('data-theme')==='light'?'dark':'light';
    root.setAttribute('data-theme',next);try{localStorage.setItem('ps-theme',next)}catch(e){}
  });
  var burger=document.getElementById('burger'),mob=document.getElementById('mobnav');
  if(burger&&mob)burger.addEventListener('click',function(){
    var open=mob.hasAttribute('hidden');
    if(open)mob.removeAttribute('hidden');else mob.setAttribute('hidden','');
    burger.setAttribute('aria-expanded',open?'true':'false');
  });
  var cur=document.querySelector('.site-nav a[aria-current=page]');
  if(cur&&cur.scrollIntoView&&window.innerWidth<720)cur.scrollIntoView({block:'nearest',inline:'center'});
})();
</script>"""

SUN = ('<svg class="ico-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.6"/>'
       '<path d="M12 1.6v3M12 19.4v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1.6 12h3M19.4 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/></svg>')
MOON = '<svg class="ico-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
BURGER = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18"/></svg>'

# Pozycje menu głównej strony ligi (jak w assets/js/config.js → nav).
PS_NAV = [('Links', 'index.html#hub'), ('Results', 'wyniki.html'), ('Calendar', 'kalendarz.html'),
          ('Articles', 'artykuly/'), ('Rules', 'regulamin/'), ('Media', 'index.html#media')]
PS_SOCIAL = [('Discord', PS_DISCORD), ('YouTube', 'https://www.youtube.com/@ProjectSimracingpl'),
             ('Facebook', 'https://www.facebook.com/ProjectSimracing/'),
             ('Patronite', 'https://patronite.pl/projectsimracing')]

# Etykieta "Wyniki" w pasku PS prowadzi prosto do zakładki ACR na stronie wyników.
RESULTS_LINK = 'wyniki.html?champ=acr'


def _ps(href):
    return PS_SITE + '/' + href


def _logo(cls):
    return ('<picture class="' + cls + '"><source srcset="' + STATIC + 'logo.webp" type="image/webp">'
            '<img src="' + STATIC + 'logo.png" width="2500" height="236" alt="Project Simracing"></picture>')


def _club_nav(active):
    return [('rallies', '/', tr('Rallies')), ('seasons', '/seasons', tr('Results and standings')),
            ('club', '/club', tr('My profile')), ('launcher', '/launcher', 'Launcher'),
            ('guide', '/guide', tr('Getting started'))]


def _brand():
    b = branding()
    mark = ('<img class="brand-logo" src="/club-logo" alt="" width="30" height="30">' if b.get('logo')
            else '<i class="brand-mark" aria-hidden="true"></i>')
    return ('<a href="/" class="brand">' + mark + '<span class="brand-name">' + escape(b['title'])
            + '<span class="brand-sub">' + escape(b['subtitle']) + '</span></span></a>')


def _discord():
    link = branding().get('discordInvite') or PS_DISCORD
    return ('<a class="btn btn--primary btn--sm topbar__cta discord-invite" href="' + escape(link, quote=True)
            + '" target="_blank" rel="noopener noreferrer">Discord</a>')


def _topbar(club_links):
    ps_links = ''.join('<a href="' + escape(_ps(RESULTS_LINK if href == 'wyniki.html' else href), quote=True) + '">'
                       + escape(tr(label)) + '</a>' for label, href in PS_NAV[:2])
    # „Klub AC Rally” — ta sama pozycja, którą dodajemy do menu na projectsimracing.pl
    ps_links += '<a href="/" class="is-on" aria-current="true">' + escape(tr('AC Rally Club')) + '</a>'
    ps_links += ''.join('<a href="' + escape(_ps(href), quote=True) + '">' + escape(tr(label)) + '</a>'
                        for label, href in PS_NAV[2:])
    mob = ('<div class="mobnav__cat">' + escape(branding()['title']) + '</div>' + club_links
           + '<div class="mobnav__cat">Project Simracing</div>' + ps_links)
    return ('<a class="skip" href="#main">' + escape(tr('Skip to content')) + '</a>'
            '<header class="topbar" id="topbar"><div class="shell topbar__in">'
            '<a class="ps-brand" href="' + escape(PS_SITE + '/', quote=True) + '" aria-label="Project Simracing">'
            + _logo('ps-logo') + '</a>'
            '<nav class="nav" aria-label="Project Simracing">' + ps_links + '</nav>'
            '<div class="topbar__tools"><!--acr-language-->'
            '<button type="button" class="icobtn" id="themeBtn" aria-label="' + escape(tr('Toggle theme'), quote=True)
            + '" title="' + escape(tr('Toggle theme'), quote=True) + '">' + SUN + MOON + '</button>'
            + _discord() +
            '<button type="button" class="icobtn burger" id="burger" aria-label="Menu" aria-expanded="false" aria-controls="mobnav">'
            + BURGER + '</button></div></div>'
            '<nav class="mobnav" id="mobnav" aria-label="Menu" hidden>' + mob + '</nav></header>')


def _footer():
    social = ''.join('<a href="' + escape(href, quote=True) + '" target="_blank" rel="noopener">' + label + '</a>'
                     for label, href in PS_SOCIAL)
    return ('<footer class="foot"><div class="shell foot__in">'
            '<a class="foot__logo" href="' + escape(PS_SITE + '/', quote=True) + '">' + _logo('') + '</a>'
            '<p class="foot__copy">© 2026 Project Simracing · ' + escape(branding()['title']) + '</p>'
            '<nav class="foot__social" aria-label="Social media">' + social + '</nav>'
            '<p class="foot__note">' + escape(tr('ACR Rally Club · Results subject to verification · DNF = 0 points'))
            + ' · ' + escape(tr('Based on ACR Daily (MIT license)')) + '</p></div></footer>')


def _head(title):
    return ('<!doctype html><html lang="pl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="dark light">'
            '<title>' + escape(title) + '</title>'
            '<link rel="icon" type="image/png" sizes="32x32" href="' + STATIC + 'favicon-32.png">'
            '<link rel="icon" type="image/png" sizes="16x16" href="' + STATIC + 'favicon-16.png">'
            '<link rel="apple-touch-icon" href="' + STATIC + 'apple-touch-icon.png">'
            '<link rel="preload" as="font" type="font/woff2" crossorigin href="' + STATIC + 'saira-condensed-800.woff2">'
            '<link rel="preload" as="font" type="font/woff2" crossorigin href="' + STATIC + 'barlow-400.woff2">'
            + THEME_BOOT + '<style>' + CSS + '</style></head>')


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
    club = _club_nav(active)
    links = ''.join('<a href="' + href + '"' + (' aria-current="page"' if active == ident else '') + '>'
                    + escape(label) + '</a>' for ident, href, label in club)
    mob_links = ''.join('<a href="' + href + '">' + escape(label) + '</a>' for _ident, href, label in club)
    document = (_head(title) + '<body>' + _topbar(mob_links)
                + '<div class="sitebar"><div class="shell sitebar-in">' + _brand()
                + '<nav class="site-nav" aria-label="' + escape(tr('Main navigation')) + '">' + links + '</nav></div></div>'
                + '<main id="main" class="shell">' + content + '</main>'
                + (_footer() if footer else '') + UI_JS + tr(scripts) + '</body></html>')
    from public_security import DOWNLOAD_URL, launcher_release_page
    download = launcher_release_page(DOWNLOAD_URL or 'https://github.com/ValtteriPSR/acr-daily/releases/latest')
    return document.replace('href="/download"', 'href="' + escape(download, quote=True) + '"')


def admin_shell(page, active='admin'):
    """Inject uniform top navigation and theme, preserving all V5 admin forms and JS.

    The administrator panel keeps the dark theme: its own forms use fixed colours.
    """
    links = tr('<a href="/">Rallies</a><a href="/seasons">Results and standings</a><a href="/club">My profile</a>'
               '<a href="/guide">Guide</a><a class="nav-admin" href="/admin">Rally administration</a>'
               '<a class="nav-admin" href="/admin/seasons">Season administration</a>')
    bar = ('<div class="sitebar"><div class="shell sitebar-in">' + _brand()
           + '<nav class="site-nav" aria-label="' + escape(tr('Main navigation')) + '">' + links + '</nav>'
           + '<span class="admin-tools"><!--acr-language--></span></div></div>')
    head = ('<style>' + CSS + '</style>'
            '<link rel="icon" type="image/png" sizes="32x32" href="' + STATIC + 'favicon-32.png">')
    return page.replace('</head>', head + '</head>', 1).replace('<body>', '<body class="acr-admin">' + bar, 1)
