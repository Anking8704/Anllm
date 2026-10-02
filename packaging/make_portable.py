"""Package the verified runtime using a clean application directory."""
import hashlib, json, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE / 'dist' / 'Anllm'
OUTPUT = HERE.parent.parent / 'outputs'
for folder in ('config', 'data', 'workspace', 'images', 'logs', 'cache'):
    assert not (APP / folder).exists(), 'Unexpected user data: ' + folder
package = OUTPUT / 'Anllm-Portable-1.4-x64.zip'
with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(APP.rglob('*')):
        if path.is_file():
            archive.write(path, 'Anllm/' + path.relative_to(APP).as_posix())
with zipfile.ZipFile(package) as archive:
    assert archive.testzip() is None
    assert 'Anllm/_internal/browsers/chromium-1243/chrome-win64/chrome.exe' in archive.namelist()
    with archive.open('Anllm/Anllm.exe') as stream, (APP / 'Anllm.exe').open('rb') as original:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == hashlib.file_digest(original, 'sha256').hexdigest()
print(json.dumps({'portable': package.name, 'status': 'passed', 'bytes': package.stat().st_size}))


