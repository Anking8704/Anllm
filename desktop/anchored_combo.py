"""Keep topbar dropdowns beside their control, inside the current screen."""
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QStyledItemDelegate
from theme import T


class AnchoredComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_delegate = QStyledItemDelegate(self.view())

    def showPopup(self):
        if not self.count():
            return
        view = self.view()
        # A list delegate uses the themed highlight rather than the native
        # menu delegate, which can paint a black selection on Windows.
        view.setItemDelegate(self._popup_delegate)
        view.setStyleSheet(
            'QAbstractItemView {background:' + T['BG_CARD'] + '; color:' + T['TEXT'] +
            '; border:1px solid ' + T['BORDER_GOLD'] + '; padding:4px; outline:0;}'
            'QAbstractItemView::item {padding:5px 8px; border:none; background:transparent;}'
            'QAbstractItemView::item:selected {background:rgba(181,139,53,0.16); color:' + T['TEXT'] + ';}'
            'QAbstractItemView::item:hover {background:rgba(181,139,53,0.08); color:' + T['TEXT'] + ';}')
        # Native popup containers and viewports can inherit Windows dark colors
        # around rounded styles. Paint one complete ivory surface underneath.
        palette=view.palette()
        for role in (QPalette.Window,QPalette.Base,QPalette.AlternateBase):palette.setColor(role,QColor(T['BG_CARD']))
        palette.setColor(QPalette.Text,QColor(T['TEXT']))
        palette.setColor(QPalette.Highlight,QColor(181,139,53,40));palette.setColor(QPalette.HighlightedText,QColor(T['TEXT']))
        view.setPalette(palette);view.viewport().setPalette(palette);view.viewport().setAutoFillBackground(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setTextElideMode(Qt.ElideRight)
        for index in range(self.count()):
            if self.itemData(index, Qt.ToolTipRole) != self.itemText(index):
                self.setItemData(index, self.itemText(index), Qt.ToolTipRole)
        super().showPopup()
        popup = view.window()
        if popup is self.window() or not popup.isVisible():
            return
        popup.setObjectName('anchoredComboPopup')
        popup.setPalette(palette);popup.setAutoFillBackground(True)
        popup.setStyleSheet('QFrame#anchoredComboPopup {background:' + T['BG_CARD'] +
                            '; border:none;}')
        view.ensurePolished()
        view.doItemsLayout()
        screen = self.screen().availableGeometry()
        anchor = self.mapToGlobal(QPoint(0, self.height()))
        top = self.mapToGlobal(QPoint(0, 0)).y()
        # Follow the control width; longer names remain visible in tooltips.
        width = min(self.width(), screen.width())
        rows = min(self.count(), self.maxVisibleItems())
        row_height = max(view.sizeHintForRow(0), self.fontMetrics().height() + 12)
        margins = view.contentsMargins()
        chrome = max(margins.top() + margins.bottom() + 2 * view.frameWidth(),
                     popup.height() - view.viewport().height()) + 4
        desired = rows * row_height + chrome
        below = max(0, screen.bottom() - anchor.y() - 3)
        above = max(0, top - screen.top() - 4)
        use_below = desired <= below or below >= above
        height = min(desired, below if use_below else above, screen.height())
        if height < 1:
            height = min(desired, screen.height())
        x = max(screen.left(), min(anchor.x(), screen.right() - width + 1))
        y = anchor.y() + 4 if use_below else top - height - 4
        y = max(screen.top(), min(y, screen.bottom() - height + 1))
        # Qt's native popup initially aligns the selected row with the combo.
        # Place the whole popup below/above instead, preserving its native input.
        popup.setMinimumWidth(0)
        popup.setMaximumWidth(screen.width())
        popup.setMinimumHeight(0)
        popup.setMaximumHeight(screen.height())
        popup.setGeometry(QRect(x, y, width, height))
        view.scrollTo(view.currentIndex(), QAbstractItemView.PositionAtCenter)
