"""Test neglect deadlines, save migration and recovery without waiting a real day."""
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread
import json
from playwright.sync_api import sync_playwright

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(Path(__file__).resolve().parents[1])))
Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_port}/'
HOUR = 3600000
NOW = 2000000000000
BASE = dict(character='momonga', hunger=60, happy=60, energy=60, xp=155, coins=88, sleeping=False, updated=NOW, meals=7)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    errors = []

    def new_page(record):
        context = browser.new_context(viewport={'width':375,'height':667}, has_touch=True)
        context.add_init_script(f'''
          window.__now=Number(sessionStorage.getItem('test-time'))||{NOW};Date.now=()=>window.__now;
          if(!localStorage.getItem('chiekawa-little-day-v1'))localStorage.setItem('chiekawa-little-day-v1',JSON.stringify({json.dumps(record)}));
        ''')
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        return context, page

    def elapse(page, milliseconds):
        page.evaluate('''ms=>{window.__now+=ms;sessionStorage.setItem('test-time',window.__now);advance();render();save();}''', milliseconds)

    context, page = new_page({**BASE, 'updated':NOW-30*24*HOUR})
    assert not page.evaluate('!!state.goneAt')
    assert page.evaluate('state.lastCareAt') == NOW
    assert page.locator('#coins').inner_text() == '88'
    assert page.locator('#level').inner_text() == 'Lv. 2'
    context.close()
    print('PASS old save receives a full-day grace period with level/coins retained')

    for character in ['chiikawa','momonga']:
        context, page = new_page({**BASE,'character':character,'lastCareAt':NOW-12*HOUR,'goneAt':0})
        assert page.locator('#care-notice').is_visible()
        assert page.locator('#pet').is_visible()
        last_care = page.evaluate('state.lastCareAt')
        page.evaluate('save();save();save()')
        assert page.evaluate('state.lastCareAt') == last_care
        elapse(page, 12*HOUR-1)
        assert not page.evaluate('!!state.goneAt')
        elapse(page, 1)
        assert page.locator('#pet').is_hidden()
        assert page.locator('#away-scene').is_visible()
        assert page.evaluate('state.goneAt') == last_care+24*HOUR
        for selector in ['#food-0','#food-3','#play-button','#pet-button','#sleep-button','#choose-button']:
            assert page.locator(selector).is_disabled(), selector
        page.evaluate('openChoice()')
        assert page.locator('#choice-modal').is_hidden()
        page.reload()
        assert page.locator('#away-scene').is_visible()
        assert page.locator('#pet').is_hidden()
        page.locator('#bring-home').scroll_into_view_if_needed()
        page.screenshot(path=f'/tmp/runaway-{character}.png')
        page.locator('#bring-home').tap()
        assert not page.evaluate('!!state.goneAt')
        assert page.locator('#pet').is_visible()
        assert page.locator('#coins').inner_text()=='88' and page.locator('#level').inner_text()=='Lv. 2'
        assert page.evaluate('state.character')==character and page.evaluate('state.meals')==7
        assert page.evaluate('state.lastCareAt')==NOW+12*HOUR
        page.reload()
        assert page.locator('#pet').is_visible() and page.locator('#away-scene').is_hidden()
        context.close()
    print('PASS 12h warning, exact 24h departure, autosave does not extend care, unavailable care/switch, persistent absence, return preserving both characters and progress')

    for selector in ['#food-0','#pet-button','#play-button','#sleep-button']:
        context, page = new_page({**BASE,'lastCareAt':NOW-12*HOUR,'goneAt':0})
        page.locator(selector).scroll_into_view_if_needed();page.locator(selector).tap()
        assert page.evaluate('state.lastCareAt')==NOW
        assert page.locator('#care-notice').is_hidden()
        elapse(page,24*HOUR-1);assert not page.evaluate('!!state.goneAt')
        elapse(page,1);assert page.evaluate('!!state.goneAt')
        context.close()
    print('PASS all four successful care actions reset the deadline; automatic wake does not reset it')

    context, page = new_page({**BASE,'lastCareAt':NOW-24*HOUR+1,'goneAt':0})
    page.locator('#choose-button').tap();page.locator('.character-choice[data-character="chiikawa"]').tap()
    elapse(page,1);assert page.evaluate('!!state.goneAt')
    context.close()
    print('PASS switching character does not bypass neglect')

    context, page = new_page(BASE)
    record={**BASE,'character':'chiikawa','lastCareAt':NOW-25*HOUR,'goneAt':NOW-HOUR}
    page.evaluate('''record=>{gameAccount.pause();gameAccount.load(record,KEY+':account:test');gameAccount.resume();}''',record)
    assert page.locator('#pet').is_hidden() and page.locator('#bring-home').is_visible()
    assert page.evaluate("JSON.parse(localStorage.getItem(KEY+':account:test')).goneAt")==NOW-HOUR
    assert page.evaluate('gameAccount.snapshot().lastCareAt')==NOW-25*HOUR
    context.close()
    assert not errors, errors
    print('PASS account restore and snapshots preserve absence/care timestamps; no JavaScript errors')
    browser.close()
server.shutdown()
