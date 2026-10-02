from PyInstaller.utils.hooks import collect_data_files, collect_all, copy_metadata, collect_submodules
from pathlib import Path
from hashlib import sha256
import PySide6
icon_bytes=Path('Anllm.ico').read_bytes()
icon_path=Path('build/icon-assets')/('Anllm-'+sha256(icon_bytes).hexdigest()[:16]+'.ico')
icon_path.parent.mkdir(parents=True,exist_ok=True)
if not icon_path.exists():icon_path.write_bytes(icon_bytes)
playwright_data, playwright_bins, playwright_hidden = collect_all('playwright')
a = Analysis(['../desktop/launcher.py'],pathex=['../desktop'],
    binaries=playwright_bins,
    datas=playwright_data + [entry for entry in collect_data_files('openharness') if '/_frontend/' not in Path(entry[0]).as_posix()] + copy_metadata('openharness-ai') + copy_metadata('comtypes') + [('Anllm.ico','.'),('../desktop/chevron.svg','.'),('../desktop/check.svg','.'),('../desktop/gold-corner.svg','.'),('../desktop/gold-flourish.svg','.'),('../desktop/gold-vine.svg','.'),('../desktop/literary-crest.svg','.'),('../desktop/grand-piano.svg','.'),('../desktop/snowflake.svg','.'),('../desktop/note.svg','.'),('../desktop/star.svg','.'),('../desktop/sparkle.svg','.'),('../desktop/glow.svg','.'),('../desktop/ornament.svg','.'),('../desktop/rose.svg','.'),('../desktop/rose-pattern.svg','.')],
    hiddenimports=playwright_hidden + collect_submodules('comtypes.gen'),
    excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtQuick','PySide6.QtQml','tkinter','PIL'],
    noarchive=False)
# Never let unrelated SDK tools on PATH shadow the native Windows ICU/UCRT.
a.binaries=[entry for entry in a.binaries if 'codex-runtimes' not in entry[1].lower()]
# Qt's supplied redistributable is newer than the Python interpreter's CRT.
crt=list(Path(PySide6.__file__).parent.glob('*140*.dll'))
crt_names={path.name.lower() for path in crt}
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower() not in crt_names]
a.binaries.extend((path.name,str(path),'BINARY') for path in crt)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Anllm',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon=str(icon_path),version='version-info.txt')
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Anllm')
