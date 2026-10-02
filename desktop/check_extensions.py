"""Isolated component checks: actual Edge actions + actual OpenHarness teammate loops."""
import asyncio
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch

import core,browser_bridge
from team import AgentTeam,TaskSpec
from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage,TextBlock,ToolUseBlock


HTML='''<!doctype html><meta charset=utf-8><title>Browser Fixture</title>
<style>body{font:22px sans-serif;padding:50px}input,button,select{font-size:22px;margin:15px;padding:12px}</style>
<h1>浏览器功能验证</h1><label>名称 <input aria-label="名称" id=name></label>
<label>密码 <input type=password aria-label="密码" value="DO_NOT_DISCLOSE"></label>
<button onclick="document.querySelector('#result').textContent='完成：'+document.querySelector('#name').value">确认更新</button>
<select aria-label="色彩"><option value=white>银白</option><option value=blue>蓝色</option></select>
<p id=result>尚未点击</p><a href=/next>下一页</a>'''


class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        body=(HTML if self.path!='/' and self.path!='/next' else ('<title>Next Page</title><h1>已经跳转</h1>' if self.path=='/next' else HTML)).encode()
        self.send_response(200);self.send_header('Content-Type','text/html;charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


class ChildClient:
    active=0;peak=0
    def __init__(self,spec): self.spec=spec;self.calls=0
    async def stream_message(self,req):
        ChildClient.active+=1;ChildClient.peak=max(ChildClient.peak,ChildClient.active)
        try:
            await asyncio.sleep(.12)
            if self.calls==0: blocks=[ToolUseBlock(id=self.spec.name+'-read',name='read_file',input={'path':'source.txt'})]
            elif self.calls==1 and self.spec.write_paths:
                blocks=[ToolUseBlock(id=self.spec.name+'-write',name='write_file',input={'path':self.spec.write_paths[0],'content':self.spec.name+' finished'})]
            else: blocks=[TextBlock(text=self.spec.name+'：已检查并完成子任务。')]
            self.calls+=1
            yield ApiMessageCompleteEvent(message=ConversationMessage(role='assistant',content=blocks),usage=UsageSnapshot())
        finally: ChildClient.active-=1


async def check_browser(service,url):
    events=[];approvals=[]
    async def deny(*args): approvals.append(args);return False
    async def allow(*args): approvals.append(args);return True
    toolset={tool.name:tool for tool in browser_bridge.tools('test:main',events.append,allow,service=service)}
    async def invoke(name,**arguments):
        tool=toolset[name];result=await tool.execute(tool.input_model(**arguments),None)
        assert not result.is_error,result.output
        return json.loads(result.output)
    state=await invoke('browser_open',url=url)
    identifier=state['page_id'];assert '浏览器功能验证' in state['text']
    assert 'DO_NOT_DISCLOSE' not in json.dumps(state)
    password=next(e for e in state['elements'] if e['label']=='密码')
    result=await toolset['browser_fill'].execute(browser_bridge.FillInput(page_id=identifier,ref=password['ref'],text='no'),None)
    assert result.is_error and not approvals
    name=next(e for e in state['elements'] if e['label']=='名称')
    toolset['browser_fill'].approve=deny
    result=await toolset['browser_fill'].execute(browser_bridge.FillInput(page_id=identifier,ref=name['ref'],text='拒绝写入'),None)
    assert result.is_error
    state=await invoke('browser_read',page_id=identifier)
    assert next(e for e in state['elements'] if e['label']=='名称')['value']==''
    name=next(e for e in state['elements'] if e['label']=='名称');old_ref=name['ref']
    toolset['browser_fill'].approve=allow
    state=await invoke('browser_fill',page_id=identifier,ref=name['ref'],text='OpenHarness')
    result=await toolset['browser_click'].execute(browser_bridge.ClickInput(page_id=identifier,ref=old_ref),None)
    assert result.is_error,'Stale references accepted'
    click=next(e for e in state['elements'] if e['label']=='确认更新')
    state=await invoke('browser_click',page_id=identifier,ref=click['ref'])
    assert '完成：OpenHarness' in state['text']
    select=next(e for e in state['elements'] if e['label']=='色彩')
    state=await invoke('browser_select',page_id=identifier,ref=select['ref'],value='blue')
    assert next(e for e in state['elements'] if e['label']=='色彩')['value']=='blue'
    try: await service.call('read','another-owner',identifier)
    except ValueError: pass
    else: raise AssertionError('Page owner isolation failed')
    assert events and Path(events[-1]['browser']['screenshot']).exists()
    return identifier


async def check_team(workspace,data,backup):
    with patch.object(core,'DATA',data),patch.object(core,'BACKUPS',backup),patch.object(core,'PREFS',data/'prefs.json'):
        core.save_preferences({'workspace':str(workspace),'max_turns':8,'parallel_agents':3})
        session=core.new_session();events=[]
        async def approve(*args): raise AssertionError('Worker should not execute commands')
        team=AgentTeam(session,core.shared.settings(),events.append,approve,lambda _:None,client_factory=ChildClient)
        tasks=[TaskSpec(name='frontend',task='read and implement',write_paths=['front.txt']),TaskSpec(name='tests',task='read and test',write_paths=['tests.txt'])]
        results=await team.delegate(tasks)
        assert ChildClient.peak>=2,'Workers did not run concurrently'
        assert all(item['status']=='completed' for item in results)
        assert (workspace/'front.txt').read_text()=='frontend finished' and (workspace/'tests.txt').read_text()=='tests finished'
        assert len(session['changes'])==2 and len(core.load_session(session['id'])['agents'])==2
        try: await team.delegate([TaskSpec(name='one',task='a',write_paths=['src/']),TaskSpec(name='two',task='b',write_paths=['src/x.txt'])])
        except ValueError: pass
        else: raise AssertionError('Overlapping scopes accepted')
        team.claims['scope']=[(workspace/'front.txt',False)]
        try: team.allow_write('scope',workspace/'tests.txt')
        except ValueError: pass
        else: raise AssertionError('Worker escaped assigned scope')
        try: team.allow_write('main',workspace/'front.txt')
        except ValueError: pass
        else: raise AssertionError('Main agent overwrote active worker file')
        team.claims.clear()
        # Stop one teammate while another finishes normally.
        class SlowClient(ChildClient):
            async def stream_message(self,req):
                if self.spec.name=='slow': await asyncio.sleep(20)
                async for event in super().stream_message(req): yield event
        team.client_factory=SlowClient
        delegated=asyncio.create_task(team.delegate([TaskSpec(name='slow',task='wait'),TaskSpec(name='fast',task='inspect')]))
        while not any(record['name']=='slow' and record['status']=='running' for record in session['agents']): await asyncio.sleep(.02)
        identifier=next(record['id'] for record in session['agents'] if record['name']=='slow')
        assert team.cancel(identifier)
        results=await delegated
        assert next(r for r in results if r['name']=='slow')['status']=='stopped'
        assert next(r for r in results if r['name']=='fast')['status']=='completed'
        await team.close()


with tempfile.TemporaryDirectory(dir=Path(__file__).parent,prefix='extensions-') as temporary:
    root=Path(temporary);workspace=root/'project';workspace.mkdir();(workspace/'source.txt').write_text('fixture source',encoding='utf-8')
    data=root/'sessions';backup=data/'backups';backup.mkdir(parents=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=server.serve_forever,daemon=True).start()
    service=browser_bridge.BrowserService(headless=True,profile=root/'profile',captures=root/'captures')
    try:
        identifier=asyncio.run(check_browser(service,f'http://127.0.0.1:{server.server_port}/'))
        # A fresh asyncio loop still controls the same browser/tab.
        state=asyncio.run(service.call('read','test:main',identifier));assert '完成：OpenHarness' in state['text']
        asyncio.run(check_team(workspace,data,backup))
    finally: service.shutdown();server.shutdown();server.server_close()
print('PASS: actual Edge navigation/read/fill/click/select, refused actions, password masking, stale refs, ownership, cross-loop browser persistence, real parallel OpenHarness loops, scope conflicts, saved changes/results, individual cancellation.')
