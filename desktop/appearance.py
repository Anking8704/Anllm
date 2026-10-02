"""Local wallpaper storage and a painted native conversation surface."""
from pathlib import Path
import shutil,uuid
from PySide6.QtCore import Qt,QRect
from PySide6.QtGui import QColor,QImageReader,QPainter,QPixmap
from PySide6.QtWidgets import QWidget
from runtime_paths import ROOT
from image_assets import thumbnail
from theme import T
from PySide6.QtCore import QSize

def wallpaper_path(value):
    if not value:return None
    path=(ROOT/str(value)).resolve()
    if not path.is_relative_to((ROOT/'data'/'appearance').resolve()):return None
    return path if path.is_file() else None

def import_wallpaper(filename):
    path=Path(filename);reader=QImageReader(str(path));size=reader.size()
    if not reader.canRead() or not size.isValid():raise ValueError('请选择可读取的图片。')
    if path.stat().st_size>30*1024*1024 or size.width()*size.height()>40_000_000:raise ValueError('壁纸需小于 30 MB、4000 万像素。')
    if reader.read().isNull():raise ValueError('图片损坏或无法读取。')
    folder=ROOT/'data'/'appearance';folder.mkdir(parents=True,exist_ok=True)
    destination=folder/('wallpaper-'+uuid.uuid4().hex+'.'+bytes(reader.format()).decode('ascii'))
    shutil.copy2(path,destination)
    return destination.relative_to(ROOT).as_posix()

class WallpaperSurface(QWidget):
    def __init__(self):
        super().__init__();self.setObjectName('wallpaperSurface');self.picture=QPixmap();self.shade=68;self.scaled=QPixmap();self.scaled_size=QSize();self.source_key=None

    def apply(self,prefs):
        path=wallpaper_path(prefs.get('wallpaper'))
        key=(str(path),path.stat().st_mtime_ns) if path else None
        if key!=self.source_key:
            self.picture=thumbnail(path,QSize(2560,1440)) if path else QPixmap()
            self.source_key=key;self.scaled=QPixmap();self.scaled_size=QSize()
        self.shade=prefs.get('wallpaper_shade',68);self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor(T['BG_DEEP']))
        if not self.picture.isNull():
            if self.scaled_size!=self.size():
                self.scaled=self.picture.scaled(self.size(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation);self.scaled_size=self.size()
            painter.drawPixmap((self.width()-self.scaled.width())//2,(self.height()-self.scaled.height())//2,self.scaled)
            shade=QColor(T['BG_DEEP']);shade.setAlpha(round(255*self.shade/100));painter.fillRect(self.rect(),shade)
