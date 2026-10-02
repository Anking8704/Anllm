"""Offline package verification; no account credentials or paid requests."""
import asyncio,json,os,sys,tempfile,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import core,browser_bridge
from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage,TextBlock,ToolUseBlock

class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/v1/models':body=json.dumps({'data':[{'id':'local-agent'},{'id':'local-image'}]}).encode();mime='application/json'
        else:
            body=b'<title>Anllm Package</title><input aria-label="Name"><button onclick="document.querySelector(\'#done\').textContent=document.querySelector(\'input\').value">Confirm</button><p id="done"></p>';mime='text/html'
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

class FakeModel:
    def __init__(self):self.calls=0
    async def stream_message(self,req):
        steps=[('ask_user',{'questions':[{'question':'选择文件内容','options':['silver','blue']}]}),
            ('write_file',{'path':'answer.txt','content':'silver'}),('run_command',{'command':"Write-Output 'ANLLM_PACKAGE_OK'"})]
        if self.calls<len(steps):
            name,args=steps[self.calls];blocks=[ToolUseBlock(id='package-'+str(self.calls),name=name,input=args)]
        else:blocks=[TextBlock(text='已根据用户回答完成验证。')]
        self.calls+=1
        yield ApiMessageCompleteEvent(message=ConversationMessage(role='assistant',content=blocks),usage=UsageSnapshot())

async def task_checks(root):
    checked=[]
    for mode in ('readonly','standard','full'):
        project=root/mode;project.mkdir();data=root/(mode+'-data');data.mkdir();backups=data/'backups';backups.mkdir()
        approvals=[];questions=[]
        async def ask(value):questions.append(value);await asyncio.sleep(.02);return {'cancelled':False,'answers':[{'question':value[0]['question'],'answer':'silver'}]}
        async def approve(*args):approvals.append(args);return False
        with patch.object(core,'DATA',data),patch.object(core,'BACKUPS',backups),patch.object(core,'PREFS',root/(mode+'.json')):
            core.save_preferences({'workspace':str(project),'permission_mode':mode,'max_turns':8,'parallel_agents':2})
            session=core.new_session();model=FakeModel();await core.execute_task(session,'验证交互和权限',[],'agent',lambda _:None,approve,model,ask=ask)
            assert len(questions)==1 and model.calls==4
            outputs=[e['output'] for e in session['events'] if e['type']=='tool_end']
            assert any('silver' in result for result in outputs)
            assert (project/'answer.txt').exists()==(mode!='readonly')
            assert not approvals,'Simple output command should not request confirmation'
            assert any('ANLLM_PACKAGE_OK' in output for output in outputs)==(mode!='readonly')
            checked.append(mode)
    return checked

def verify_package():
    report={'frozen':bool(getattr(sys,'frozen',False)),'executable':sys.executable,'data_root':str(core.ROOT)}
    try:
        with tempfile.TemporaryDirectory(dir=core.ROOT/'cache',prefix='package-check-') as temporary:
            root=Path(temporary);report['permission_modes']=asyncio.run(task_checks(root))
            server=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                url='http://127.0.0.1:'+str(server.server_port)
                assert core.shared.read_models(url+'/v1','LOCAL_TEST_ONLY')==['local-agent','local-image']
                service=browser_bridge.BrowserService(headless=True,profile=root/'browser',captures=root/'captures')
                async def browser():
                    state=await service.call('open','verification',url);page=state['page_id']
                    name=next(e['ref'] for e in state['elements'] if e.get('label')=='Name')
                    state=await service.call('act','verification',page,name,'fill','BROWSER_PACKAGE_OK')
                    confirm=next(e['ref'] for e in state['elements'] if e.get('label')=='Confirm')
                    state=await service.call('act','verification',page,confirm,'click')
                    assert 'BROWSER_PACKAGE_OK' in state['text']
                try:asyncio.run(browser());report['bundled_browser']='passed'
                finally:service.shutdown()
            finally:server.shutdown();server.server_close()
            report['models_and_questions']='passed';report['status']='passed'
    except Exception as error:
        import traceback
        report['status']='failed';report['error']=core.scrub(traceback.format_exc());raise
    finally:core.shared.atomic_json(core.ROOT/'logs'/'package-verification.json',report)

if __name__=='__main__':verify_package()
