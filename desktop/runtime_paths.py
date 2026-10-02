"""Relocatable installation and writable application data paths."""
import os
from pathlib import Path
import sys

BUNDLE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
INSTALL = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get('ANLLM_DATA_DIR', INSTALL)).resolve()
for name in ('config', 'data', 'workspace', 'images', 'logs', 'cache'):
    (ROOT / name).mkdir(parents=True, exist_ok=True)
if (BUNDLE / 'browsers').is_dir():
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(BUNDLE / 'browsers')
