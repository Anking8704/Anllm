"""Local provider fixtures: connection isolation, real tool loops, image routing, wallpaper."""
import asyncio,base64,json,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtWidgets import QApplication
import api_profiles,core
from settings_panel import SettingsDialog,PRESETS
from main import MainWindow

NAMES=['GPT','Grok','Claude','Gemini','GLM','DeepSeek','Kimi']
KEYS={name:'LOCAL_FIXTURE_'+name+'_ONLY' for name in NAMES}
seen=[]
PNG=base64.b64encode(bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082')).decode()

class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def identify(self):
        key=self.headers.get('x-api-key') or self.headers.get('Authorization','').removeprefix('Bearer ')
        name=next((n for n,k in KEYS.items() if k==key),None)
        assert name,'Unexpected fixture credential';seen.append((name,self.command,urlsplit(self.path).path))
        if name=='Claude':assert self.headers['anthropic-version']=='2023-06-01' and not self.headers.get('Authorization')
        return name
    def respond(self,body):
        raw=json.dumps(body).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        name=self.identify();self.respond({'data':[{'id':name.lower()+'-agent'},{'id':name.lower()+'-image'}]})
    def do_POST(self):
        name=self.identify();payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path.endswith('/images/generations'):
            assert name=='GPT' and payload['model']=='gpt-image';self.respond({'data':[{'b64_json':PNG}]});return
        assert payload['model']==name.lower()+'-agent'
        if name=='Claude':
            assert self.path.endswith('/messages');assert payload['tools'] and 'input_schema' in payload['tools'][0]
            answered=any(b.get('type')=='tool_result' for m in payload['messages'] for b in m['content'])
            if answered:blocks=[{'type':'text','text':'Claude resumed: silver'}]
            else:blocks=[{'type':'tool_use','id':'claude-question','name':'ask_user','input':{'questions':[{'question':'选哪种颜色？','options':['silver','blue']}]}}]
            self.respond({'content':blocks,'usage':{'input_tokens':5,'output_tokens':5},'stop_reason':'end_turn' if answered else 'tool_use'})
        else:
            assert self.path.endswith('/chat/completions')
            answered=any(m['role']=='tool' for m in payload['messages'])
            message={'role':'assistant','content':name+' resumed: silver'} if answered else {'role':'assistant','content':'','tool_calls':[{'id':name+'-question','type':'function','function':{'name':'ask_user','arguments':json.dumps({'questions':[{'question':'选哪种颜色？','options':['silver','blue']}]})}}]}
            self.respond({'choices':[{'message':message}],'usage':{'prompt_tokens':5,'completion_tokens':5}})

server=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=server.serve_forever,daemon=True).start()
base='http://127.0.0.1:'+str(server.server_port)+'/v1';profiles={}
try:
    for name in NAMES:
        protocol='anthropic' if name=='Claude' else 'chat'
        model_names=core.shared.read_models(base,KEYS[name],'',protocol)
        value={'name':name,'base_url':base,'api_key':KEYS[name],'chat_model':name.lower()+'-agent','image_model':name.lower()+'-image','chat_api':protocol,'make_default':name=='GPT'}
        profile=core.shared.save_settings(value,'');profiles[name]=profile['id'];core.shared.cache_models(model_names,profile['id'])
        assert core.shared.cached_models(profile['id'])==model_names
        assert core.shared.read_models(base,'',profile['id'],protocol)==model_names
    assert len({api_profiles.get(p)['credential_profile'] for p in profiles.values()})==7
    first=core.new_session(profile_id=profiles['GPT']);second=core.new_session(profile_id=profiles['Claude'])
    core.shared.save_settings({'make_default':True},profiles['Grok'])
    assert core.new_session()['api_profile_id']==profiles['Grok']
    assert core.load_session(first['id'])['api_profile_id']==profiles['GPT']
    assert core.load_session(second['id'])['api_profile_id']==profiles['Claude']
    async def ask(value):await asyncio.sleep(.01);return {'cancelled':False,'answers':[{'question':value[0]['question'],'answer':'silver'}]}
    async def deny(*_):raise AssertionError('Chat fixture should not request execution')
    async def run():
        sessions=[first,second]+[core.new_session(profile_id=profiles[n]) for n in NAMES if n not in ('GPT','Claude')]
        await asyncio.gather(*(core.execute_task(s,'请先问我颜色',[],'chat',lambda _:None,deny,ask=ask) for s in sessions))
        for s in sessions:
            assert 'resumed: silver' in s['messages'][-1]['text'] and not s['messages'][-1].get('error')
            assert s['messages'][-1]['api_profile_id']==s['api_profile_id']
    asyncio.run(run())
    assert all(any(n==name and method=='POST' for n,method,_ in seen) for name in NAMES)
    core.shared.save_settings({'image_api_profile_id':profiles['GPT']},profiles['Claude'])
    from core import ImageTool,ImageInput
    pictures=[];tool=ImageTool(api_profiles.get(profiles['Claude']),[],pictures.append)
    asyncio.run(tool.execute(ImageInput(prompt='a silver shape'),None));assert len(pictures)==1
    assert pictures[0]['model']=='gpt-image'
    try:core.shared.save_settings({'base_url':'https://example.invalid/v1'},profiles['GPT'])
    except ValueError:pass
    else:raise AssertionError('Changed URL reused old credential')
    for path in core.DATA.glob('*.json'):
        text=path.read_text('utf-8');assert not any(key in text for key in KEYS.values())
    assert not any(key in api_profiles.store_path().read_text('utf-8') for key in KEYS.values())
    assert all(key not in core.scrub(' '.join(KEYS.values())) for key in KEYS.values())
    application=QApplication.instance() or QApplication([])
    image=QImage(1200,800,QImage.Format_RGB32);image.fill(QColor('#385980'));painter=QPainter(image)
    painter.setBrush(QColor('#8c5f88'));painter.setPen(Qt.NoPen);painter.drawEllipse(400,-200,1000,1000);painter.setBrush(QColor('#597f96'));painter.drawEllipse(-200,300,800,800);painter.end()
    sample=core.ROOT/'sample-wallpaper.png';image.save(str(sample))
    from appearance import import_wallpaper,wallpaper_path
    wallpaper=import_wallpaper(sample);sample.unlink();assert wallpaper_path(wallpaper)
    core.save_preferences({**core.preferences(),'wallpaper':wallpaper,'wallpaper_shade':55})
    from theme import STYLE
    application.setStyleSheet(STYLE);window=MainWindow();window.show();application.processEvents()
    window.open_session(first['id']);assert window.api_button.currentData()==profiles['GPT']
    window.open_session(second['id']);assert window.api_button.currentData()==profiles['Claude']
    window.api_button.setCurrentIndex(window.api_button.findData(profiles['Kimi']));assert core.load_session(second['id'])['api_profile_id']==profiles['Kimi']
    window.open_session(first['id']);assert window.api_button.currentData()==profiles['GPT']
    assert not window.wallpaper_surface.picture.isNull()
    window.new_chat();application.processEvents();window.grab().save(str(core.ROOT/'wallpaper-render.png'))
    dialog=SettingsDialog(window);dialog.show();application.processEvents()
    assert not dialog.chat.isEditable() and not dialog.image.isEditable()
    assert [item[0] for item in PRESETS[1:]]==NAMES
    dialog.grab().save(str(core.ROOT/'settings-render.png'))
    dialog.new_profile();dialog.name.setText('GPT 工作账号');dialog.base.setText(base);dialog.key.setText(KEYS['GPT']);dialog.protocol.setCurrentIndex(dialog.protocol.findData('chat'))
    def settle():
        deadline=time.monotonic()+15
        while dialog.workers and time.monotonic()<deadline:application.processEvents();time.sleep(.01)
        application.processEvents();assert not dialog.workers,'Settings worker did not finish'
    dialog.read_models();settle();assert dialog.chat.currentText()=='gpt-agent'
    dialog.save();settle();extra=dialog.profile_id
    assert extra!=profiles['GPT'] and core.shared.public_settings(extra)['name']=='GPT 工作账号'
    assert core.shared.cached_models(extra)==['gpt-agent','gpt-image']
    assert window.current['api_profile_id']==extra and not dialog.dirty
    dialog.finish();application.processEvents();assert dialog.result()==1
    # Updating one account at an identical endpoint invalidates only its own catalog.
    core.shared.save_settings({'api_key':'LOCAL_ROTATED_KEY_ONLY'},extra)
    assert core.shared.cached_models(extra)==[] and core.shared.cached_models(profiles['GPT'])==['gpt-agent','gpt-image']
    window.close()
    report={'status':'passed','saved_provider_profiles':NAMES,'concurrent_real_agent_tool_loops':7,'native_claude':'passed','image_api_routing':'passed','per_conversation_restore':'passed','credential_isolation':'passed','settings_async_save':'passed','local_wallpaper_copy_and_render':'passed'}
    core.shared.atomic_json(core.ROOT/'logs'/'profiles-verification.json',report);print(json.dumps(report,ensure_ascii=False))
finally:server.shutdown();server.server_close()
