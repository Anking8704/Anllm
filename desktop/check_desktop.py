"""Real Windows input against a disposable fixture; no personal apps are operated."""
import asyncio,ctypes,json,os,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
from desktop_control import DesktopService,ActionInput,InspectInput,WindowsInput,tools,action_request,key_codes
from desktop_native import WindowsDesktop,Input
import core

source=Path(__file__).parent;state_file=core.ROOT/'workspace'/'desktop-fixture.json'
environment=dict(os.environ);environment.pop('QT_QPA_PLATFORM',None)
command=[sys.executable,'--desktop-fixture',str(state_file)] if getattr(sys,'frozen',False) else [sys.executable,str(source/'desktop_fixture.py'),str(state_file)]
fixture_log=(core.ROOT/'logs'/'desktop-fixture.log').open('w',encoding='utf-8')
process=subprocess.Popen(command,env=environment,creationflags=subprocess.CREATE_NO_WINDOW,stdout=fixture_log,stderr=fixture_log)

def state():
    try:return json.loads(state_file.read_text('utf-8'))
    except (OSError,ValueError):return {}
def wait(condition):
    deadline=time.monotonic()+15
    while not condition():
        assert process.poll() is None,'Fixture exited unexpectedly';time.sleep(.03)
        assert time.monotonic()<deadline,'Fixture input did not arrive'

service=DesktopService(captures=core.ROOT/'data'/'desktop'/'screen-captures');owner='verification:main';service.begin(owner)
report={}
try:
    wait(lambda:state().get('ready'))
    windows=service.windows(owner)
    window=next(value for value in windows if value['pid']==process.pid and value['title']=='Anllm Desktop Verification')
    assert ctypes.sizeof(Input)==40
    service.focus(owner,window['id'])
    frame=service.inspect(owner,window['id'])
    assert Path(frame['screenshot']).is_file() and Path(frame['screenshot']).stat().st_size>1000
    assert frame['elements'],'UI Automation returned no controls: '+getattr(service.native,'last_automation_error','no details')
    def element(frame,name):return next(row for row in frame['elements'] if row['name']==name)
    field=element(frame,'测试文本');assert field['type']==50004
    action=ActionInput(snapshot_id=frame['snapshot_id'],action='type',ref=field['ref'],text='桌面控制 ✓ Test 123',purpose='验证中文输入')
    service.act(owner,action);wait(lambda:state().get('text')=='桌面控制 ✓ Test 123')
    try:service.act(owner,action);raise AssertionError('Used snapshot allowed a second action')
    except ValueError:pass
    frame=service.inspect(owner,window['id']);field=element(frame,'测试文本')
    service.act(owner,ActionInput(snapshot_id=frame['snapshot_id'],action='type',ref=field['ref'],text='替换成功',select_all=True,purpose='替换测试内容'))
    wait(lambda:state().get('text')=='替换成功')
    frame=service.inspect(owner,window['id'])
    service.act(owner,ActionInput(snapshot_id=frame['snapshot_id'],action='press',keys='Enter',purpose='验证按键'))
    wait(lambda:state().get('enter')==1)
    frame=service.inspect(owner,window['id']);button=element(frame,'普通按钮')
    service.act(owner,ActionInput(snapshot_id=frame['snapshot_id'],action='click',ref=button['ref'],purpose='点击测试按钮'))
    wait(lambda:state().get('clicks')==1)
    frame=service.inspect(owner,window['id']);password=next(row for row in frame['elements'] if row['password'])
    try:service.act(owner,ActionInput(snapshot_id=frame['snapshot_id'],action='type',ref=password['ref'],text='never typed',purpose='验证密码保护'));raise AssertionError('Password accepted')
    except ValueError:pass
    # Use the UIA group bounds when available, otherwise a known point inside our own fixture.
    frame=service.inspect(owner,window['id']);pad=next((row for row in frame['elements'] if row['name']=='测试拖动区域'),None)
    if pad:
        r=pad['bounds'];x=(r[0]+r[2])//2;y=(r[1]+r[3])//2
    else:x=frame['image_size'][0]//2;y=round(frame['image_size'][1]*.75)
    for kind,extra,predicate in (
        ('double_click',{},lambda:state().get('double',0)>0),
        ('click',{'button':'right'},lambda:state().get('right',0)>0),
        ('scroll',{'amount':-3},lambda:state().get('wheel',0)<0),
        ('drag',{'end_x':x+40,'end_y':y+20},lambda:state().get('released',0)>=3),
    ):
        frame=service.inspect(owner,window['id']);service.act(owner,ActionInput(snapshot_id=frame['snapshot_id'],action=kind,x=x,y=y,purpose='验证测试区域 '+kind,**extra));wait(predicate)
    frame=service.inspect(owner,window['id'])
    # Moving a window invalidates old coordinates instead of clicking the wrong app.
    native=service.native;rect=frame['rect']
    native.user.SetWindowPos(window['hwnd'],None,rect[0]+20,rect[1]+20,0,0,1|4)
    try:service.act(owner,ActionInput(snapshot_id=frame['snapshot_id'],action='click',x=x,y=y,purpose='验证旧坐标拒绝'));raise AssertionError('Moved window used old coordinates')
    except ValueError:pass
    frame=service.inspect(owner,window['id']);service.cancel(owner)
    try:service.act(owner,ActionInput(snapshot_id=frame['snapshot_id'],action='press',keys='Enter',purpose='验证停止'));raise AssertionError('Cancelled task accepted input')
    except ValueError:pass
    service.end(owner);assert not service.frames and not service.stops and not service.consents
    service.begin(owner);service.windows(owner)

    async def permission_checks():
        confirmations=[]
        async def deny(title,request,detail):confirmations.append(request);return False
        registry={tool.name:tool for tool in tools(owner,{},lambda _:None,deny,'standard',service)}
        denied=await registry['desktop_inspect'].execute(InspectInput(window_id=window['id'],question=''),None)
        assert denied.is_error and confirmations and confirmations[-1]['kind']=='desktop'
        assert '查看' in confirmations[-1]['summary']
        async def approve(*_):return True
        registry={tool.name:tool for tool in tools(owner,{},lambda _:None,approve,'readonly',service)}
        viewed=await registry['desktop_inspect'].execute(InspectInput(window_id=window['id'],question=''),None)
        assert not viewed.is_error
        new_frame=service.frames[owner]
        blocked=await registry['desktop_action'].execute(ActionInput(snapshot_id=new_frame['snapshot_id'],action='press',keys='Enter',purpose='只读验证'),None)
        assert blocked.is_error
        registry={tool.name:tool for tool in tools(owner,{},lambda _:None,deny,'standard',service)}
        service.consents[owner].add(window['id'])
        denied=await registry['desktop_action'].execute(ActionInput(snapshot_id=new_frame['snapshot_id'],action='click',x=x,y=y,purpose='验证拒绝'),None)
        assert denied.is_error and not new_frame['used']
    asyncio.run(permission_checks())
    # Exercise the actual Agent query loop and the screenshot-to-vision route.
    from openharness.api.client import ApiMessageCompleteEvent
    from openharness.api.usage import UsageSnapshot
    from openharness.engine.messages import ConversationMessage,TextBlock,ImageBlock,ToolUseBlock,ToolResultBlock
    class Vision:
        calls=0
        def __init__(self,config):pass
        async def stream_message(self,request):
            assert any(isinstance(block,ImageBlock) and block.data for block in request.messages[0].content)
            assert '截图像素' in request.messages[0].text
            type(self).calls+=1
            yield ApiMessageCompleteEvent(message=ConversationMessage(role='assistant',content=[TextBlock(text='测试窗口中有文本输入框和普通按钮。')]),usage=UsageSnapshot())
    class Agent:
        def __init__(self):self.calls=0
        async def stream_message(self,request):
            assert {'desktop_windows','desktop_focus','desktop_inspect','desktop_action'} <= {item['name'] for item in request.tools}
            step=self.calls;self.calls+=1
            if step==0:name,args='desktop_windows',{}
            elif step==1:
                result=next(block for block in request.messages[-1].content if isinstance(block,ToolResultBlock))
                found=json.loads(result.content)['windows']
                actual=next(item for item in found if item['pid']==process.pid)
                name,args='desktop_inspect',{'window_id':actual['id'],'question':'识别测试窗口的输入框','purpose':'验证 Agent 桌面观察'}
            elif step==2:
                result=next(block for block in request.messages[-1].content if isinstance(block,ToolResultBlock))
                actual=json.loads(result.content);assert actual['analysis']
                field=next(item for item in actual['elements'] if item['name']=='测试文本')
                name,args='desktop_action',{'snapshot_id':actual['snapshot_id'],'action':'type','ref':field['ref'],
                    'text':'Agent 桌面闭环通过','select_all':True,'purpose':'填写独立测试窗口'}
            elif step==3:
                result=next(block for block in request.messages[-1].content if isinstance(block,ToolResultBlock))
                assert json.loads(result.content)['completed']
                name,args='desktop_inspect',{'window_id':window['id'],'question':'','purpose':'检查输入结果'}
            else:
                wait(lambda:state().get('text')=='Agent 桌面闭环通过')
                yield ApiMessageCompleteEvent(message=ConversationMessage(role='assistant',content=[TextBlock(text='已完成桌面输入并重新观察。')]),usage=UsageSnapshot());return
            yield ApiMessageCompleteEvent(message=ConversationMessage(role='assistant',content=[ToolUseBlock(id='desktop-loop-'+str(step),name=name,input=args)]),usage=UsageSnapshot())
    async def check_loop():
        prefs=core.preferences();core.save_preferences({**prefs,'permission_mode':'full','max_turns':8})
        session=core.new_session();client=Agent();events=[]
        async def unexpected(*_):raise AssertionError('Full access requested approval')
        with patch.object(core,'CompatibleClient',Vision),patch('api_profiles.vision_config',return_value={'name':'本地视觉验证','chat_model':'fixture'}):
            await core.execute_task(session,'在专用测试窗口输入测试内容并查看结果',[],'agent',events.append,unexpected,client,desktop_service=service)
        assert client.calls==5 and Vision.calls==1 and not session['messages'][-1].get('error'),session['messages'][-1]
        assert len([event for event in events if event['type']=='desktop'])==2
        assert session['desktop_capture']['window']['id']==window['id']
        assert session['id']+':main' not in service.stops
        assert core.load_session(session['id'])['desktop_capture']['screenshot']==session['desktop_capture']['screenshot']
        core.save_preferences(prefs)
    asyncio.run(check_loop())
    assert key_codes('Ctrl+Shift+A')==[17,16,65]
    frame={'image_size':[1000,800],'rect':[-2000,-200,0,1400]}
    assert service.map_point(frame,500,100)==(-1000,0)
    try:service.map_point(frame,1000,0);raise AssertionError('Out-of-range point accepted')
    except ValueError:pass
    request=action_request(ActionInput(snapshot_id='x',action='click',x=2,y=2,purpose='发送测试消息'),window,{'name':'发送','type':50000},(2,2))
    assert not request['routine'] and '发送' in request['summary']
    report={'status':'passed','actual_windows_fixture_only':True,'native_64bit_input_abi':True,'ui_automation_control_refs':True,
        'real_window_screenshot':True,'unicode_and_select_all_input':True,'real_click_double_right_drag_scroll_keys':True,
        'protected_input_rejected':True,'used_snapshot_and_moved_window_rejected':True,'cancel_prevents_further_input':True,
        'read_only_and_denied_requests_prevent_input':True,'negative_monitor_origin_and_scaled_coordinates':True,
        'agent_query_loop_observe_act_verify':True,'configured_vision_receives_real_screenshot':True,'session_retains_latest_preview':True}
finally:
    service.end(owner)
    if process.poll() is None:process.terminate()
    process.wait(timeout=8)
    fixture_log.close()
core.shared.atomic_json(core.ROOT/'logs'/'desktop-verification.json',report)
print(json.dumps(report,ensure_ascii=False))
