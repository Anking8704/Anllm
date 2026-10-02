"""Compile the actual application icon into a multi-size Windows ICO."""
from pathlib import Path
import os,sys,tempfile,struct
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parent/'desktop'))
os.environ['ANLLM_DATA_DIR']=tempfile.mkdtemp(prefix='anllm-icon-build-')
from PySide6.QtCore import QBuffer,QIODevice,Qt,QSize
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
import main
app=QApplication([])
icon=main.app_icon()
frames=[]
for size in (16,24,32,48,64,128,256):
    pixmap=icon.pixmap(128,128).scaled(size,size,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    buffer=QBuffer();buffer.open(QIODevice.WriteOnly);assert pixmap.save(buffer,'PNG')
    frames.append((size,bytes(buffer.data())))
offset=6+16*len(frames)
headers=[]
for size,data in frames:
    headers.append(struct.pack('<BBBBHHII',size if size<256 else 0,size if size<256 else 0,0,0,1,32,len(data),offset));offset+=len(data)
path=root/'Anllm.ico'
payload=struct.pack('<HHH',0,1,len(frames))+b''.join(headers)+b''.join(data for _,data in frames)
if not path.exists() or path.read_bytes()!=payload:path.write_bytes(payload)
check=QIcon(str(path));assert not check.isNull()
for size,_ in frames:assert QSize(size,size) in check.availableSizes()
print('Generated pearl-white/gold ICO with seven sizes:',path)
