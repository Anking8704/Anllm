"""Model-native effort options and wire parameters. Sources: outputs/思考强度适配说明.md."""
import re

LABELS={'none':'关闭','minimal':'极低','low':'低','medium':'中','high':'高','xhigh':'极高','max':'最高'}
THREE=('low','medium','high')
OPENAI={
    'gpt-5':('minimal',*THREE),
    'gpt-5.1':('none',*THREE),
    'gpt-5.2':('none',*THREE,'xhigh'),
    'gpt-5.4':('none',*THREE,'xhigh'),
    'gpt-5.5':('none',*THREE,'xhigh'),
    'gpt-5.6':('none',*THREE,'xhigh','max'),
    'gpt-5.6-sol':('none',*THREE,'xhigh','max'),
    'gpt-6-sol':('none',*THREE,'xhigh','max'),
    'gpt-6-luna':('none',*THREE,'xhigh','max'),
    'gpt-6-astra':(*THREE,'xhigh','max'),
    'gpt-6.1-sol':(*THREE,'xhigh','max'),
    'gpt-5.2-codex':(*THREE,'xhigh'),
    'gpt-5.3-codex':(*THREE,'xhigh'),
}
CLAUDE={
    'claude-opus-4-5':THREE,
    'claude-opus-4-6':(*THREE,'max'),
    'claude-opus-4-7':(*THREE,'xhigh','max'),
    'claude-opus-4-8':(*THREE,'xhigh','max'),
    'claude-opus-5':(*THREE,'xhigh','max'),
    'claude-opus-5-5':(*THREE,'xhigh','max'),
    'claude-sonnet-4-6':(*THREE,'max'),
    'claude-sonnet-5':(*THREE,'xhigh','max'),
    'claude-sonnet-5-5':(*THREE,'xhigh','max'),
    'claude-fable-5':(*THREE,'xhigh','max'),
    'claude-fable-5-1':(*THREE,'xhigh','max'),
    'claude-mythos-5':(*THREE,'xhigh','max'),
    'claude-mythos-5-1':(*THREE,'xhigh','max'),
    'claude-mythos-preview':(*THREE,'max'),
}
GEMINI={
    'gemini-3.8-flash':THREE,'gemini-3.7-flash':THREE,
    'gemini-3.6-flash':('minimal',*THREE),
    'gemini-3.5-flash':('minimal',*THREE),
    'gemini-3.5-flash-lite':('minimal',*THREE),
    'gemini-3.1-pro-preview':THREE,
    'gemini-3.1-flash-lite-image':('minimal','high'),
    'gemini-3-flash-preview':('minimal',*THREE),
    'gemini-3-pro-preview':('low','high'),
    'gemini-2.5-pro':THREE,
    'gemini-2.5-flash':('none',*THREE),
    'gemini-2.5-flash-lite':('none',*THREE),
}
GROK={'grok-4.5':THREE,'grok-4.6':(*THREE,'xhigh'),'grok-4.7':(*THREE,'xhigh')}
DEEPSEEK={'deepseek-flash':('none','low','high','max'),'deepseek-v4-pro':('none','low','high','max')}

def model_name(model):
    # Namespaced gateway ids and dated snapshots; never match arbitrary suffixes.
    name=(model or '').casefold().rsplit('/',1)[-1]
    return re.sub(r'-(?:\d{4}-\d{2}-\d{2}|\d{8})$','',name)

def catalog_options(item):
    if not isinstance(item,dict):return None
    caps=item.get('capabilities',{})
    candidates=[item.get('supported_reasoning_efforts'),item.get('reasoning_effort'),
        caps.get('reasoning_effort') if isinstance(caps,dict) else None,
        item.get('effort',{}).get('supported_levels') if isinstance(item.get('effort'),dict) else None]
    for value in candidates:
        if isinstance(value,dict):value=value.get('enum',value.get('supported_values'))
        if isinstance(value,list):
            result=list(dict.fromkeys(v for v in value if isinstance(v,str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,24}',v)))
            if result or not value:return result
    return None

def options(config,model=None):
    model=model or config.get('chat_model','');name=model_name(model)
    metadata=config.get('model_capabilities',{}).get(model)
    if metadata is not None:return tuple(metadata)
    if config.get('chat_api')=='anthropic':return CLAUDE.get(name,DEEPSEEK.get(name,()))
    if name.startswith('claude-'):return ()  # Compatible gateways must advertise their mapping.
    return OPENAI.get(name,GEMINI.get(name,GROK.get(name,DEEPSEEK.get(name,()))))

def selection(config,model=None):
    effort=config.get('reasoning_effort','')
    if effort and effort not in options(config,model):
        raise ValueError('当前模型不支持所选思考强度，请重新选择思考强度。')
    return effort

def apply(payload,config,api,model=None):
    effort=selection(config,model)
    if not effort:return payload
    if api=='anthropic':
        if model_name(model or config.get('chat_model')) in DEEPSEEK:
            payload['thinking']={'type':'disabled' if effort=='none' else 'enabled'}
            if effort!='none':payload['output_config']={'effort':effort}
        else:payload['output_config']={'effort':effort}
        if model_name(model or config.get('chat_model')) in CLAUDE and model_name(model or config.get('chat_model'))!='claude-opus-4-5':
            payload['thinking']={'type':'adaptive'}
    elif api=='responses':payload['reasoning']={'effort':effort}
    else:payload['reasoning_effort']=effort
    return payload

def responses_for_tools(model):
    return model_name(model) in {'gpt-6-astra','gpt-6.1-sol','gpt-6-sol','gpt-6-luna'}
