"""Real browser regression checks against a disposable local club, never production."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'server_local'),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright, expect
from server import Store,make_handler
from admin_panel import AdminAuth
from admin_access import admin_path
from test_server import event
from test_seasons import new_event, new_season
from seasons import save_season, set_rallies, set_rally_points, add_group
from seasons import steam_finish
from test_steam_auth import authenticated_pending
from integrity_rules import expected_settings
import club_settings
import telemetry_audit


def main():
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory)/'club.db');ev=event();store.import_event(ev)
        season_event=new_event('season-summary-browser');store.import_event(season_event)
        season_id=save_season(store,new_season())['id'];set_rallies(store,season_id,[season_event['id']])
        set_rally_points(store,season_id,season_event['id'],[50,35,20],[12,8],[3,1])
        add_group(store,season_id,'division','Division One');add_group(store,season_id,'team','Club Team')
        driver=store.join(ev['id'],'Browser Driver')['token']
        auth=AdminAuth(Path(directory)/'admin-key.txt')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store,auth));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        origin='http://127.0.0.1:'+str(server.server_port)
        errors=[]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                page=browser.new_page(viewport={'width':1280,'height':900},color_scheme='dark')
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(origin+'/')
                page.locator('#themeBtn').click()
                assert page.evaluate("getComputedStyle(document.body).backgroundColor==='rgb(239, 233, 222)'")
                page.reload()
                assert page.locator('html').get_attribute('data-theme')=='light'
                page.locator('#themeBtn').click()
                page.goto(origin+admin_path(auth.key_path))
                page.locator('#adminKey').fill(auth._secret);page.locator('#loginBtn').click();page.locator('#workspace').wait_for(state='visible')
                page.locator('#brandTitle').fill('Custom Rally Club')
                page.locator('#brandSubtitle').fill('Championship')
                page.locator('#brandTagline').fill('Custom competition')
                page.locator('#brandDiscord').fill('https://discord.gg/club42')
                with page.expect_navigation():page.locator('#saveBrand').click()
                page.locator('#workspace').wait_for(state='visible')
                assert 'Custom Rally Club' in page.locator('.brand').text_content()
                page.locator('#newEvent').click();page.locator('#allowBreaks').wait_for(state='visible')
                assert page.locator('#allowBreaks option').count()==2
                for lang in ('pl','en'):
                    page.context.add_cookies([{'name':'acrclub_language','value':lang,'url':origin}])
                    for width in (390,1280):
                        page.set_viewport_size({'width':width,'height':900})
                        for path in ('/', '/guide','/launcher','/seasons', '/rally/'+ev['id'],'/rally/'+season_event['id'],admin_path(auth.key_path),admin_path(auth.key_path)+'/seasons'):
                            page.goto(origin+path)
                            if not page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'):
                                print('Overflow nodes:',page.evaluate("[...document.querySelectorAll('main *, .sitebar *')].filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+1 && getComputedStyle(e).position!=='absolute'}).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,text:e.textContent.slice(0,70)})).slice(0,15)"))
                                raise AssertionError((lang,width,path,'page overflow'))
                            assert page.evaluate("getComputedStyle(document.body).backgroundColor==='rgb(13, 19, 32)'"),(lang,width,path,'background')
                            if not path.startswith(admin_path(auth.key_path)):
                                assert page.locator('.discord-invite').get_attribute('href')=='https://discord.gg/club42'
                                if width==390 and path=='/':
                                    page.locator('#burger').click()
                                    assert page.locator('#mobnav').is_visible()
                                    assert page.locator('#burger').get_attribute('aria-expanded')=='true'
                                    page.locator('#burger').click()
                                    assert not page.locator('#mobnav').is_visible()
                            if path=='/launcher':
                                text=page.locator('main').inner_text()
                                assert 'Python' not in text and '.bat' not in text and 'Automatyczna nawigacja' not in text
                                assert ('Steam' in text)
                                assert page.locator('#launcher-tools a').get_attribute('href')=='acrclub://tools'
                                assert '0.2.15' in page.locator('#launcher-tools').inner_text()
                            if path=='/guide':
                                assert page.locator('#save-safety-guide').count()==1
                                assert '0.2.16' in page.locator('#save-safety-guide').inner_text()
                                assert page.locator(".site-nav a[href='/guide']").evaluate('(element) => getComputedStyle(element).color')=='rgb(237, 71, 3)'
                            if path=='/rally/'+season_event['id']:
                                rules=page.locator('.rally-conditions .season-rules')
                                assert rules.is_visible()
                                assert '50, 35, 20' in rules.inner_text()
                                assert '12, 8' in rules.inner_text() and '3, 1' in rules.inner_text()
                                assert 'Division One' in rules.inner_text()
                                assert rules.evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')==12
                            if path.startswith('/rally/'):
                                assert page.locator('#rally-stage-results details[open]').count()==0
                        page.goto(origin+'/');assert page.locator('a[href$="/ACR-Rally-Club-Setup.exe"]').first.get_attribute('href').startswith('https://github.com/')
                page.goto(origin+admin_path(auth.key_path)+'/seasons')
                page.locator('#workspace').wait_for(state='visible')
                assert page.locator('#seasonList .season-id').inner_text()==season_id
                page.locator('button[data-open="'+season_id+'"]').click()
                expect(page.locator('#seasonId')).to_have_text(season_id)
                page.locator('#newSeason').click()
                assert not page.locator('#seasonIdentifier').is_visible()
                page.set_viewport_size({'width':1280,'height':900});page.goto(origin+'/rally/'+ev['id'])
                page.locator('#rally-stage-results summary').first.click()
                page.locator('#driver-search').fill('Browser')
                csrf=next(c['value'] for c in page.context.cookies() if c['name']=='acrclub_csrf')
                response=page.request.post(origin+'/web/enroll',form={'eventId':ev['id'],'nickname':'Run Dialog Driver','csrf':csrf})
                assert response.ok
                page.goto(origin+'/rally/'+ev['id'])
                rally_url=page.url
                page.evaluate("document.addEventListener('click',e=>{if(e.target.closest('#run-open'))e.preventDefault();},true)")
                with page.expect_response('**/web/run') as launched:
                    page.locator('form[action="/web/run"] button').click()
                assert launched.value.ok
                page.locator('#run-open').wait_for(state='visible')
                assert page.url==rally_url
                assert page.locator('#run-dialog').evaluate('(e)=>e.open')
                assert page.locator('#run-open').get_attribute('href').startswith('acrclub://start?ticket=')
                page.locator('#run-close').click()
                assert not page.locator('#run-dialog').evaluate('(e)=>e.open')
                page.locator('#rally-stage-results summary').first.click()
                page.locator('#driver-search').fill('Browser')
                csrf=next(c['value'] for c in page.context.cookies() if c['name']=='acrclub_csrf')
                store.start(driver,ev['id'],0,ev['allowedCars'][0],expected_settings(ev))
                points=[[i,i/1000*10,0,36,.5,.1,0,2,4000,False] for i in range(1000,60001,5000)]
                telemetry_audit.submit(store,driver,{'eventId':ev['id'],'stageIndex':0,'seq':0,'points':points,'dropped':0})
                page.locator('.trace-root > summary').click()
                expect(page.locator('.trace-driver')).to_have_count(1)
                expect(page.locator('.trace-driver .trace-progress')).to_be_visible()
                assert 'has not finished all stages yet.' in page.locator('.trace-progress').first.inner_text()
                page.locator('.trace-driver > summary').first.click()
                page.locator('[data-trace-stage] > summary').first.click()
                page.locator('.trace-map').first.wait_for(state='visible')
                assert page.locator('.trace-map polyline').first.get_attribute('points')
                assert store.state(driver)['status']=='active'
                assert page.evaluate("getComputedStyle(document.querySelector('main a')).textDecorationLine==='none'")
                store.stage_end(driver,ev['id'],0,60000,expected_settings(ev),12500)
                page.locator('#rally-stage-results td.mono').first.wait_for(state='visible',timeout=12000)
                assert '+00:12.500' in page.locator('#rally-stage-results').inner_text()
                assert page.locator('#rally-stage-results details[open]').count()==1
                assert page.locator('#driver-search').input_value()=='Browser'
                assert next(c['value'] for c in page.context.cookies() if c['name']=='acrclub_csrf')==csrf
                page.goto(origin+admin_path(auth.key_path))
                page.locator('summary').filter(has_text='Administrator time penalties').click()
                page.locator('#apEvent').select_option(ev['id'])
                pid=store._auth(driver)['id']
                page.locator('#apPlayer option[value="'+str(pid)+'"]').wait_for(state='attached')
                page.locator('#apPlayer').select_option(str(pid))
                page.locator('#apSeconds').fill('5')
                page.locator('#apReason').fill('Browser test penalty')
                page.locator('#apAdd').click()
                page.locator('#apHistory').get_by_text('Browser test penalty',exact=False).wait_for()
                assert store.board(ev['id'])['stageResults'][0]['admin_penalty_ms']==5000
                store.start(driver,ev['id'],1,ev['allowedCars'][0],expected_settings(ev))
                store.dnf(driver,'Browser test retirement')
                page.goto(origin+'/rally/'+ev['id'])
                page.locator('.trace-root > summary').click()
                expect(page.locator('.trace-driver .trace-progress')).to_contain_text('DNF')
                account=steam_finish(store,authenticated_pending(store),'Browser Member')
                page.context.add_cookies([{'name':'acrclub_member','value':account['token'],'url':origin}])
                for n,lang in enumerate(('pl','en')):
                    page.context.add_cookies([{'name':'acrclub_language','value':lang,'url':origin}])
                    page.goto(origin+'/club')
                    page.locator('input[name="nickname"]').fill('Browser Club '+str(n))
                    with page.expect_navigation():page.locator('form[action="/web/club/nickname"] button').click()
                    notice=page.locator('.nickname-saved')
                    expect(notice).to_be_visible()
                    assert notice.inner_text()==('Indywidualny nick został zapisany.' if lang=='pl' else 'Your custom nickname has been saved.')
                    assert notice.evaluate('(e)=>getComputedStyle(e).fontSize')=='12px'
                    assert notice.evaluate('(e)=>getComputedStyle(e).color')=='rgb(63, 191, 127)'
                    page.reload();expect(page.locator('.nickname-saved')).to_have_count(0)
                assert not errors,errors
                browser.close()
        finally:
            server.shutdown();server.server_close();store.db.close()
    print('Browser checks passed: 390/1280 px, PL/EN, branding, admin controls, direct downloads, live stage results and CSRF preservation')

if __name__=='__main__':main()
