from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import threading
from playwright.sync_api import sync_playwright
html=(Path(__file__).resolve().parents[1]/'index.html').read_text()
# Inject a fake backend only into this test response; application auth logic is unchanged.
html=html.replace('client=window.supabase.createClient','client=window.__mockSupabase.createClient')
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(html.encode())
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
mock='''
window.__db={};window.__failSave=false;let session=null,callback=()=>{};
window.__mockSupabase={createClient:()=>({auth:{
 onAuthStateChange(cb){callback=cb;return {data:{subscription:{unsubscribe(){}}}}},
 async getSession(){return {data:{session},error:null}},
 async signInWithPassword({email,password}){if(password==='bad-password')return {error:{code:'invalid_credentials'}};session={user:{id:email,email}};callback('SIGNED_IN',session);return {data:{session},error:null}},
 async signUp(){return {data:{session:null},error:null}},
 async resetPasswordForEmail(){return {data:{},error:null}},
 async updateUser(){return {data:{},error:null}},
 async signOut(){session=null;callback('SIGNED_OUT',null);return {error:null}}
},from(){return {select(){return this},eq(){return this},async maybeSingle(){return {data:window.__db[session.user.id]||null,error:null}}}},
 async rpc(name,{p_state,p_expected_revision}){if(window.__failSave)return {error:{message:'offline'}};const id=session.user.id,old=window.__db[id];if((old?.revision||0)!==p_expected_revision)return {error:{message:'SAVE_CONFLICT'}};const revision=p_expected_revision+1;window.__db[id]={state:JSON.parse(JSON.stringify(p_state)),revision};return {data:revision,error:null}}
})};
'''
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 c=b.new_context(viewport={'width':810,'height':1080});c.add_init_script(mock)
 page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(f'http://127.0.0.1:{server.server_port}/');page.locator('.character-choice[data-character="momonga"]').click()
 page.locator('#food-0').click();page.locator('#play-button').click()
 page.locator('#account-button').click();page.locator('#auth-email').fill('a@example.com');page.locator('#auth-password').fill('password123');page.locator('#sign-in').click()
 page.locator('#import-guest').wait_for(state='visible');page.locator('#import-guest').click()
 page.wait_for_function("window.__db['a@example.com']?.state.coins===42")
 assert page.locator('#coins').inner_text()=='42'
 print('PASS sign-in UI, guest-import and initial account upload')
 page.locator('#sign-out').click();page.wait_for_function("document.querySelector('#account-button').textContent==='로그인'")
 assert page.locator('#coins').inner_text()=='42'
 page.locator('#auth-email').fill('b@example.com');page.locator('#auth-password').fill('password123');page.locator('#sign-in').click();page.locator('#start-account').click()
 page.wait_for_function("!!window.__db['b@example.com']")
 page.locator('#close-account').click();page.locator('.character-choice[data-character="chiikawa"]').click();assert page.locator('#coins').inner_text()=='30'
 page.locator('#account-button').click();page.locator('#sign-out').click();page.wait_for_function("document.querySelector('#account-button').textContent==='로그인'")
 page.locator('#auth-email').fill('a@example.com');page.locator('#auth-password').fill('password123');page.locator('#sign-in').click();page.wait_for_function("document.querySelector('#coins').textContent==='42'")
 assert page.locator('#pet').get_attribute('data-character')=='momonga'
 print('PASS A/B account isolation and cloud restore')
 page.locator('#close-account').click();page.evaluate("window.__failSave=true;state.coins=101;save();window.dispatchEvent(new Event('online'))")
 page.wait_for_function("document.querySelector('#cloud-status').textContent.includes('서버 저장 대기')")
 assert page.evaluate("JSON.parse(localStorage.getItem(KEY+':account:a@example.com')).coins")==101
 page.evaluate("window.__failSave=false;window.dispatchEvent(new Event('online'))")
 page.wait_for_function("window.__db['a@example.com'].state.coins===101")
 print('PASS failed upload keeps local account save and retries online')
 page.evaluate("window.__db['a@example.com'].revision+=1;state.coins=102;save();window.dispatchEvent(new Event('online'))")
 page.wait_for_function("document.querySelector('#cloud-status').textContent.includes('다른 기기')")
 assert page.evaluate('document.querySelector("main").inert')
 assert page.evaluate("window.__db['a@example.com'].state.coins")==101
 print('PASS stale revision pauses game instead of overwriting another device')
 page.set_viewport_size({'width':375,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors
 print('PASS no JS errors and mobile layout')
 c2=b.new_context();c2.add_init_script(mock);p2=c2.new_page();p2.goto(f'http://127.0.0.1:{server.server_port}/')
 p2.locator('.character-choice[data-character="chiikawa"]').click();p2.locator('#account-button').click();p2.locator('#auth-email').fill('new@example.com');p2.locator('#auth-password').fill('password123');p2.locator('#sign-up').click()
 p2.wait_for_function("document.querySelector('#auth-message').textContent.includes('인증 링크')")
 p2.locator('#forgot-password').click();p2.wait_for_function("document.querySelector('#auth-message').textContent.includes('재설정 메일')")
 p2.locator('#auth-password').fill('bad-password');p2.locator('#sign-in').click();p2.wait_for_function("document.querySelector('#auth-message').textContent.includes('맞지 않아요')")
 print('PASS signup confirmation, reset request and wrong-password feedback (mock responses)')
 b.close()
server.shutdown()
