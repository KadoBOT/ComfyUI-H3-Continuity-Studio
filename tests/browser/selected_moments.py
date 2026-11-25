"""Selected moments: the time follows the earlier clip's playhead, and Remember keeps that time with the typed text.
Set H3C_MOMENT_VIDEO to an mp4 to play a real video; without it the playhead is moved by hand."""
from pathlib import Path
from urllib.parse import urlparse,unquote
from playwright.sync_api import sync_playwright
import os,json
ROOT=Path.cwd().resolve()
(ROOT/'.tmp').mkdir(exist_ok=True)
from studio_fixture import FIXTURE
VIDEO=os.environ.get('H3C_MOMENT_VIDEO')
def serve_video(request):
 # Chrome seeks a video only when its server answers byte ranges.
 data=Path(VIDEO).read_bytes();wanted=request.request.headers.get('range','bytes=0-')[6:].split('-')
 start=int(wanted[0] or 0);end=int(wanted[1]) if wanted[1] else len(data)-1
 return request.fulfill(status=206,body=data[start:end+1],headers={'Content-Type':'video/mp4','Accept-Ranges':'bytes',
  'Content-Range':f'bytes {start}-{end}/{len(data)}','Content-Length':str(end-start+1)})
with sync_playwright() as p:
 executable=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or 'C:/Program Files/Google/Chrome/Application/chrome.exe'
 browser=p.chromium.launch(executable_path=executable,headless=True,args=['--disable-gpu'])
 page=browser.new_page(viewport=dict(width=1440,height=1000));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def route(request):
  path=unquote(urlparse(request.request.url).path)
  if path=='/fixture':return request.fulfill(body=FIXTURE,content_type='text/html')
  if path=='/scripts/app.js':return request.fulfill(body='export const app=window.fixtureApp;',content_type='text/javascript')
  if path=='/scripts/api.js':return request.fulfill(body='export const api={apiURL:path=>path,addEventListener(){},fetchApi:async()=>({status:200,ok:true,json:async()=>({revision:0,value:null})})};',content_type='text/javascript')
  if path=='/view':return serve_video(request) if VIDEO else request.abort()
  target=(ROOT/path.lstrip('/')).resolve()
  if ROOT in target.parents and target.is_file():return request.fulfill(body=target.read_text(encoding='utf-8'),content_type='text/javascript')
  return request.abort()
 page.route('**/*',route);page.goto('https://h3c.test/fixture');page.wait_for_function('window.ready===true');page.evaluate('showStudio()')
 page.evaluate("()=>{editor.select(2);editor.box().memory='selected';editor.commit();editor.setTab('box');}")
 player=page.locator('.h3ct-moment-player')
 time=page.get_by_label('Time in the earlier clip, seconds')
 text=page.get_by_label('What to remember at this moment')
 remember=page.get_by_role('button',name='Remember',exact=True)
 result={'player_shown':player.is_visible(),'source':page.get_by_label('Earlier clip to remember').input_value(),
  'remember_needs_text':remember.is_disabled()}
 if VIDEO:
  page.wait_for_function("()=>document.querySelector('.h3ct-moment-player').readyState>=1")
  page.evaluate("()=>new Promise(r=>{const v=document.querySelector('.h3ct-moment-player');v.addEventListener('seeked',r,{once:true});v.currentTime=1.5;})")
 else:
  page.evaluate("()=>{const v=document.querySelector('.h3ct-moment-player');Object.defineProperty(v,'currentTime',{value:1.5,writable:true,configurable:true});v.dispatchEvent(new Event('timeupdate'));}")
 result['time_follows_playhead']=time.input_value()
 text.fill('red brick house, blue door')
 result['remember_enabled_with_text']=not remember.is_disabled()
 page.screenshot(path=str(ROOT/'.tmp'/'selected-moments-before.png'))
 remember.click()
 result['saved']=page.evaluate("()=>stored().boxes[2].memories")
 result['player_kept']=page.evaluate("()=>document.querySelector('.h3ct-moment-player').currentTime")
 result['text_cleared']=text.input_value()==''
 result['listed']=page.locator('.h3ct-moment .h3ct-moment-at').all_inner_texts()
 page.screenshot(path=str(ROOT/'.tmp'/'selected-moments-after.png'))
 page.evaluate_handle('editor.memoryEl').as_element().screenshot(path=str(ROOT/'.tmp'/'selected-moments-panel.png'))
 # A typed time moves the playhead and is what Remember keeps.
 time.fill('0.5');time.dispatch_event('change')
 text.fill('the porch light');text.press('Enter')
 result['typed']=page.evaluate("()=>stored().boxes[2].memories.map(m=>[m.box,m.frame,m.label])")
 print(json.dumps(result))
 assert result['player_shown'] and result['source']=='b2' and result['remember_needs_text'],result
 assert result['time_follows_playhead']=='1.50' and result['remember_enabled_with_text'],result
 assert result['saved']==[{'box':'b2','frame':36,'label':'red brick house, blue door'}],result
 assert abs(result['player_kept']-1.5)<0.05 and result['text_cleared'] and result['listed']==['Clip 2 · 1.50 s'],result
 assert result['typed']==[['b2',36,'red brick house, blue door'],['b2',12,'the porch light']],result
 assert not errors,errors
 print('pass')
 browser.close()
