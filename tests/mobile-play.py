"""Portrait interaction regression: character/speech stay visible at real tap targets."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(Path(__file__).resolve().parents[1])))
Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_port}/'

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    for width, height in [(320, 568), (360, 640), (375, 667), (390, 844), (412, 915), (430, 932)]:
        for character in ['chiikawa', 'momonga']:
            context = browser.new_context(viewport={'width': width, 'height': height}, has_touch=True, is_mobile=True)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url)
            page.locator(f'.character-choice[data-character="{character}"]').tap()

            def tap_and_check(selector, expression):
                button = page.locator(selector)
                button.scroll_into_view_if_needed()
                assert button.evaluate('''el=>{const r=el.getBoundingClientRect();const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return el===hit||el.contains(hit)}'''), (width, height, selector, 'button covered')
                button.tap()
                assert page.locator('#pet').get_attribute('data-expression') == expression
                for _ in range(3):
                    assert page.evaluate('''()=>{const pet=document.querySelector('#pet').getBoundingClientRect(),speech=document.querySelector('#speech').getBoundingClientRect(),room=document.querySelector('#room').getBoundingClientRect();return pet.top>=0&&pet.bottom<=innerHeight&&speech.top>=0&&speech.bottom<=innerHeight&&room.bottom<=innerHeight}'''), (width, height, selector, 'reaction outside viewport')
                    page.wait_for_timeout(100)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')

            tap_and_check('#pet-button', 'play')
            tap_and_check('#play-button', 'play')
            tap_and_check('#food-0', 'eat')
            if (width, height, character) == (390, 844, 'momonga'):
                page.screenshot(path='/tmp/mobile-feeding-after.png')
            # The lower food row must remain usable with the sticky room above it.
            page.wait_for_timeout(2600)
            tap_and_check('#food-3', 'eat')
            tap_and_check('#sleep-button', 'sleep')
            page.screenshot(path='/tmp/mobile-sleep-after.png') if (width, height, character) == (320, 568, 'chiikawa') else None
            tap_and_check('#sleep-button', 'play')
            page.locator('#account-button').scroll_into_view_if_needed()
            page.locator('#account-button').tap()
            assert page.locator('#account-dialog').is_visible()
            assert page.locator('#auth-email').is_visible()
            assert not errors, errors
            context.close()
        print(f'PASS {width}x{height}: both characters visible for pet/play/both food rows/sleep/wake; controls clickable; login opens')

    # The original tablet and landscape arrangements retain their non-sticky room.
    for width, height in [(810, 1080), (1080, 810), (844, 390)]:
        context = browser.new_context(viewport={'width': width, 'height': height}, has_touch=True)
        page = context.new_page()
        page.goto(url)
        page.locator('.character-choice[data-character="momonga"]').tap()
        assert page.locator('#room').evaluate('el=>getComputedStyle(el).position') != 'sticky'
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        context.close()
    print('PASS tablet and landscape layout retained')
    browser.close()
server.shutdown()
