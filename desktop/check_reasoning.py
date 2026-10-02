"""Native model ranges, per-task choices, exact payloads and thinking tool continuation."""
import asyncio,json
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QSystemTrayIcon
from openharness.api.client import ApiMessageRequest
from openharness.engine.messages import ConversationMessage,TextBlock,ToolResultBlock
import core,main,reasoning,api_profiles

cfg={'id':'fixture','chat_api':'chat','chat_model':'gpt-5.2','base_url':'https://example.invalid/v1'}
assert reasoning.options(cfg)==('none','low','medium','high','xhigh')
assert reasoning.options(cfg,'gpt-5')==('minimal','low','medium','high')
assert reasoning.options(cfg,'gpt-6.1-sol')==('low','medium','high','xhigh','max')
assert reasoning.options(cfg,'openai/gpt-5.2-2025-12-11')==reasoning.options(cfg)
assert not reasoning.options(cfg,'gpt-5.2-pro') and not reasoning.options(cfg,'gpt-4o')
assert reasoning.options({**cfg,'chat_api':'anthropic'},'claude-sonnet-4-6')==('low','medium','high','max')
assert reasoning.options(cfg,'gemini-3-pro-preview')==('low','high')
assert reasoning.options(cfg,'gemini-3-flash-preview')==('minimal','low','medium','high')
assert reasoning.options({**cfg,'model_capabilities':{'gpt-5.2':['low','high']}})==('low','high')
assert reasoning.catalog_options({'reasoning_effort':{'enum':['low','high','bad value']}})==['low','high']
assert reasoning.catalog_options({'supported_parameters':['reasoning_effort']}) is None

async def request(config):
    client=core.CompatibleClient(config);seen=[]
    async def post(endpoint,payload):
        seen.append((endpoint,payload))
        if endpoint=='/messages':return {'content':[{'type':'text','text':'ok'}]}
        if endpoint=='/responses':return {'output':[{'type':'message','content':[{'type':'output_text','text':'ok'}]}]}
        return {'choices':[{'message':{'content':'ok'}}]}
    client.post=post
    req=ApiMessageRequest(model=config['chat_model'],messages=[ConversationMessage.from_user_text('hello')],max_tokens=8192)
    assert [e async for e in client.stream_message(req)];return seen

for api in ('chat','responses'):
    endpoint,payload=asyncio.run(request({**cfg,'chat_api':api,'reasoning_effort':'xhigh'}))[0]
    assert payload.get('reasoning_effort')=='xhigh' if api=='chat' else payload.get('reasoning')=={'effort':'xhigh'}
    assert endpoint==('/chat/completions' if api=='chat' else '/responses')
    default=asyncio.run(request({**cfg,'chat_api':api}))[0][1];assert 'reasoning_effort' not in default and 'reasoning' not in default
try:asyncio.run(request({**cfg,'reasoning_effort':'max'}))
except ValueError:pass
else:raise AssertionError('Unsupported effort reached transport')

async def claude_loop():
    config={**cfg,'chat_api':'anthropic','chat_model':'claude-opus-4-6','reasoning_effort':'max'}
    client=core.CompatibleClient(config);seen=[]
    raw=[{'type':'thinking','thinking':'fixture reasoning','signature':'fixture signature'}, {'type':'tool_use','id':'fixture-call','name':'read_file','input':{'path':'notes.txt'}}]
    async def post(endpoint,payload):
        assert endpoint=='/messages' and payload['output_config']=={'effort':'max'} and payload['thinking']=={'type':'adaptive'};seen.append(payload)
        return {'content':raw if len(seen)==1 else [{'type':'text','text':'ok'}]}
    client.post=post;history=[ConversationMessage.from_user_text('read')]
    req=ApiMessageRequest(model=config['chat_model'],messages=history,max_tokens=8192)
    events=[e async for e in client.stream_message(req)];answer=events[-1].message
    history.extend([answer,ConversationMessage(role='user',content=[ToolResultBlock(tool_use_id='fixture-call',content='fixture text')])])
    req=ApiMessageRequest(model=config['chat_model'],messages=history,max_tokens=8192)
    events=[e async for e in client.stream_message(req)]
    assert seen[-1]['messages'][1]['content']==raw and events[-1].message.text=='ok'
asyncio.run(claude_loop())

async def native_continuation(api,model):
    context={};config={**cfg,'chat_api':api,'chat_model':model,'reasoning_effort':'high','provider_context':context}
    seen=[]
    async def post(endpoint,payload):
        seen.append(payload)
        if api=='responses':
            assert payload['reasoning']=={'effort':'high'}
            if len(seen)==1:return {'output':[{'type':'reasoning','id':'reasoning-id','encrypted_content':'opaque-fixture','summary':[]},{'type':'function_call','call_id':'native-call','name':'read_file','arguments':'{"path":"notes.txt"}'}]}
            assert payload['input'][1]['type']=='reasoning' and payload['input'][1]['encrypted_content']=='opaque-fixture'
            return {'output':[{'type':'message','content':[{'type':'output_text','text':'done'}]}]}
        assert payload['reasoning_effort']=='high'
        if len(seen)==1:return {'choices':[{'message':{'content':'','reasoning_content':'native-fixture','tool_calls':[{'id':'native-call','type':'function','function':{'name':'read_file','arguments':'{"path":"notes.txt"}'}}]}}]}
        assert payload['messages'][1]['reasoning_content']=='native-fixture'
        return {'choices':[{'message':{'content':'done','reasoning_content':'next-fixture'}}]}
    history=[ConversationMessage.from_user_text('read')]
    for turn in range(2):
        # Recreate the client from persisted context to exercise cross-turn continuation.
        client=core.CompatibleClient(config);client.post=post
        req=ApiMessageRequest(model=model,messages=history,max_tokens=8192,tools=[{'name':'read_file','description':'read','input_schema':{'type':'object','properties':{'path':{'type':'string'}}}}])
        events=[e async for e in client.stream_message(req)];answer=events[-1].message;history.append(answer)
        if turn==0:history.append(ConversationMessage(role='user',content=[ToolResultBlock(tool_use_id='native-call',content='fixture')]))
    assert answer.text=='done' and context
asyncio.run(native_continuation('chat','deepseek-flash'))
asyncio.run(native_continuation('responses','gpt-5.2'))

fixture_item={'id':'future-model','effort':{'supported_levels':['low','high','max']}}
catalog=api_profiles.ModelCatalog(['future-model'],{'future-model':reasoning.catalog_options(fixture_item)})
with patch.object(core.shared,'credential',return_value='LOCAL_FIXTURE_ONLY'):
    api_profiles.cache(catalog,'legacy')
    assert api_profiles.get('legacy')['model_capabilities']['future-model']==['low','high','max']

app=QApplication.instance() or QApplication([])
with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=False),patch.object(core.shared,'public_settings',return_value={**cfg,'key_configured':True}),patch.object(core.shared,'cached_models',return_value=['gpt-5.2','gpt-4o']):
    window=main.MainWindow();window.current.update(api_profile_id='fixture',chat_model='gpt-5.2');window.update_models()
    assert window.reasoning_button.count()==6 and window.reasoning_button.isEnabled()
    window.reasoning_button.setCurrentIndex(window.reasoning_button.findData('xhigh'));a=window.current['id']
    assert core.session_config({**window.current,'api_profile_id':'legacy','reasoning_choices':{'legacy/gpt-5.2':'xhigh'}})['reasoning_effort']=='xhigh'
    window.select_model('gpt-4o');window.update_models();assert not window.reasoning_button.isEnabled()
    window.select_model('gpt-5.2');window.update_models();assert window.reasoning_button.currentData()=='xhigh'
    assert core.load_session(a)['reasoning_choices']['fixture/gpt-5.2']=='xhigh'
    window.new_chat();window.current.update(api_profile_id='fixture',chat_model='gpt-5.2');window.update_models();assert window.reasoning_button.currentData()==''
    window.request_exit();app.processEvents()

report={'status':'passed','model_specific_native_ranges':True,'catalog_advertised_options_override_fallback':True,'unsupported_values_rejected_before_network':True,'default_omits_extra_parameters':True,'chat_and_responses_native_effort_payloads':True,'claude_native_effort_and_thinking_signature_preserved':True,'deepseek_and_responses_native_context_survives_client_recreation':True,'catalog_capabilities_persisted':True,'per_model_per_task_selection_persisted':True}
core.shared.atomic_json(core.ROOT/'logs'/'reasoning-verification.json',report);print(json.dumps(report,ensure_ascii=False))
