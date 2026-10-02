"""Named API connections. Credentials stay in AuthManager, never in conversations."""
from __future__ import annotations
import hashlib,json,re,threading,uuid
from pathlib import Path
import httpx
from openharness.auth.manager import AuthManager
from openharness.config.settings import ProviderProfile

LOCK=threading.RLock()

class ModelCatalog(list):
    def __init__(self,models,capabilities=None):
        super().__init__(models);self.capabilities=capabilities or {}

def store_path():
    import desktop_shared as shared
    return shared.CONFIG/'api-profiles.json'

def store():
    import desktop_shared as shared
    with LOCK:
        path=store_path()
        if path.exists():return json.loads(path.read_text('utf-8'))
        legacy=shared.legacy_settings()
        profile={**legacy,'id':'legacy','name':'原有 API','models':[],'model_identity':''}
        try:
            catalog=json.loads(shared.CATALOG_FILE.read_text('utf-8'))
            if catalog['identity']==shared.catalog_identity(legacy['base_url'],shared.credential(legacy)):
                profile.update(models=catalog['models'],model_identity=identity(legacy,shared.credential(legacy)))
        except Exception:pass
        value={'default_id':'legacy','profiles':{'legacy':profile}}
        shared.atomic_json(path,value)
        return value

def identity(config,key):
    return hashlib.sha256((config['base_url']+'\0'+key+'\0'+config.get('chat_api','auto')).encode()).hexdigest()

def get(profile_id=None):
    value=store();identifier=profile_id or value['default_id']
    if identifier not in value['profiles']:raise ValueError('该对话的 API 配置不存在，请重新选择 API。')
    return dict(value['profiles'][identifier])

def public(profile_id=None):
    import desktop_shared as shared
    config=get(profile_id)
    try:
        key=shared.credential(config);configured=bool(key);hint='•••• '+key[-4:] if key else '未配置'
    except Exception:configured=False;hint='未配置'
    return {k:v for k,v in config.items() if k not in ('credential_profile','models','model_identity')}|{'key_configured':configured,'key_hint':hint}

def listed():
    value=store()
    return [public(identifier)|{'is_default':identifier==value['default_id']} for identifier in value['profiles']]

def models(profile_id=None):
    import desktop_shared as shared
    try:
        config=get(profile_id)
        if config.get('model_identity')!=identity(config,shared.credential(config)):return []
        return list(config.get('models',[]))
    except Exception:return []

def cache(model_names,profile_id=None):
    import desktop_shared as shared
    with LOCK:
        value=store();config=get(profile_id)
        config.update(models=sorted(set(model_names)),model_identity=identity(config,shared.credential(config)))
        if hasattr(model_names,'capabilities'):config['model_capabilities']=model_names.capabilities
        else:config['model_capabilities']={k:v for k,v in config.get('model_capabilities',{}).items() if k in model_names}
        value['profiles'][config['id']]=config;shared.atomic_json(store_path(),value)

def save(fields,profile_id=None):
    import desktop_shared as shared
    with LOCK:
        value=store()
        # None updates the default for older callers; empty string explicitly creates a new profile.
        identifier=(value['default_id'] if profile_id is None else profile_id) or uuid.uuid4().hex
        old=value['profiles'].get(identifier)
        try:old_identity=identity(old,shared.credential(old)) if old else None
        except Exception:old_identity=None
        config={**shared.DEFAULTS,**(old or {}),**{key:fields[key] for key in ('name','base_url','chat_model','image_model','chat_api','size','image_api_profile_id','image_model_override','vision_api_profile_id','vision_model') if key in fields},'id':identifier}
        config['name']=str(config.get('name') or 'API 配置').strip()[:60]
        if not config['name']:raise ValueError('请填写配置名称。')
        if any(p['name'].casefold()==config['name'].casefold() and p['id']!=identifier for p in value['profiles'].values()):raise ValueError('配置名称已存在，请换一个名称。')
        config['base_url']=shared.valid_base(config['base_url'])
        if config['chat_api'] not in ('auto','chat','responses','anthropic'):raise ValueError('请选择有效接口。')
        if config['size'] not in ('1024x1024','1536x1024','1024x1536'):raise ValueError('请选择有效图片尺寸。')
        for field in ('chat_model','image_model','image_model_override','vision_model'):
            config[field]=str(config.get(field) or '').strip()
            if len(config[field])>150:raise ValueError('模型名称过长。')
        image_id=config.get('image_api_profile_id','')
        if image_id and image_id!=identifier and image_id not in value['profiles']:raise ValueError('图片 API 不存在。')
        vision_id=config.get('vision_api_profile_id','')
        if vision_id and vision_id!=identifier and vision_id not in value['profiles']:raise ValueError('视觉 API 不存在。')
        key=str(fields.get('api_key','')).strip()
        if not key and (not old or config['base_url']!=old['base_url']):raise ValueError('新建配置或更换地址时，请填写该服务的密钥。')
        if key:
            slot='anllm-'+identifier
            manager=AuthManager()
            native=config['chat_api']=='anthropic'
            manager.upsert_profile(slot,ProviderProfile(label=config['name'],provider='anthropic' if native else 'openai',api_format='anthropic' if native else 'openai',
                auth_source='anthropic_api_key' if native else 'openai_api_key',default_model=config['chat_model'],base_url=config['base_url'],credential_slot=slot))
            manager.store_profile_credential(slot,'api_key',key);config['credential_profile']=slot
        elif not shared.credential(config):raise ValueError('请填写 API 密钥。')
        if not old or identity(config,shared.credential(config))!=old_identity:
            config.update(models=[],model_identity='',model_capabilities={})
        value['profiles'][identifier]=config
        if fields.get('make_default'):value['default_id']=identifier
        shared.atomic_json(store_path(),value)
        return public(identifier)

def read(base_url=None,api_key='',profile_id=None,chat_api=None):
    import desktop_shared as shared
    config=get(profile_id) if profile_id is not None else get()
    base=shared.valid_base(base_url or config['base_url']);protocol=chat_api or config['chat_api']
    key=api_key.strip()
    if not key:
        if base!=config['base_url'] or profile_id=='':raise ValueError('新建配置或更换地址时，请填写该服务的密钥。')
        try:key=shared.credential(config)
        except Exception:raise ValueError('请填写 API 密钥。') from None
    if not key:raise ValueError('请填写 API 密钥。')
    headers={'x-api-key':key,'anthropic-version':'2023-06-01'} if protocol=='anthropic' else {'Authorization':'Bearer '+key}
    found=set();capabilities={};params={'limit':100} if protocol=='anthropic' else {}
    with httpx.Client(timeout=httpx.Timeout(40,connect=15),trust_env=False,follow_redirects=False) as client:
        for _ in range(30):
            response=client.get(base+'/models',headers=headers,params=params)
            try:body=response.json()
            except Exception:body={}
            if not response.is_success:
                error=body.get('error',{}) if isinstance(body,dict) else {}
                message=error.get('message','读取模型失败') if isinstance(error,dict) else str(error)
                raise ValueError(f'HTTP {response.status_code}: {message}'.replace(key,'[密钥已隐藏]'))
            import reasoning
            for item in body.get('data',[]):
                if not isinstance(item,dict) or not item.get('id'):continue
                model=str(item['id']);found.add(model);choices=reasoning.catalog_options(item)
                if choices is not None and reasoning.model_name(model) in reasoning.DEEPSEEK and 'none' not in choices:choices=['none',*choices]
                if choices is not None:capabilities[model]=choices
            if protocol!='anthropic' or not body.get('has_more'):break
            cursor=body.get('last_id')
            if not cursor or params.get('after_id')==cursor:raise ValueError('模型分页返回异常。')
            params['after_id']=cursor
        else:raise ValueError('模型分页过多，请检查服务地址。')
    if not found:raise ValueError('服务未返回可选择的模型。')
    return ModelCatalog(sorted(found),capabilities)

def image_config(config):
    selected=config.get('image_api_profile_id')
    result=get(selected) if selected and selected!=config['id'] else dict(config)
    if result['chat_api']=='anthropic':raise ValueError('Claude 原生 API 不提供生图接口，请在设置里选择已保存的图片 API。')
    result={**result,'image_model':config.get('image_model_override') or result.get('image_model',''),'size':config['size']}
    if not result.get('image_model'):raise ValueError('请先为图片 API 读取并选择图片模型。')
    if result['image_model'] not in models(result['id']):raise ValueError('请先为生图 API 读取模型，再选择生图模型。')
    return result

def vision_config(config):
    selected=config.get('vision_api_profile_id')
    result=get(selected) if selected and selected!=config['id'] else dict(config)
    model=config.get('vision_model') or result['chat_model']
    if not model:raise ValueError('请在“能力与路由”中选择视觉模型。')
    if model not in models(result['id']):raise ValueError('请先为视觉 API 读取模型，再选择视觉模型。')
    return {**result,'chat_model':model}

def use_vision_bridge(config):
    selected=config.get('vision_api_profile_id')
    return bool((selected and selected!=config['id']) or (config.get('vision_model') and config['vision_model']!=config['chat_model']))

def redact(text):
    import desktop_shared as shared
    result=str(text)
    try:
        for config in store()['profiles'].values():
            try:key=shared.credential(config)
            except Exception:continue
            if key:result=result.replace(key,'[密钥已隐藏]')
    except Exception:pass
    return result
