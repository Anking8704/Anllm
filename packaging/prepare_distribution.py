"""Assemble clean deliverables from explicit code/runtime allowlists."""
from pathlib import Path
import importlib.metadata as metadata,json,re,shutil,zipfile

HERE=Path(__file__).resolve().parent
APP=HERE/'dist'/'Anllm'
OUTPUTS=HERE.parent.parent/'outputs'
OUTPUTS.mkdir(exist_ok=True)
shutil.copy2(OUTPUTS/'Anllm使用说明.md',APP/'使用说明.md')
shutil.copy2(HERE/'第三方组件与许可.md',APP/'第三方组件与许可.md')
licenses=APP/'licenses';licenses.mkdir(exist_ok=True)
versions={}
for distribution in metadata.distributions():
    name=distribution.metadata['Name'];versions[name]=distribution.version
    for item in distribution.files or []:
        if any(token in str(item).lower() for token in ('license','copying','notice')):
            source=Path(distribution.locate_file(item))
            if source.is_file() and source.stat().st_size<4*1024*1024 and source.suffix.lower() not in ('.pyd','.dll','.exe','.pyc'):
                destination=licenses/name/str(item).replace('../','').replace('..\\','')
                destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
(licenses/'components.json').write_text(json.dumps(versions,indent=2),encoding='utf-8')
for forbidden in ('config','data','workspace','images','logs','cache'):
    assert not (APP/forbidden).exists(),'User data must not enter distributable: '+forbidden
source_files=['check_window_style.py','window_chrome.py','launcher.py','main.py','anchored_combo.py','reasoning.py','check_multitask.py','check_reasoning.py','core.py','team.py','browser_bridge.py','desktop_shared.py','runtime_paths.py','theme.py','settings_panel.py','api_profiles.py','modal_tools.py','appearance.py','diagnostics.py','image_assets.py','check_image_limits.py','check_tray.py','desktop_native.py','desktop_control.py','desktop_hotkey.py','desktop_fixture.py','check_desktop.py','check_stop_shortcut.py','app_version.py','routine_queries.py','request_presenter.py','request_dialogs.py','check_requests.py','check_multimodal.py','check_tasks.py','check_core.py','check_profiles.py','check_extensions.py','chevron.svg','check.svg','gold-corner.svg','gold-flourish.svg','gold-vine.svg','literary-crest.svg','grand-piano.svg','thinking_indicator.py','decorations.py','snowflake.svg','note.svg','star.svg','sparkle.svg','glow.svg','ornament.svg','rose.svg','rose-pattern.svg']
with zipfile.ZipFile(OUTPUTS/'Anllm-Source-1.4.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in source_files:
        path=HERE.parent/'desktop'/name
        assert not re.search(r'(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}',path.read_text('utf-8')),'Unexpected credential-like text in source'
        archive.write(path,'Anllm/desktop/'+name)
    for name in ['Anllm.spec','Anllm.iss','Anllm.ico','generate_icon.py','prepare_build.py','ChineseSimplified.isl','version-info.txt','第三方组件与许可.md','prepare_distribution.py','make_portable.py','requirements-build.txt','源代码构建.md']:
        archive.write(HERE/name,'Anllm/packaging/'+name)
    archive.write(OUTPUTS/'Anllm使用说明.md','Anllm/使用说明.md')
    archive.write(OUTPUTS/'思考强度适配说明.md','Anllm/思考强度适配说明.md')
    archive.write(OUTPUTS/'Anllm-1.4更新说明.md','Anllm/更新说明.md')
print('Clean distribution prepared; user data excluded.')




