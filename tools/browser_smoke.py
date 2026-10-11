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
from playwright.sync_api import sync_playwright
from server import Store,make_handler
from admin_panel import AdminAuth
from admin_access import admin_path
from test_server import event
from integrity_rules import expected_settings
import club_settings


def main():
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory)/'club.db');ev=event();store.import_event(ev)
        driver=store.join(ev['id'],'Browser Driver')['token']
        auth=AdminAuth(Path(directory)/'admin-key.txt')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store,auth));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        origin='http://127.0.0.1:'+str(server.server_port)
        errors=[]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                page=browser.new_page(viewport={'width':1280,'height':900})
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(origin+admin_path(auth.key_path))
                page.locator('#adminKey').fill(auth._secret);page.locator('#loginBtn').click();page.locator('#workspace').wait_for(state='visible')
                page.locator('#brandTitle').fill('Custom Rally Club')
                page.locator('#brandSubtitle').fill('Championship')
                page.locator('#brandTagline').fill('Custom competition')
                page.locator('#brandDiscord').fill('https://discord.gg/club42')
                with page.expect_navigation():page.locator('#saveBrand').click()
                page.locator('#workspace').wait_for(state='visible')
                assert 'Custom Rally Club' in page.locator('.brand').inner_text()
                page.locator('#newEvent').click();page.locator('#allowBreaks').wait_for(state='visible')
                assert page.locator('#allowBreaks option').count()==2
                for lang in ('pl','en'):
                    page.context.add_cookies([{'name':'acrclub_language','value':lang,'url':origin}])
                    for width in (390,1280):
                        page.set_viewport_size({'width':width,'height':900})
                        for path in ('/', '/guide','/launcher','/seasons', '/rally/'+ev['id'],admin_path(auth.key_path),admin_path(auth.key_path)+'/seasons'):
                            page.goto(origin+path)
                            if not page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'):
                                print('Overflow nodes:',page.evaluate("[...document.querySelectorAll('main *, .sitebar *')].filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+1 && getComputedStyle(e).position!=='absolute'}).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,text:e.textContent.slice(0,70)})).slice(0,15)"))
                                raise AssertionError((lang,width,path,'page overflow'))
                            assert page.evaluate("getComputedStyle(document.body).backgroundColor==='rgb(20, 29, 48)'"),(lang,width,path,'background')
                            assert page.locator('.discord-invite').get_attribute('href')=='https://discord.gg/club42'
                            if path=='/launcher':assert 'Python' not in page.locator('main').inner_text() and '.bat' not in page.locator('main').inner_text()
                            if path.startswith('/rally/'):
                                assert page.locator('#rally-stage-results details[open]').count()==0
                        page.goto(origin+'/');assert page.locator('a[href$="/ACR-Rally-Club-Setup.exe"]').first.get_attribute('href').startswith('https://github.com/')
                page.set_viewport_size({'width':1280,'height':900});page.goto(origin+'/rally/'+ev['id'])
                page.locator('#rally-stage-results summary').first.click()
                page.locator('#driver-search').fill('Browser')
                csrf=next(c['value'] for c in page.context.cookies() if c['name']=='acrclub_csrf')
                store.start(driver,ev['id'],0,ev['allowedCars'][0],expected_settings(ev));store.stage_end(driver,ev['id'],0,60000,expected_settings(ev))
                page.locator('#rally-stage-results td.mono').first.wait_for(state='visible',timeout=12000)
                assert page.locator('#rally-stage-results details[open]').count()==1
                assert page.locator('#driver-search').input_value()=='Browser'
                assert next(c['value'] for c in page.context.cookies() if c['name']=='acrclub_csrf')==csrf
                assert not errors,errors
                browser.close()
        finally:
            server.shutdown();server.server_close();store.db.close()
    print('Browser checks passed: 390/1280 px, PL/EN, branding, admin controls, direct downloads, live stage results and CSRF preservation')

if __name__=='__main__':main()
