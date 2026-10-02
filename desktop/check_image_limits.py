"""Many-image import, image-only messages and low-overhead galleries."""
import asyncio,base64,json,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QObject,QTimer,Signal,Qt,QSize
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage,TextBlock,ImageBlock
import core,modal_tools
from main import MainWindow,MessageCard
from image_assets import CACHE,thumbnail

app=QApplication.instance() or QApplication([])
source=core.ROOT/'workspace'/'reference.png';image=QImage(256,192,QImage.Format_RGB32);image.fill(QColor('#ccddef'));assert image.save(str(source))
window=MainWindow();ticks=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
original=core.shared.import_image
def slow_import(path):time.sleep(.006);return original(path)
with patch.object(core.shared,'import_image',side_effect=slow_import):
    window.add_files([str(source)]*32);window.paste_image(image)
    deadline=time.monotonic()+10
    while window.import_worker or window.import_queue:
        app.processEvents();time.sleep(.002)
        assert time.monotonic()<deadline,'Background import did not finish'
timer.stop();assert len(ticks)>8,'Import blocked the UI event loop'
assert len(window.attachments)==33 and window.attachment_list.count()==33
assert window.send_button.isEnabled() and not window.background_workers
attachments=list(window.attachments)
before=CACHE.decodes
card=MessageCard({'id':'many','role':'user','text':'','attachments':attachments})
assert CACHE.decodes==before,'Hidden reference gallery eagerly decoded every image'
assert card.text.isHidden()
picture=thumbnail(source,QSize(56,56));again=thumbnail(source,QSize(56,56))
assert picture.size()==again.size() and picture.width()<=56 and picture.height()<=56
assert CACHE.decodes==before+1 and CACHE.used<=CACHE.budget
card.show();app.processEvents();card.hide()

class InspectModel:
    async def stream_message(self,req):
        blocks=req.messages[-1].content
        assert len([block for block in blocks if isinstance(block,ImageBlock)])==33
        assert any(isinstance(block,TextBlock) and '分析这些图片' in block.text for block in blocks)
        yield ApiMessageCompleteEvent(message=ConversationMessage(role='assistant',content=[TextBlock(text='看到了全部 33 张图片。')]),usage=UsageSnapshot())
async def deny(*_):raise AssertionError('Image analysis should not request execution')
async def check_chat():
    for mode in ('chat','agent'):
        session=core.new_session()
        await core.execute_task(session,'',attachments,mode,lambda _:None,deny,InspectModel())
        assert not session['messages'][-1].get('error') and session['messages'][0]['text']==''
        assert session['title']=='图片消息 · 33 张'
        assert all(not block.get('data') for item in session['history'] for block in item['content'] if block['type']=='image')
        assert any(item['id']==session['id'] for item in core.sessions())
asyncio.run(check_chat())

class Vision:
    def __init__(self,config):pass
    async def stream_message(self,req):
        assert len([block for block in req.messages[0].content if isinstance(block,ImageBlock)])==33
        yield ApiMessageCompleteEvent(message=ConversationMessage(role='assistant',content=[TextBlock(text='全部参考图均已分析')]),usage=UsageSnapshot())
tool=modal_tools.AnalyzeImagesTool({},lambda:[item['name'] for item in attachments],lambda:[item['name'] for item in attachments],core.ROOT/'workspace',lambda _:None)
with patch('modal_tools.vision_config',return_value={'name':'本地视觉验证','chat_model':'fixture'}),patch('core.CompatibleClient',Vision):
    result=asyncio.run(tool.execute(modal_tools.AnalyzeImagesInput(question='检查所有参考图',images=[item['name'] for item in attachments]),None))
    assert len(json.loads(result.output)['images'])==33

streams=[]
def image_request(config,endpoint,**kwargs):
    assert endpoint=='/images/edits' and len(kwargs['files'])==33
    for field,(name,stream,mime) in kwargs['files']:
        assert field=='image[]' and hasattr(stream,'read') and not isinstance(stream,bytes)
        assert stream.read(8)==b'\x89PNG\r\n\x1a\n';streams.append(stream)
    return {'data':[{'b64_json':base64.b64encode(source.read_bytes()).decode()}]}
with patch.object(core.shared,'request',side_effect=image_request):
    generated=core.shared.generate_image({'image_model':'fixture','size':'1024x1024'},'参考全部图片',[item['name'] for item in attachments])
assert len(generated)==1 and all(stream.closed for stream in streams)
def image_only(config,prompt,references):
    assert prompt and len(references)==33
    return [dict(generated[0])]
with patch('api_profiles.image_config',return_value={'name':'本地图片验证','image_model':'fixture'}),patch.object(core.shared,'generate_image',side_effect=image_only):
    session=core.new_session()
    asyncio.run(core.execute_task(session,'',attachments,'image',lambda _:None,deny))
    assert not session['messages'][-1].get('error') and session['messages'][-1]['images']

class StubWorker(QObject):
    event=Signal(object);result=Signal(object);finished=Signal()
    captured=[]
    def __init__(self,session,text,files,mode):super().__init__();self.captured.append((text,list(files),mode))
    def start(self):pass
fixture_config={**core.shared.public_settings(window.current['api_profile_id']),'key_configured':True}
with patch('main.AgentWorker',StubWorker),patch.object(core.shared,'public_settings',return_value=fixture_config),patch.object(core.shared,'cached_models',return_value=[window.current['chat_model']]):
    window.prompt.clear();window.send();assert window.worker and StubWorker.captured[-1][0]=='' and len(StubWorker.captured[-1][1])==33
window.worker=None;window.attachments=[];window.render_attachments();window.send();assert window.worker is None
long_session=core.new_session();long_session['messages']=[{'id':str(i),'role':'user','text':'消息 '+str(i)} for i in range(100)]
core.save_session(long_session);window.open_session(long_session['id']);assert len(window.cards)==40
window.show_more_messages();assert len(window.cards)==80
assert len(core.load_session(long_session['id'])['messages'])==100
window.close();app.processEvents()
report={'status':'passed','imported_images':33,'clipboard_after_more_than_four':True,'background_import_keeps_ui_responsive':True,
    'image_only_ui_chat_agent_and_image_mode':True,'all_images_reach_vision':True,'all_references_reach_image_edit':True,
    'multipart_uses_file_streams':True,'thumbnail_decode_is_lazy_and_bounded':True,
    'saved_history_has_no_inline_image_bytes':True,'history_paging_retains_all_messages':True}
core.shared.atomic_json(core.ROOT/'logs'/'image-performance-verification.json',report);print(json.dumps(report,ensure_ascii=False))
