"""Public results and championship views with accessible division tabs and search."""
from i18n import tr
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
    page=(tr('<section class="hero"><span class="eyebrow">Rally championship / Seasons</span><h1>Results and standings</h1><p>Overall standings, divisions, teams and points for every round. Choose a season and follow the results.</p><div class="stats"><div class="stat"><strong>')+str(len(seasons))+tr('</strong><span>Seasons</span></div><div class="stat"><strong>')+str(sum(s['rallyCount'] for s in seasons))+tr('</strong><span>Rallies in the calendar</span></div></div></section>'))
    page+=tr('<div class="card-head"><div><span class="section-kicker">Season history</span><h2>Club seasons</h2></div></div><div class="grid-cards">')
    archived=[]
    now=datetime.now(timezone.utc).timestamp()
    for s in seasons:
        card=('<article class="rally-card">'+_chip(tr('Season'))+'<h2><a href="/season/'+e(s['id'],quote=True)+'">'+e(s['name'])+'</a></h2>'
               '<p>'+e(_date_plus_two(s['opensAt']))+' — '+e(_date_plus_two(s['closesAt']))+'</p>'
               '<div class="rally-foot"><small>'+str(s['rallyCount'])+tr(' rallies</small><a class="btn-link" href="/season/')+e(s['id'],quote=True)+tr('">View standings →</a></div></article>'))
        if datetime.fromisoformat(s['closesAt'].replace('Z','+00:00')).timestamp()<now: archived.append(card)
        else: page+=card
    page+='</div>'
    if archived: page+='<details class="round archive"><summary>'+e(tr('Past seasons'))+' · '+str(len(archived))+'</summary><div class="grid-cards">'+''.join(archived)+'</div></details>'
    if not seasons:page+=tr('<div class="empty">The organizer has not added any seasons yet.</div>')
    return shell(tr('ACR Rally Club — Results and standings'),page,active='seasons')


def _ranking(rows,division=False):
    if not rows:
        return tr('<div class="empty">No classified drivers yet.</div>')
    out=tr('<div class="table-scroll"><table><thead><tr><th>Pos.</th><th>Driver</th><th>Rallies finished</th><th>Overall</th><th>Divisions</th><th>Power Stage</th><th>Points</th></tr></thead><tbody>')
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
    page=(tr('<a class="backlink" href="/seasons">← All seasons</a><section class="hero"><span class="eyebrow">ACR Rally Club / Standings</span><h1>')+e(s['name'])+tr('</h1><p>Season results, divisions and team scoring.</p><div class="stats"><div class="stat"><strong>')+str(len(rallies))+tr('</strong><span>Rounds</span></div><div class="stat"><strong>')+str(len(drivers))+tr('</strong><span>Drivers</span></div><div class="stat"><strong>')+str(len(divs))+tr('</strong><span>Divisions</span></div><div class="stat"><strong>')+str(len(data['teams']))+tr('</strong><span>Teams</span></div></div></section>'))
    page+=tr('<section class="card"><div class="card-head"><div><span class="section-kicker">Current standings</span><h2>Driver standings</h2></div>')+_chip(tr('Points finalized after the round closes'))+'</div>'
    page+=tr('<div class="toolbar"><label for="driver-search">Search drivers</label><input id="driver-search" type="search" placeholder="Search drivers…" autocomplete="off"></div>')
    tabs=[('all',tr('Overall standings'))]+[('div-'+str(d['id']),d['name']) for d in divs]
    page+=tr('<div class="tabs" role="tablist" aria-label="Choose a division">')
    for n,(ident,title) in enumerate(tabs):
        page+='<button type="button" class="tab" role="tab" data-target-panel="'+e(ident,quote=True)+'" aria-selected="'+('true' if n==0 else 'false')+'">'+e(title)+'</button>'
    page+='</div>'
    page+='<div id="all" class="classification-panel" role="tabpanel">'+_ranking(drivers)+'</div>'
    for d in divs:
        page+='<div id="div-'+str(d['id'])+'" role="tabpanel" class="classification-panel" hidden>'+_ranking(d['drivers'],True)+'</div>'
    page+='</section>'
    page+=tr('<section class="card"><div class="card-head"><div><span class="section-kicker">Team competition</span><h2>Team standings</h2></div></div>')
    mode={'combined':tr('Sum of overall, division and Power Stage points'),'general':tr('Overall and Power Stage points'),'division':tr('Division points only')}.get(s['teamMode'],tr('Points'))
    page+='<p class="muted">'+e(mode)+tr('</p><div class="table-scroll"><table><thead><tr><th>Pos.</th><th>Team</th><th>Roster</th><th>Points</th></tr></thead><tbody>')
    for n,t in enumerate(data['teams'],1):
        page+=('<tr><td class="rank-col">'+str(n)+'</td><td><strong>'+e(t['name'])+'</strong></td><td>'+str(t['members'])+'/'+str(t['capacity'])+'</td>'
               '<td class="points-strong">'+str(t['points'])+'</td></tr>')
    page+='</tbody></table></div></section>'
    page+=tr('<section class="card"><div class="card-head"><div><span class="section-kicker">Results calendar</span><h2>Rounds and points</h2></div></div>')
    page+=tr('<p class="muted">Points are finalized after the rally closes; positions are provisional until then.</p>')
    for ix,rally in enumerate(rallies,1):
        closed=rally['closed']
        page+='<details class="round"'+''+'><summary><span>R'+f'{ix:02d}'+' · '+e(rally['name'])+'</span>'+_chip(tr('POINTS FINALIZED') if closed else tr('PROVISIONAL'),'chip-active' if closed else 'chip-upcoming')+'</summary>'
        page+='<p><a href="/rally/'+e(rally['id'],quote=True)+tr('">Open stage and rally results →</a></p>')
        page+=tr('<div class="table-scroll"><table><thead><tr><th>Position</th><th>Driver</th><th>Time</th><th>Overall pts.</th><th>Division position</th><th>Division pts.</th><th>PS position</th><th>PS pts.</th></tr></thead><tbody>')
        for entry in rally['results']:
            place='—' if entry['rankDivision'] is None else str(entry['rankDivision'])
            page+=('<tr><td class="rank-col">'+str(entry['rankGeneral'])+'</td><td>'+e(entry['nickname'])+'</td>'
                   '<td class="mono">'+format_ms(entry['totalMs'])+'</td><td>'+str(entry['pointsGeneral'])+'</td><td>'+place+'</td><td>'+str(entry['pointsDivision'])+'</td><td>'+str(entry.get('rankPowerStage') or '—')+'</td><td>'+str(entry.get('pointsPowerStage',0))+'</td></tr>')
        page+='</tbody></table></div>'
        if not rally['results']:page+=tr('<div class="empty">No results for this round yet.</div>')
        page+='</details>'
    if not rallies:page+=tr('<div class="empty">No rallies have been assigned to this season yet.</div>')
    page+='</section>'
    return shell('ACR Rally Club — '+s['name'],page,active='seasons',scripts=FILTER_JS)
