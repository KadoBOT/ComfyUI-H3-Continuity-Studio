"""Isolated Studio lane editing smoke; no live ComfyUI or GPU work."""
from pathlib import Path
from urllib.parse import urlparse,unquote
from playwright.sync_api import sync_playwright
import os,json
ROOT=Path.cwd().resolve()
FIXTURE='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;background:#15171b;color:#ddd;font:14px Arial}*{box-sizing:border-box}</style></head><body><script>window.fixtureApp={registerExtension(){},ui:{settings:{getSettingValue:()=>false}},extensionManager:{dialog:{confirm:async()=>true}}};</script><script type="module">\nimport {TimelineEditor} from \'/web/h3c_timeline_editor.mjs\';\nimport {Studio} from \'/web/h3c_studio.mjs\';\nimport {TimelineHistory} from \'/web/h3c_history.mjs\';\nimport {parseJSON,stringifyJSON} from \'/web/h3c_project.mjs\';\nconst LAYER={id:\'b2v1\',seed:5101,prompt:\'Close on her hands.\',first:\'\',last:\'\',previews:[],memory:\'off\',memories:[],dialogue:\'cues\'};\nconst DOC=JSON.stringify({version:1,prompt:\'\',requires:[\'video-layers-1\'],boxes:[\n {id:\'a1\',frames:48,exact:true,prompt:\'The street.\',seed:7,cut:false},\n {id:\'b2\',frames:90,exact:true,prompt:\'Wide on the kitchen.\',seed:1,cut:true,layers:[LAYER],\n  switch:{cuts:[{at:27,to:\'b2v1\'}],fade:6,sound:\'screen\'}},\n {id:\'c3\',frames:48,exact:true,prompt:\'The door.\',seed:2,cut:true}]});\nconst file=name=>({filename:name,subfolder:\'h3_continuity\',type:\'output\'});\nconst STATUS={ok:true,message:\'\',boxes:[\n {id:\'a1\',status:\'done\',video:{file:file(\'a1.mp4\'),frames:48,fps:24}},\n {id:\'b2\',status:\'done\',video:{file:file(\'b2.mp4\'),frames:90,fps:24},stack:{file:file(\'stack@b2.mp4\'),frames:90,fps:24},\n  videos:[{id:\'b2v1\',status:\'done\',seed:5101,video:{file:file(\'b2v1.mp4\'),frames:90,fps:24}}]},\n {id:\'c3\',status:\'next\'}],layers_remaining:0};\nwindow.showStudio=()=>{\n let stored=DOC;\n const queued=[];\n const host={read:()=>stored,write:text=>{stored=text;},context:()=>39,settings:()=>({width:512,height:512,context_frames:39}),\n  connected:()=>({images:[],audios:[],videos:[],video_audios:[]}),viewUrl:file=>`/view?filename=${file.filename}`,\n  watch:()=>({running:false}),runningBox:()=>null,title:()=>\'Video layers\',titleOf:id=>id,changed(){},story:()=>null,\n  node:{id:1,widgets:[],inputs:[]},hasVideo:()=>true,queue:async(...args)=>{queued.push(args);}};\n host.sequenceName=()=>"fixture";host.prepareStillPrompts=async()=>null; const editor=new TimelineEditor(host);host.editor=editor;document.body.append(editor.root);\n host.history=new TimelineHistory({read:()=>({timeline:parseJSON(stored),settings:{}}),identity:()=>\'video-layers\',\n  apply:value=>{stored=stringifyJSON(value.timeline);editor.load();},notify:()=>{},group:()=>null,flush:()=>{}});\n host.undoStep=()=>host.history.capture();\n const studio=new Studio();studio.open(host);\n editor.setStatus(STATUS);editor.select(1);editor.inspectClip();studio.refresh();\n Object.assign(window,{editor,studio,stored:()=>JSON.parse(stored),queued});\n return true;\n};\nwindow.screenVideo=()=>studio.screen.querySelector(\'video:not(.h3cx-live)\')?.getAttribute(\'src\')??\'\';\nwindow.ready=true;\n</script></body></html>'
with sync_playwright() as p:
 executable=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or 'C:/Program Files/Google/Chrome/Application/chrome.exe'
 browser=p.chromium.launch(executable_path=executable,headless=True,args=['--disable-gpu'])
 page=browser.new_page(viewport=dict(width=1440,height=1000));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def route(request):
  path=unquote(urlparse(request.request.url).path)
  if path=='/fixture':return request.fulfill(body=FIXTURE,content_type='text/html')
  if path=='/scripts/app.js':return request.fulfill(body='export const app=window.fixtureApp;',content_type='text/javascript')
  if path=='/scripts/api.js':return request.fulfill(body='export const api={apiURL:path=>path,addEventListener(){},fetchApi:async()=>({status:200,ok:true,json:async()=>({revision:0,value:null})})};',content_type='text/javascript')
  target=(ROOT/path.lstrip('/')).resolve()
  if ROOT in target.parents and target.is_file():return request.fulfill(body=target.read_text(encoding='utf-8'),content_type='text/javascript')
  return request.abort()
 page.route('**/*',route);page.goto('https://h3c.test/fixture');page.wait_for_function('window.ready===true');page.evaluate('showStudio()')
 # Navigation and toolbars keep names while rendering SVG controls.
 page.get_by_role('tab',name='References',exact=True).click()
 assert page.locator('.h3cx-focus').get_by_text('Pictures',exact=True).count()>0
 assert page.locator('.h3cx-focus').get_by_text('RefMods',exact=True).count()>0
 page.evaluate("studio.setPage('refmods')")
 assert page.get_by_role('tab',name='References',exact=True).get_attribute('aria-selected')=='true'
 page.get_by_role('tab',name='References',exact=True).press('Home')
 assert page.get_by_role('tab',name='Viewer',exact=True).get_attribute('aria-selected')=='true'
 assert page.locator('.h3cx-project-actions button svg').count()==6
 assert page.locator('input[aria-label="Takes to render"]').count()==0
 assert page.locator('.h3ct-clip-actions summary').count()==0
 page.get_by_role('button',name='Add video lane',exact=True).click()
 assert page.evaluate("stored().tracks.filter(t=>t.type==='video').length")==2
 assert page.get_by_role('button',name='Collapse video lanes',exact=True).is_visible()
 before=page.evaluate('JSON.stringify(stored())')
 page.once('dialog',lambda d:d.dismiss());page.get_by_role('button',name='Delete Video 1',exact=True).click()
 assert page.evaluate('JSON.stringify(stored())')==before
 page.get_by_role('button',name='Delete Video 2',exact=True).click()
 assert page.evaluate("stored().tracks.filter(t=>t.type==='video').length")==1
 page.get_by_role('button',name='Add video lane',exact=True).click()
 page.evaluate('editor.playheadFrame=0;editor.trackEditor.addClip()')
 assert page.evaluate("editor.box().track===stored().tracks.filter(t=>t.type==='video').at(-1).id")
 clip=page.locator('.h3ct-track-row[data-track="v2"] .h3ct-track-clip').last
 rect=clip.bounding_box();body=clip.locator('..').bounding_box();span=page.evaluate('editor.trackEditor.span')
 page.mouse.move(rect['x']+10,rect['y']+12);page.mouse.down();page.mouse.move(rect['x']+10+49*body['width']/span,rect['y']+12,steps=8);page.mouse.up()
 assert page.evaluate('editor.box().start')==48,page.evaluate('editor.box().start')
 page.get_by_role('button',name='Collapse video lanes',exact=True).click()
 assert page.get_by_role('button',name='Expand video lanes',exact=True).is_visible()
 # Overlap inspector changes the selected pair and rejects out-of-range fades.
 page.get_by_role('button',name='Edit overlap between clips 2 and 4',exact=True).click()
 assert page.locator('.h3cx-inspector-title').inner_text()=='Overlap'
 page.get_by_role('checkbox',name='Use overlap switch',exact=True).check()
 switch=page.get_by_role('spinbutton',name='Overlap switch at frame',exact=True)
 switch.fill('99');switch.dispatch_event('change')
 page.get_by_role('combobox',name='Overlap sound',exact=True).select_option('b2')
 assert page.evaluate("stored().overlap_switches[0].at===99 && stored().overlap_switches[0].sound==='b2'")
 switch=page.get_by_role('spinbutton',name='Overlap switch at frame',exact=True)
 switch.fill('49');switch.dispatch_event('change')
 assert page.evaluate('stored().overlap_switches[0].at')==99
 assert page.locator('.h3ct-overlap-inspector [role=status]').inner_text()
 page.get_by_role('checkbox',name='Use overlap switch',exact=True).uncheck()
 assert page.evaluate('stored().overlap_switches.length')==0
 page.evaluate('editor.inspectClip()')
 page.get_by_role('tab',name='Prompt',exact=True).press('End')
 assert page.get_by_role('tab',name='Settings',exact=True).get_attribute('aria-selected')=='true'
 # A populated lane needs confirmation; Undo restores its clips and placement.
 before_delete=page.evaluate('JSON.stringify(stored())')
 page.get_by_role('button',name='Expand video lanes',exact=True).click()
 page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='Delete Video 2',exact=True).click()
 assert page.evaluate("!stored().tracks.some(t=>t.id==='v2')")
 page.evaluate('editor.host.history.undo()')
 assert page.evaluate('JSON.stringify(stored())')==before_delete
 # Import into two independent text lanes without overwriting the first.
 for text in ['First title','Second title']:
  with page.expect_file_chooser() as chosen:page.get_by_role('button',name='Add text lane',exact=True).click()
  chosen.value.set_files(dict(name='words.json',mimeType='application/json',buffer=json.dumps(dict(segments=[dict(start=0,end=1,text=text)])).encode()))
  page.wait_for_function('(n)=>stored().text_lanes?.length===n',arg=1 if text=='First title' else 2)
 assert page.evaluate('stored().text_lanes.map(l=>l.attachment.cues[0].text)')==['First title','Second title']
 page.evaluate("editor.host.uploadAudio=async()=>({duration:5,title:'Test recording',peaks:[],file:{type:'input',filename:'test.wav',subfolder:''}})")
 with page.expect_file_chooser() as chosen:page.get_by_role('button',name='Add audio lane',exact=True).click()
 chosen.value.set_files(dict(name='test.wav',mimeType='audio/wav',buffer=b'fixture'))
 page.wait_for_function('stored().audio_clips?.length===1')
 assert page.evaluate("stored().tracks.find(t=>t.id===stored().audio_clips[0].track).type==='audio'")
 # Reusable conversion instructions live in Project settings and retain their storage.
 page.get_by_role('button',name='Project settings',exact=True).click()
 instructions=page.get_by_role('textbox',name='Still prompt conversion instructions',exact=True)
 instructions.fill('Keep framing and visual details.');instructions.dispatch_event('change')
 assert page.evaluate("stored().still_prompt_preparation.instructions==='Keep framing and visual details.'")
 assert page.locator('summary').filter(has_text='Still prompt conversion instructions').count()==0
 page.evaluate('studio.close()')
 assert page.evaluate('editor.frameImages.preparation.instructionsRoot.parentNode===editor.frameImages.preparation.root')
 page.evaluate('studio.open(editor.host)')
 # Unknown reader requirements protect every new lane action.
 page.evaluate("editor.state.requires.push('future-1');editor.host.write(JSON.stringify(editor.state));editor.load()")
 protected=page.evaluate('JSON.stringify(stored())')
 page.evaluate("editor.trackEditor.addLane('video')")
 assert page.evaluate('JSON.stringify(stored())')==protected
 assert not errors,errors
 print(json.dumps(dict(lanes='pass',snap='pass',confirmation='pass',errors=errors)))
 browser.close()
