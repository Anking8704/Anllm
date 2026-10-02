from __future__ import annotations
import base64, hashlib, ipaddress, json, mimetypes, os, re, secrets, socket, threading, uuid, webbrowser, shutil
from contextlib import ExitStack
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
import httpx

from runtime_paths import ROOT
APP = Path(__file__).resolve().parent
CONFIG = ROOT / 'config'
DATA = ROOT / 'data' / 'studio'
IMAGES = ROOT / 'images'
UPLOADS = DATA / 'uploads'
for directory in (CONFIG, DATA, IMAGES, UPLOADS): directory.mkdir(parents=True, exist_ok=True)
os.environ['OPENHARNESS_CONFIG_DIR'] = str(CONFIG)
os.environ['OPENHARNESS_DATA_DIR'] = str(ROOT / 'data')
os.environ['OPENHARNESS_LOGS_DIR'] = str(ROOT / 'logs')
from openharness.auth.manager import AuthManager
from openharness.config.settings import ProviderProfile

PORT = int(os.environ.get('OPENHARNESS_STUDIO_PORT', '18878'))
ORIGIN = f'http://127.0.0.1:{PORT}'
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.RLock()
SESSION_LOCKS = {}
JOBS = {}
SETTINGS_FILE = CONFIG / 'studio.json'
DEFAULTS = {'base_url': 'https://puppyrouter.com/v1', 'chat_model': 'gpt-6.1-sol',
    'image_model': 'gpt-image-2.5-flare', 'chat_api': 'auto', 'size': '1024x1024', 'credential_profile': 'puppyrouter-image'}
SYSTEM = ('你是一个自然、简洁的中文 AI 助手，可以对话、分析图片和创作图片。'
    '用户要求画图、生成图片、海报、插画、照片或修改参考图时，主动调用 generate_image，'
    '不要只解释步骤，也不要只提供提示词。把用户需求整理为完整提示词，不改变核心要求。'
    '有参考图且需要编辑或参考时设置 use_reference=true。没有参考图时生成新图片。'
    '工具完成后简短说明结果，不编造图片链接。聊天时正常回答。')
SCHEMA = {'type':'object','properties':{'prompt':{'type':'string','description':'完整的图片创作或编辑提示词'},
    'use_reference':{'type':'boolean','description':'是否使用当前参考图或上一张生成图片'}},'required':['prompt'], 'additionalProperties':False}
CHAT_TOOL = {'type':'function','function':{'name':'generate_image','description':'生成新图片，或根据参考图编辑图片。用户要求生图时主动调用。','parameters':SCHEMA}}
RESPONSE_TOOL = {'type':'function','name':'generate_image','description':CHAT_TOOL['function']['description'],'parameters':SCHEMA}

def atomic_json(path, value):
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('w',encoding='utf-8',buffering=65536) as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
        temporary.replace(path)
    finally:
        if temporary.exists():temporary.unlink()

def legacy_settings():
    with LOCK:
        saved = json.loads(SETTINGS_FILE.read_text(encoding='utf-8')) if SETTINGS_FILE.exists() else {}
        return {**DEFAULTS, **saved}

def credential(config):
    manager = AuthManager()
    name = config.get('credential_profile', 'puppyrouter-image')
    resolved = manager.settings.model_copy(update={'active_profile': name}).materialize_active_profile()
    return resolved.resolve_auth().value

def settings(profile_id=None):
    from api_profiles import get
    return get(profile_id)

def public_settings(profile_id=None):
    from api_profiles import public
    return public(profile_id)

def api_profiles():
    from api_profiles import listed
    return listed()

def valid_base(value):
    value = str(value).strip().rstrip('/')
    url = urlsplit(value)
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('请输入完整 API 地址，不要在地址中填写密钥。')
    if url.scheme != 'https' and url.hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('远程 API 地址请使用 HTTPS。')
    return value

def save_settings(value,profile_id=None):
    from api_profiles import save
    return save(value,profile_id)

def request(config, endpoint, *, payload=None, files=None, form=None):
    key = credential(config)
    with httpx.Client(timeout=httpx.Timeout(180,connect=20),trust_env=False,follow_redirects=False) as client:
        kwargs = {'headers':{'Authorization':'Bearer '+key}}
        if files: kwargs.update(files=files, data=form)
        elif payload is not None: kwargs['json'] = payload
        response = client.request('POST' if payload is not None or files else 'GET', config['base_url']+endpoint, **kwargs)
    try: body = response.json()
    except Exception: body = {}
    if not response.is_success:
        detail = body.get('error',{}) if isinstance(body,dict) else {}
        detail = detail.get('message','接口返回错误') if isinstance(detail,dict) else str(detail)
        error = ValueError(f'HTTP {response.status_code}: {str(detail).replace(key,"[密钥已隐藏]")}')
        error.status = response.status_code
        raise error
    return body

CATALOG_FILE = CONFIG / 'model-catalog.json'

def catalog_identity(base_url, key):
    return hashlib.sha256((valid_base(base_url)+'\0'+key).encode()).hexdigest()

def cached_models(profile_id=None):
    from api_profiles import models
    return models(profile_id)

def cache_models(models,profile_id=None):
    from api_profiles import cache
    return cache(models,profile_id)

def read_models(base_url=None,api_key='',profile_id=None,chat_api=None):
    from api_profiles import read
    return read(base_url,api_key,profile_id,chat_api)

def model_catalog():
    models=read_models();cache_models(models);return models

def session_id(value):
    return str(uuid.UUID(str(value)))

def load_session(identifier):
    path = DATA / (session_id(identifier)+'.json')
    if not path.exists(): raise ValueError('会话不存在。')
    return json.loads(path.read_text(encoding='utf-8'))

def save_session(session):
    session['updated'] = datetime.now().astimezone().isoformat()
    atomic_json(DATA/(session_id(session['id'])+'.json'), session)

def sessions():
    items = []
    for path in DATA.glob('*.json'):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            items.append({name:value.get(name) for name in ('id','title','updated')})
        except Exception: continue
    return sorted(items,key=lambda item:item.get('updated') or '',reverse=True)

def new_session():
    session = {'id':str(uuid.uuid4()),'title':'新会话','messages':[]}
    with LOCK: save_session(session)
    return session

def image_path(value):
    name = Path(str(value)).name
    if name != value or not re.fullmatch(r'[a-zA-Z0-9_.-]+',name): raise ValueError('无效图片名称。')
    for directory in (UPLOADS, IMAGES):
        path = directory/name
        if path.is_file(): return path
    raise ValueError('图片不存在。')

def image_extension(content):
    if content.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if content.startswith(b'\xff\xd8\xff'): return '.jpg'
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP': return '.webp'
    raise ValueError('请选择 PNG、JPG 或 WebP 图片。')

def upload(value):
    raw = base64.b64decode(value.get('data',''),validate=True)
    if not raw or len(raw)>25*1024*1024: raise ValueError('图片需要小于 25 MB。')
    name = 'upload-'+uuid.uuid4().hex+image_extension(raw)
    (UPLOADS/name).write_bytes(raw)
    return {'name':name,'label':str(value.get('name','参考图'))[:150],'url':'/assets/'+name}

def import_image(filename):
    path=Path(filename)
    if not path.is_file() or not 0<path.stat().st_size<=25*1024*1024:raise ValueError('图片需要小于 25 MB。')
    with path.open('rb') as stream:extension=image_extension(stream.read(16))
    name='upload-'+uuid.uuid4().hex+extension;target=UPLOADS/name
    shutil.copyfile(path,target)
    if target.stat().st_size>25*1024*1024:
        target.unlink();raise ValueError('图片需要小于 25 MB。')
    return {'name':name,'label':path.name[:150],'url':'/assets/'+name}

def download_image(url):
    parts = urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or parts.username: raise ValueError('不支持的平台图片地址。')
    for result in socket.getaddrinfo(parts.hostname,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(result[4][0]).is_global: raise ValueError('拒绝访问非公网图片地址。')
    with httpx.Client(timeout=60,trust_env=False,follow_redirects=False) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content

def generate_image(config, prompt, references):
    params = {'model':config['image_model'],'prompt':str(prompt),'n':1,'size':config['size']}
    if references:
        with ExitStack() as stack:
            files=[]
            for name in references:
                path=image_path(name)
                files.append(('image' if len(references)==1 else 'image[]',(path.name,stack.enter_context(path.open('rb')),mimetypes.guess_type(path.name)[0])))
            result=request(config,'/images/edits',files=files,form={name:str(value) for name,value in params.items()})
    else: result = request(config,'/images/generations',payload=params)
    pictures = []
    for item in result.get('data',[]):
        if item.get('b64_json'): raw = base64.b64decode(item['b64_json'],validate=True)
        elif str(item.get('url','')).startswith('data:image/'):
            raw = base64.b64decode(item['url'].split(';base64,',1)[1],validate=True)
        elif item.get('url'): raw = download_image(item['url'])
        else: continue
        filename = 'image-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:10]+image_extension(raw)
        (IMAGES/filename).write_bytes(raw)
        pictures.append({'name':filename,'url':'/assets/'+filename,'prompt':str(prompt),'model':config['image_model']})
    if not pictures: raise ValueError('接口没有返回图片。')
    return pictures

def model_messages(session):
    result = [{'role':'system','content':SYSTEM}]
    for item in session['messages'][-24:]:
        if item.get('error'): continue
        if item['role']=='user' and item.get('attachments'):
            content = [{'type':'text','text':item['text']}]
            for attachment in item['attachments']:
                path = image_path(attachment['name'])
                mime = mimetypes.guess_type(path.name)[0]
                content.append({'type':'image_url','image_url':{'url':'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()}})
            result.append({'role':'user','content':content})
        else: result.append({'role':item['role'],'content':item.get('text') or '已生成图片。'})
    return result

def responses_input(messages):
    result = []
    for item in messages:
        if item['role']=='system': continue
        if item['role']=='tool':
            result.append({'type':'function_call_output','call_id':item['tool_call_id'],'output':item['content']})
            continue
        for call in item.get('tool_calls',[]):
            result.append({'type':'function_call','call_id':call['id'],'name':call['function']['name'],'arguments':call['function']['arguments']})
        content = item.get('content')
        if not content: continue
        if isinstance(content,list):
            content = [{'type':'input_text','text':part['text']} if part['type']=='text' else {'type':'input_image','image_url':part['image_url']['url']} for part in content]
        result.append({'role':item['role'],'content':content})
    return result

def text_call(config, messages, api):
    if api=='responses':
        payload = {'model':config['chat_model'],'instructions':SYSTEM,'input':responses_input(messages),
            'tools':[RESPONSE_TOOL],'store':False,'max_output_tokens':4096}
        body = request(config,'/responses',payload=payload)
        text, calls = [], []
        for item in body.get('output',[]):
            if item.get('type')=='function_call':
                calls.append({'id':item['call_id'],'type':'function','function':{'name':item['name'],'arguments':item['arguments']}})
            for part in item.get('content',[]):
                if part.get('type')=='output_text': text.append(part.get('text',''))
        return {'role':'assistant','content':'\n'.join(text),'tool_calls':calls}
    payload = {'model':config['chat_model'],'messages':messages,'tools':[CHAT_TOOL], 'tool_choice':'auto','stream':False}
    body = request(config,'/chat/completions',payload=payload)
    choices = body.get('choices',[])
    if not choices: raise ValueError('对话接口没有返回消息。')
    return choices[0]['message']

def explicit_image_request(text):
    if re.search(r'不要.*(生图|画图|生成图片)|如何|怎么|教程|能不能',text[:24]): return False
    return bool(re.search(r'生图|画(?:一|个|张|幅)|(?:生成|制作|绘制|画出).{0,20}(?:图片|图像|海报|插画|照片|壁纸|头像|图)|^(?:draw|generate an? image|create an? image|make an? picture)\b',text,re.I))

