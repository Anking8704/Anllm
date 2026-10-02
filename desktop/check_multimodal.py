"""Full coordinator -> vision -> image -> vision -> coordinator loop with isolated local APIs."""
import asyncio,base64,json,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication
import api_profiles,core
from modal_tools import AnalyzeImagesInput,AnalyzeImagesTool

application=QApplication.instance() or QApplication([])
reference=core.ROOT/'workspace'/'project.png';result_file=core.ROOT/'cache'/'result.png'
for path,color in [(reference,'#eef0f8'),(result_file,'#456cba')]:
    picture=QImage(64,64,QImage.Format_RGB32);picture.fill(QColor(color));assert picture.save(str(path))
REFERENCE=reference.read_bytes();GENERATED=result_file.read_bytes();calls=[]
KEYS={'DeepSeek':'LOCAL_DS_ONLY','GPT vision':'LOCAL_VISION_ONLY','GPT image':'LOCAL_IMAGE_ONLY','Claude vision':'LOCAL_CLAUDE_VISION_ONLY','Responses vision':'LOCAL_RESPONSES_VISION_ONLY'}

def all_strings(value):
    if isinstance(value,str):return [value]
    if isinstance(value,list):return [s for item in value for s in all_strings(item)]
    if isinstance(value,dict):return [s for item in value.values() for s in all_strings(item)]
    return []

class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def identify(self):
        key=self.headers.get('x-api-key') or self.headers.get('Authorization','').removeprefix('Bearer ')
        name=next((name for name,value in KEYS.items() if value==key),None)
        assert name,'Unknown local fixture credential'
        assert name==self.server.role or (self.server.role=='GPT vision' and name in ('Claude vision','Responses vision'))
        calls.append((name,self.command,self.path));return name
    def respond(self,body):
        raw=json.dumps(body).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        name=self.identify()
        models={'DeepSeek':['deepseek-chat'],'GPT vision':['gpt-5.5','gpt-6.1-sol'],'GPT image':['gpt-image-2','gpt-image-2.5-flare'],'Claude vision':['claude-vision'],'Responses vision':['gpt-responses-vision']}[name]
        self.respond({'data':[{'id':model} for model in models]})
    def do_POST(self):
        name=self.identify();raw=self.rfile.read(int(self.headers['Content-Length']))
        if name=='GPT image':
            if self.path.endswith('/images/edits'):
                assert 'multipart/form-data' in self.headers['Content-Type'] and b'gpt-image-2.5-flare' in raw and REFERENCE in raw
            else:
                payload=json.loads(raw);assert self.path.endswith('/images/generations') and payload['model']=='gpt-image-2.5-flare'
            self.respond({'data':[{'b64_json':base64.b64encode(GENERATED).decode()}]});return
        payload=json.loads(raw)
        if name in ('GPT vision','Claude vision','Responses vision'):
            assert not payload.get('tools'),'Vision must not recurse into tools'
            if name=='Claude vision':
                assert self.path.endswith('/messages') and self.headers.get('anthropic-version')=='2023-06-01'
                images=[b['source']['data'] for m in payload['messages'] for b in m['content'] if b.get('type')=='image']
            else:
                images=[s.split(';base64,')[1] for s in all_strings(payload) if s.startswith('data:image/')]
            assert len(images)==1 and base64.b64decode(images[0]) in (REFERENCE,GENERATED)
            text='VISIBLE_REFERENCE_SILVER' if base64.b64decode(images[0])==REFERENCE else 'VISIBLE_GENERATED_BLUE'
            if name=='Claude vision':self.respond({'content':[{'type':'text','text':text}],'usage':{},'stop_reason':'end_turn'})
            elif name=='Responses vision':self.respond({'output':[{'type':'message','content':[{'type':'output_text','text':text}]}],'usage':{}})
            else:
                assert payload['model']=='gpt-6.1-sol';self.respond({'choices':[{'message':{'role':'assistant','content':text}}],'usage':{}})
            return
        assert payload['model']=='deepseek-chat' and self.path.endswith('/chat/completions')
        assert not any(s.startswith('data:image/') for s in all_strings(payload)),'Text-only coordinator received raw image bytes'
        user_text=' '.join(all_strings([m for m in payload['messages'] if m['role']=='user']))
        tool_names={call['id']:call['function']['name'] for message in payload['messages'] for call in message.get('tool_calls',[])}
        results={tool_names[m['tool_call_id']]:m['content'] for m in payload['messages'] if m['role']=='tool'}
        if 'READONLY_IMAGE' in user_text:
            call=('generate_image',{'prompt':'do not execute in read-only'}) if 'generate_image' not in results else None
            text='只读权限，未生成图片。'
        elif 'PROJECT_VISUAL' in user_text:
            call=('analyze_images',{'question':'识别项目参考图','images':['project.png']}) if 'analyze_images' not in results else None
            if not call:assert 'VISIBLE_REFERENCE_SILVER' in results['analyze_images']
            text='项目图片由视觉模型识别，主对话保持 DeepSeek。'
        else:
            assert 'VISIBLE_REFERENCE_SILVER' in user_text,'Coordinator did not receive automatic vision observations'
            if 'generate_image' not in results:call=('generate_image',{'prompt':'blue poster based on silver reference','use_reference':'编辑' in user_text})
            elif 'analyze_images' not in results:
                image_name=json.loads(results['generate_image'])['images'][0]['name'];call=('analyze_images',{'question':'检查生成图片的颜色和布局','images':[image_name]})
            else:
                assert 'VISIBLE_GENERATED_BLUE' in results['analyze_images'];call=None
            text='DeepSeek 已根据视觉分析调用 GPT 生成图片，并完成视觉复查。'
        message={'role':'assistant','content':text} if not call else {'role':'assistant','content':'','tool_calls':[{'id':'tool-'+str(len(calls)),'type':'function','function':{'name':call[0],'arguments':json.dumps(call[1])}}]}
        self.respond({'choices':[{'message':message}],'usage':{}})

servers=[]
for role in ('DeepSeek','GPT vision','GPT image'):
    server=ThreadingHTTPServer(('127.0.0.1',0),Fixture);server.role=role;servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
bases={server.role:f'http://127.0.0.1:{server.server_port}/v1' for server in servers}

def save_profile(name,base,model,protocol='chat',**fields):
    result=core.shared.save_settings({'name':name,'base_url':base,'api_key':KEYS[name],'chat_model':model,'image_model':'gpt-image-2' if name=='GPT image' else '', 'chat_api':protocol,**fields},'')
    models=core.shared.read_models(base,'',result['id'],protocol);core.shared.cache_models(models,result['id']);return result['id']

try:
    vision_id=save_profile('GPT vision',bases['GPT vision'],'gpt-5.5')
    image_id=save_profile('GPT image',bases['GPT image'],'gpt-image-2')
    ds_id=save_profile('DeepSeek',bases['DeepSeek'],'deepseek-chat',make_default=True,
        vision_api_profile_id=vision_id,vision_model='gpt-6.1-sol',image_api_profile_id=image_id,image_model_override='gpt-image-2.5-flare')
    attachment=core.shared.upload({'data':base64.b64encode(REFERENCE).decode(),'name':'参考图.png'})
    async def deny(*_):raise AssertionError('No commands or browser mutations expected')
    async def checks():
        samples=[]
        for mode,task in [('agent','依据参考图设计并生成海报'),('chat','依据参考图编辑图片')]:
            session=core.new_session(profile_id=ds_id);await core.execute_task(session,task,[attachment],mode,lambda _:None,deny)
            answer=session['messages'][-1];assert not answer.get('error'),answer['text']
            assert '视觉复查' in answer['text'] and answer['model']=='deepseek-chat'
            assert len(answer['images'])==1 and answer['images'][0]['model']=='gpt-image-2.5-flare'
            assert core.shared.image_path(answer['images'][0]['name']).read_bytes()==GENERATED
            tool_names=[e['name'] for e in session['events'] if e['type']=='tool_end'];assert tool_names==['analyze_images','generate_image','analyze_images']
            assert not any(b['type']=='image' for m in session['history'] for b in m['content'])
            samples.append(session)
        assert any(path.endswith('/images/edits') for _,_,path in calls)
        session=core.new_session(profile_id=ds_id);await core.execute_task(session,'PROJECT_VISUAL 检查项目图片',[],'agent',lambda _:None,deny)
        assert '由视觉模型识别' in session['messages'][-1]['text']
        native_id=save_profile('Claude vision',bases['GPT vision'],'claude-vision','anthropic')
        response_id=save_profile('Responses vision',bases['GPT vision'],'gpt-responses-vision','responses')
        for identifier,model in [(native_id,'claude-vision'),(response_id,'gpt-responses-vision')]:
            config={**api_profiles.get(ds_id),'vision_api_profile_id':identifier,'vision_model':model}
            tool=AnalyzeImagesTool(config,[attachment['name']],[attachment['name']],core.ROOT/'workspace',lambda _:None)
            result=await tool.execute(AnalyzeImagesInput(question='检查参考图'),None);assert 'VISIBLE_REFERENCE_SILVER' in result.output
        tool=AnalyzeImagesTool(api_profiles.get(ds_id),[attachment['name']],[attachment['name']],core.ROOT/'workspace',lambda _:None)
        before=len(calls)
        try:await tool.execute(AnalyzeImagesInput(question='不能读取项目外文件',images=['../private.png']),None)
        except ValueError:pass
        else:raise AssertionError('Vision tool read outside project')
        assert len(calls)==before
        captures=core.ROOT/'data'/'desktop'/'browser-captures';captures.mkdir(exist_ok=True);capture=captures/'owned.png';capture.write_bytes(REFERENCE)
        tool=AnalyzeImagesTool(api_profiles.get(ds_id),[],[],core.ROOT/'workspace',lambda _:None,pages={'page1':{'owner':'current','screenshot':str(capture)}},owner='current')
        assert 'VISIBLE_REFERENCE_SILVER' in (await tool.execute(AnalyzeImagesInput(question='读取页面截图',page_id='page1'),None)).output
        tool.owner='other'
        try:await tool.execute(AnalyzeImagesInput(question='不能读取其他 Agent 页面',page_id='page1'),None)
        except ValueError:pass
        else:raise AssertionError('Vision tool read another owner page')
        before=len([c for c in calls if c[0]=='GPT image' and c[1]=='POST'])
        core.save_preferences({**core.preferences(),'permission_mode':'readonly'})
        readonly=core.new_session(profile_id=ds_id);await core.execute_task(readonly,'READONLY_IMAGE',[],'agent',lambda _:None,deny)
        assert '只读权限' in readonly['messages'][-1]['text'] and not readonly['messages'][-1]['images']
        assert len([c for c in calls if c[0]=='GPT image' and c[1]=='POST'])==before
        core.save_preferences({**core.preferences(),'permission_mode':'standard'})
        return samples[0]
    sample=asyncio.run(checks())
    for path in core.DATA.glob('*.json'):
        assert not any(key in path.read_text('utf-8') for key in KEYS.values())
    from main import MainWindow
    from settings_panel import SettingsDialog
    from theme import STYLE
    application.setStyle('Fusion');application.setStyleSheet(STYLE);window=MainWindow();window.open_session(sample['id']);dialog=SettingsDialog(window)
    assert dialog.vision_api.currentData()==vision_id and dialog.vision.currentData()=='gpt-6.1-sol'
    assert dialog.image_api.currentData()==image_id and dialog.image.currentText()=='gpt-image-2.5-flare' and dialog.image.isEnabled()
    assert not dialog.vision.isEditable() and not dialog.image.isEditable()
    dialog.vision.setCurrentIndex(dialog.vision.findData('gpt-5.5'));dialog.image.setCurrentText('gpt-image-2');dialog.save()
    deadline=time.monotonic()+15
    while dialog.workers and time.monotonic()<deadline:application.processEvents();time.sleep(.01)
    assert not dialog.workers;config=api_profiles.get(ds_id)
    assert config['vision_model']=='gpt-5.5' and config['image_model_override']=='gpt-image-2'
    assert api_profiles.get(vision_id)['chat_model']=='gpt-5.5' and api_profiles.get(image_id)['image_model']=='gpt-image-2'
    dialog.reject();window.close()
    report={'status':'passed','fixture_only':True,'separate_http_endpoints':3,'workflow':['DeepSeek coordinator','GPT vision analysis','GPT image generation/edit','GPT vision review','DeepSeek final response'],
        'text_only_coordinator_receives_no_image_bytes':True,'native_claude_vision':'passed','responses_vision':'passed','project_and_owned_browser_images':'passed','readonly_blocks_generation':'passed','model_picker_and_route_save':'passed'}
    core.shared.atomic_json(core.ROOT/'logs'/'multimodal-verification.json',report);print(json.dumps(report,ensure_ascii=False))
finally:
    for server in servers:server.shutdown();server.server_close()
