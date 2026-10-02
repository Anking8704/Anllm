"""Static theme ornaments, decoded once and painted without timers or effects."""
from PySide6.QtCore import QSize, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QFrame, QTreeWidget
from runtime_paths import BUNDLE
from collections import OrderedDict

_SPRITES = OrderedDict()

def ornament(filename, width, height):
    key = (filename, width, height)
    if key not in _SPRITES:
        _SPRITES[key] = QIcon(str(BUNDLE / filename)).pixmap(QSize(width, height))
        if len(_SPRITES)>48:_SPRITES.popitem(last=False)
    _SPRITES.move_to_end(key)
    return _SPRITES[key]


def draw_inlay(painter, rect, radius=12, width=2.3):
    """A narrow metallic band and its inset highlight, painted on demand."""
    painter.setRenderHint(QPainter.Antialiasing)
    brush = QLinearGradient(rect.topLeft(), rect.bottomRight())
    for offset, color in ((0, '#79551B'), (.25, '#E6CD89'), (.5, '#A67B27'), (.75, '#F4E4B4'), (1, '#997024')):
        brush.setColorAt(offset, QColor(color))
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(brush, width))
    painter.drawRoundedRect(rect, radius, radius)
    painter.setPen(QPen(QColor('#FBF3DB'), .8))
    painter.drawRoundedRect(rect.adjusted(2.2, 2.2, -2.2, -2.2), max(1, radius-2), max(1, radius-2))


class DecoratedFrame(QFrame):
    def __init__(self, region, parent=None):
        super().__init__(parent)
        self.region = region
        definitions = {
            'sidebar': [('rose-pattern.svg', 112, 6, 20, False), ('gold-corner.svg', 108, 8, 110, True)],
            'topbar': [('gold-corner.svg', 56, 10, 6, False), ('rose.svg', 48, 78, 12, False)],
            'inspector': [('rose-pattern.svg', 102, 8, 12, False), ('gold-corner.svg', 108, 10, 112, True)],
        }
        self.ornaments = []
        for filename, edge, right, offset, bottom in definitions.get(region, []):
            pixmap = ornament(filename, edge, edge)
            if not pixmap.isNull():
                self.ornaments.append((pixmap, right, offset, bottom))

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.ornaments and self.region not in ('shell', 'composer'):
            return
        painter = QPainter(self)
        if self.region in ('shell', 'composer'):
            draw_inlay(painter, QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 24 if self.region=='composer' else 14, 1 if self.region=='composer' else 2.3)
        painter.setOpacity(.9)
        for pixmap, right, offset, bottom in self.ornaments:
            edge = round(pixmap.height() / pixmap.devicePixelRatio())
            painter.drawPixmap(self.width() - edge - right,
                               self.height() - edge - offset if bottom else offset, pixmap)
        if self.region in ('sidebar', 'inspector'):
            flourish = ornament('gold-flourish.svg', self.width()-38, 34)
            painter.drawPixmap(19, 104 if self.region == 'sidebar' else self.height()-44, flourish)
        if self.region == 'sidebar':
            stars = ornament('gold-vine.svg', 25, 150)
            painter.drawPixmap(self.width()-35, max(240, self.height()//2-70), stars)


class OrnamentedTree(QTreeWidget):
    """Keep the empty tool panel decorated; filled logs stay unobstructed."""
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.topLevelItemCount():
            return
        painter = QPainter(self.viewport())
        painter.setOpacity(.82)
        rose = ornament('literary-crest.svg', 210, 175)
        flourish = ornament('gold-flourish.svg', min(240, self.viewport().width()-24), 36)
        painter.drawPixmap((self.viewport().width()-rose.width())//2, max(12, self.viewport().height()//2-102), rose)
        painter.drawPixmap((self.viewport().width()-flourish.width())//2, self.viewport().height()//2+85, flourish)
