"""Public results and championship views with accessible division tabs and search."""
from html import escape as e
from datetime import datetime, timezone, timedelta

def _date_plus_two(timestamp):
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=2))).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(timestamp)[:10]

from server import format_ms
from site_theme import shell, FILTER_JS


def _chip(txt,extra=''):
    return '<span class="chip '+extra+'">'+e(str(txt))+'</span>'


def season_list(seasons):
    page=('<section class="hero"><span class="eyebrow">Rally championship / Sezony</span>'
          '<h1>Wyniki i klasyfikacje</h1>'
          '<p>Generalki, dywizje, teamy i punkty za każdą rundę. Wybierz sezon i śledź wyniki.</p>'
          '<div class="stats"><div class="stat"><strong>'+str(len(seasons))+'</strong><span>Sezonów</span></div>'
          '<div class="stat"><strong>'+str(sum(s['rallyCount'] for s in seasons))+'</strong><span>Rajdów w kalendarzu</span></div></div></section>')
    page+='<div class="card-head"><div><span class="section-kicker">Historia sezonów</span><h2>Sezony klubu</h2></div></div><div class="grid-cards">'
    for s in seasons:
        page+=('<article class="rally-card">'+_chip('Sezon')+'<h2><a href="/season/'+e(s['id'],quote=True)+'">'+e(s['name'])+'</a></h2>'
               '<p>'+e(_date_plus_two(s['opensAt']))+' — '+e(_date_plus_two(s['closesAt']))+'</p>'
               '<div class="rally-foot"><small>'+str(s['rallyCount'])+' rajdów</small>'
               '<a class="btn-link" href="/season/'+e(s['id'],quote=True)+'">Tabela wyników →</a></div></article>')
    page+='</div>'
    if not seasons:page+='<div class="empty">Organizator nie dodał jeszcze sezonów.</div>'
    return shell('ACR Rally Club — Wyniki i klasyfikacje',page,active='seasons')


def _ranking(rows,division=False):
    if not rows:
        return '<div class="empty">Brak sklasyfikowanych kierowców.</div>'
    out='<div class="table-scroll"><table><thead><tr><th>Poz.</th><th>Kierowca</th><th>Rajdy META</th><th>Generalka</th><th>Dywizje</th><th>Power Stage</th><th>Punkty</th></tr></thead><tbody>'
    for rank,r in enumerate(rows,1):
        points=r['division'] if division else r['total']
        out+=('<tr data-driver="'+e(r['nickname'],quote=True)+'"><td class="rank-col'+(' podium' if rank<=3 else '')+'">'+str(rank)+'</td>'
              '<td><strong>'+e(r['nickname'])+'</strong></td><td>'+str(r['finishes'])+'</td>'
              '<td>'+str(r['general'])+'</td><td>'+str(r['division'])+'</td><td>'+str(r.get('powerStage',0))+'</td>'
              '<td class="points-strong">'+str(points)+'</td></tr>')
    return out+'</tbody></table></div>'


def season_detail(data):
    s=data['season']
    rallies=data['rallies']; divs=data['divisions']; drivers=data['drivers']
    page=('<a class="backlink" href="/seasons">← Wszystkie sezony</a>'
          '<section class="hero"><span class="eyebrow">ACR Rally Club / Klasyfikacje</span>'
          '<h1>'+e(s['name'])+'</h1><p>Wyniki sezonu, dywizje i punktacja drużynowa.</p>'
          '<div class="stats"><div class="stat"><strong>'+str(len(rallies))+'</strong><span>Rund</span></div>'
          '<div class="stat"><strong>'+str(len(drivers))+'</strong><span>Kierowców</span></div>'
          '<div class="stat"><strong>'+str(len(divs))+'</strong><span>Dywizji</span></div>'
          '<div class="stat"><strong>'+str(len(data['teams']))+'</strong><span>Teamów</span></div></div></section>')
    page+='<section class="card"><div class="card-head"><div><span class="section-kicker">Aktualna klasyfikacja</span><h2>Wyniki kierowców</h2></div>'+_chip('Punkty zatwierdzane po zamknięciu rundy')+'</div>'
    page+='<div class="toolbar"><label for="driver-search">Szukaj kierowcy</label><input id="driver-search" type="search" placeholder="Szukaj kierowcy…" autocomplete="off"></div>'
    tabs=[('all','Klasyfikacja generalna')]+[('div-'+str(d['id']),d['name']) for d in divs]
    page+='<div class="tabs" role="tablist" aria-label="Wybierz dywizję">'
    for n,(ident,title) in enumerate(tabs):
        page+='<button type="button" class="tab" role="tab" data-target-panel="'+e(ident,quote=True)+'" aria-selected="'+('true' if n==0 else 'false')+'">'+e(title)+'</button>'
    page+='</div>'
    page+='<div id="all" class="classification-panel" role="tabpanel">'+_ranking(drivers)+'</div>'
    for d in divs:
        page+='<div id="div-'+str(d['id'])+'" role="tabpanel" class="classification-panel" hidden>'+_ranking(d['drivers'],True)+'</div>'
    page+='</section>'
    page+='<section class="card"><div class="card-head"><div><span class="section-kicker">Rywalizacja zespołowa</span><h2>Klasyfikacja teamów</h2></div></div>'
    mode={'combined':'Suma punktów generalnych, dywizyjnych i Power Stage','general':'Punkty generalne i Power Stage','division':'Tylko punkty dywizyjne'}.get(s['teamMode'],'Punkty')
    page+='<p class="muted">'+e(mode)+'</p><div class="table-scroll"><table><thead><tr><th>Poz.</th><th>Team</th><th>Skład</th><th>Punkty</th></tr></thead><tbody>'
    for n,t in enumerate(data['teams'],1):
        page+=('<tr><td class="rank-col">'+str(n)+'</td><td><strong>'+e(t['name'])+'</strong></td><td>'+str(t['members'])+'/'+str(t['capacity'])+'</td>'
               '<td class="points-strong">'+str(t['points'])+'</td></tr>')
    page+='</tbody></table></div></section>'
    page+='<section class="card"><div class="card-head"><div><span class="section-kicker">Kalendarz wyników</span><h2>Rundy i punkty</h2></div></div>'
    page+='<p class="muted">Punkty są zatwierdzane po zakończeniu terminu rajdu; przedtem pozycje są prowizoryczne.</p>'
    for ix,rally in enumerate(rallies,1):
        closed=rally['closed']
        page+='<details class="round"'+(' open' if ix==1 else '')+'><summary><span>R'+f'{ix:02d}'+' · '+e(rally['name'])+'</span>'+_chip('PUNKTY ZATWIERDZONE' if closed else 'PROWIZORYCZNIE','chip-active' if closed else 'chip-upcoming')+'</summary>'
        page+='<p><a href="/rally/'+e(rally['id'],quote=True)+'">Otwórz wyniki OS-ów i rajdu →</a></p>'
        page+='<div class="table-scroll"><table><thead><tr><th>Miejsce</th><th>Kierowca</th><th>Czas</th><th>Pkt. gen.</th><th>Miejsce dywizji</th><th>Pkt. dyw.</th><th>Poz. PS</th><th>Pkt. PS</th></tr></thead><tbody>'
        for entry in rally['results']:
            place='—' if entry['rankDivision'] is None else str(entry['rankDivision'])
            page+=('<tr><td class="rank-col">'+str(entry['rankGeneral'])+'</td><td>'+e(entry['nickname'])+'</td>'
                   '<td class="mono">'+format_ms(entry['totalMs'])+'</td><td>'+str(entry['pointsGeneral'])+'</td><td>'+place+'</td><td>'+str(entry['pointsDivision'])+'</td><td>'+str(entry.get('rankPowerStage') or '—')+'</td><td>'+str(entry.get('pointsPowerStage',0))+'</td></tr>')
        page+='</tbody></table></div>'
        if not rally['results']:page+='<div class="empty">Brak wyników dla tej rundy.</div>'
        page+='</details>'
    if not rallies:page+='<div class="empty">Sezon nie ma jeszcze przypisanych rajdów.</div>'
    page+='</section>'
    return shell('ACR Rally Club — '+s['name'],page,active='seasons',scripts=FILTER_JS)
