"""Small bounded previews; decode only thumbnails that a list actually paints."""
from collections import OrderedDict
from pathlib import Path
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate, QStyleOptionViewItem

class ThumbnailCache:
    def __init__(self, budget=16*1024*1024):
        self.budget=budget;self.used=0;self.items=OrderedDict();self.decodes=0

    def get(self,path,size):
        path=Path(path)
        try:stamp=path.stat().st_mtime_ns
        except OSError:return QPixmap()
        key=(str(path),stamp,size.width(),size.height())
        if key in self.items:
            self.items.move_to_end(key);return self.items[key][0]
        reader=QImageReader(str(path));reader.setAutoTransform(True)
        original=reader.size()
        if original.isValid():reader.setScaledSize(original.scaled(size,Qt.KeepAspectRatio))
        picture=QPixmap.fromImage(reader.read());self.decodes+=1
        if picture.isNull():return picture
        picture=picture.scaled(size,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        cost=picture.width()*picture.height()*4
        if cost<=self.budget:
            while self.items and self.used+cost>self.budget:
                _,(_,old_cost)=self.items.popitem(last=False);self.used-=old_cost
            self.items[key]=(picture,cost);self.used+=cost
        return picture

CACHE=ThumbnailCache()

def thumbnail(path,size):return CACHE.get(path,size)

class ImageDelegate(QStyledItemDelegate):
    def initStyleOption(self,option,index):
        super().initStyleOption(option,index)
        item=index.data(Qt.UserRole) or {}
        picture=thumbnail(item.get('path',''),option.decorationSize)
        if not picture.isNull():
            option.icon=QIcon(picture)
            option.features|=QStyleOptionViewItem.ViewItemFeature.HasDecoration

class ImageList(QListWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight);self.setWrapping(False)
        self.setIconSize(QSize(56,56));self.setGridSize(QSize(76,78));self.setFixedHeight(100)
        self.setUniformItemSizes(True);self.setItemDelegate(ImageDelegate(self))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def add_image(self,image):
        item=QListWidgetItem(image.get('label','图片')[:12]);item.setData(Qt.UserRole,image)
        item.setToolTip(image.get('label','图片'));self.addItem(item)
