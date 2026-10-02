"""Theme-integrated window controls with native Windows move and resize."""
import ctypes,re
from ctypes import wintypes
from PySide6.QtCore import Qt,QEvent,QPointF,QObject
from PySide6.QtGui import QColor,QPainter,QPen,QLinearGradient
from PySide6.QtWidgets import QFrame,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,QApplication,QDialog,QMessageBox,QFileDialog
from theme import T
_SURFACE_STOPS=[(float(position),QColor(color)) for position,color in re.findall(r'stop:([\d.]+)\s+(#[\da-fA-F]+)',T['BG_SURFACE'])]

def hover_color():return QColor(181,139,53,26)

class WindowControl(QPushButton):
    def __init__(self,kind,window):
        super().__init__(window);self.kind=kind;self.owner=window
        self.setObjectName('windowControl');self.setFixedSize(32,26)
        self.setStyleSheet('QPushButton#windowControl { background: transparent; border: none; padding: 0; border-radius: 6px; }')
        self.setAccessibleName({'minimize':'最小化','maximize':'最大化 / 还原','close':'关闭' if isinstance(window,QDialog) else '关闭并收起到托盘'}[kind])
        self.setToolTip(self.accessibleName())
        self.clicked.connect({'minimize':window.showMinimized,'maximize':lambda:toggle_maximized(window),'close':window.close}[kind])
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.isDown():
            painter.setPen(Qt.NoPen);painter.setBrush(QColor('#EDD5CE') if self.kind=='close' else hover_color())
            painter.drawRoundedRect(self.rect(),6,6)
        painter.setPen(QPen(QColor(T['TEXT_2']),1.25));painter.setBrush(Qt.NoBrush)
        if self.kind=='minimize':painter.drawLine(QPointF(11,14),QPointF(21,14))
        elif self.kind=='close':
            painter.drawLine(QPointF(12,9),QPointF(20,17));painter.drawLine(QPointF(20,9),QPointF(12,17))
        elif self.owner.isMaximized():
            painter.drawRect(13,8,8,8);painter.fillRect(11,10,8,8,QColor(T['BG_DEEP']));painter.drawRect(11,10,8,8)
        else:painter.drawRect(11,9,10,9)

def toggle_maximized(window):
    window.showNormal() if window.isMaximized() else window.showMaximized()

class WindowChrome(QFrame):
    def __init__(self,window,title):
        super().__init__(window);self.owner=window;self.setObjectName('windowChrome');self.setFixedHeight(30)
        self.setStyleSheet('QFrame#windowChrome { background: transparent; border: none; } QLabel { background: transparent; border: none; color: '+T['TEXT_2']+'; font-size: 11px; }')
        layout=QHBoxLayout(self);layout.setContentsMargins(12,0,4,0);layout.setSpacing(2)
        caption=QLabel('✧  '+title);caption.setAttribute(Qt.WA_TransparentForMouseEvents);layout.addWidget(caption);layout.addStretch()
        self.minimize=WindowControl('minimize',window);self.maximize=WindowControl('maximize',window);self.close_button=WindowControl('close',window)
        for widget in (self.minimize,self.maximize,self.close_button):layout.addWidget(widget)
        if isinstance(window,QDialog):self.minimize.hide();self.maximize.hide()
        window.installEventFilter(self)
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.owner.windowHandle():
            self.owner.windowHandle().startSystemMove();event.accept();return
        super().mousePressEvent(event)
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton and not isinstance(self.owner,QDialog):toggle_maximized(self.owner);event.accept();return
        super().mouseDoubleClickEvent(event)
    def eventFilter(self,watched,event):
        if event.type()==QEvent.WindowStateChange:self.maximize.update()
        return super().eventFilter(watched,event)

def native_resize_hit(window,message):
    """Use physical screen coordinates for accurate resize at any display scale."""
    if window.isMaximized() or window.isFullScreen():return None
    msg=wintypes.MSG.from_address(int(message))
    if msg.message!=0x84:return None  # WM_NCHITTEST
    rect=wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(wintypes.HWND(int(window.winId())),ctypes.byref(rect)):return None
    x=ctypes.c_short(msg.lParam&0xffff).value;y=ctypes.c_short((msg.lParam>>16)&0xffff).value
    if not (rect.left<=x<rect.right and rect.top<=y<rect.bottom):return None
    border=max(5,round(6*window.devicePixelRatioF()))
    left=x<rect.left+border;right=x>=rect.right-border;top=y<rect.top+border;bottom=y>=rect.bottom-border
    if top and left:return 13
    if top and right:return 14
    if bottom and left:return 16
    if bottom and right:return 17
    if left:return 10
    if right:return 11
    if top:return 12
    if bottom:return 15
    return None

class DialogChromeManager(QObject):
    """Remove OS chrome before native creation; preserve each dialog's layout."""
    def eventFilter(self,watched,event):
        if isinstance(watched,QDialog) and event.type()==QEvent.Paint and getattr(watched,'_anllm_chrome',None):
            painter=QPainter(watched);painter.setRenderHint(QPainter.Antialiasing)
            background=QLinearGradient(0,0,0,watched.height())
            for position,color in _SURFACE_STOPS:background.setColorAt(position,color)
            painter.setPen(QPen(QColor(T['BORDER_GOLD']),3));painter.setBrush(background)
            painter.drawRoundedRect(watched.rect().toRectF().adjusted(1.5,1.5,-1.5,-1.5),20,20);painter.end()
        if isinstance(watched,QDialog) and not isinstance(watched,(QMessageBox,QFileDialog)) and event.type() in (QEvent.Polish,QEvent.Show):
            self.decorate(watched)
        return super().eventFilter(watched,event)
    def decorate(self,watched):
        if not getattr(watched,'_anllm_chrome',None):
            layout=watched.layout()
            if layout is not None:
                watched._anllm_chrome=True
                margins=layout.contentsMargins()
                layout.setContentsMargins(max(3,margins.left()),max(3,margins.top()),max(3,margins.right()),max(3,margins.bottom()))
                watched.setWindowFlag(Qt.FramelessWindowHint)
                watched.setAttribute(Qt.WA_TranslucentBackground)
                watched.setObjectName('roundedDialog')
                watched.setStyleSheet(watched.styleSheet()+'\nQDialog#roundedDialog { background: '+T['BG_SURFACE']+'; border: 3px solid '+T['BORDER_GOLD']+'; border-radius: 20px; } QFrame#dialogFooter { border-bottom-left-radius: 17px; border-bottom-right-radius: 17px; }')
                chrome=WindowChrome(watched,watched.windowTitle())
                watched._anllm_chrome=chrome
                if hasattr(layout,'getItemPosition'):
                    items=[]
                    while layout.count():
                        position=layout.getItemPosition(0)
                        items.append((layout.takeAt(0),position))
                    for item,(row,column,rows,columns) in items:layout.addItem(item,row+1,column,rows,columns)
                    layout.addWidget(chrome,0,0,1,max(1,layout.columnCount()))
                else:layout.insertWidget(0,chrome)

def install_dialog_chrome():
    app=QApplication.instance()
    if app is not None and not hasattr(app,'_anllm_dialog_chrome'):
        app.setAttribute(Qt.AA_DontUseNativeDialogs)
        app._anllm_dialog_chrome=DialogChromeManager(app)
        app.installEventFilter(app._anllm_dialog_chrome)

class ConfirmationDialog(QDialog):
    def __init__(self,parent,title,text,buttons,default):
        super().__init__(parent);self.setWindowTitle(title);self.setMinimumWidth(420);self.setMaximumWidth(680)
        layout=QVBoxLayout(self);layout.setContentsMargins(20,8,20,20);layout.setSpacing(18)
        content=QLabel(text);content.setTextFormat(Qt.PlainText);content.setWordWrap(True);content.setTextInteractionFlags(Qt.TextSelectableByMouse);layout.addWidget(content)
        row=QHBoxLayout();row.addStretch();self.controls={};self.default_role=default
        for role,caption in ((QMessageBox.Yes,'确定'),(QMessageBox.No,'取消'),(QMessageBox.Ok,'确定'),(QMessageBox.Cancel,'取消'),(QMessageBox.Retry,'重试'),(QMessageBox.Close,'关闭')):
            if buttons & role:
                control=QPushButton(caption);control.setAutoDefault(False);control.setDefault(role==default)
                control.clicked.connect(lambda checked=False,result=role:self.done(int(result)));row.addWidget(control);self.controls[role]=control
        layout.addLayout(row)
    def button(self,role):return self.controls.get(role)
    def defaultButton(self):return self.button(self.default_role)
    def reject(self):
        role=QMessageBox.No if QMessageBox.No in self.controls else QMessageBox.Cancel if QMessageBox.Cancel in self.controls else QMessageBox.Ok
        self.done(int(role))

class ThemedMessageBox(QMessageBox):
    """Keep Qt's public decision enums without mutating its internal grid layout."""
    @staticmethod
    def question(parent,title,text,buttons=QMessageBox.Yes|QMessageBox.No,defaultButton=QMessageBox.NoButton):
        install_dialog_chrome()
        if defaultButton==QMessageBox.NoButton:defaultButton=QMessageBox.No if buttons&QMessageBox.No else QMessageBox.Ok
        return ConfirmationDialog(parent,title,text,buttons,defaultButton).exec()
    @staticmethod
    def warning(parent,title,text,buttons=QMessageBox.Ok,defaultButton=QMessageBox.NoButton):
        install_dialog_chrome()
        if defaultButton==QMessageBox.NoButton:defaultButton=QMessageBox.Ok
        return ConfirmationDialog(parent,title,text,buttons,defaultButton).exec()

class ThemedFileDialog(QFileDialog):
    """Set the theme after QFileDialog finishes building its native widget layout."""
    @staticmethod
    def create(parent,title,directory='',filter='',mode=QFileDialog.ExistingFile,save=False,options=QFileDialog.Options()):
        install_dialog_chrome()
        dialog=QFileDialog(parent,title,directory,filter);dialog.setOptions(options|QFileDialog.DontUseNativeDialog)
        dialog.setFileMode(mode)
        if save:dialog.setAcceptMode(QFileDialog.AcceptSave)
        for role,text in ((QFileDialog.LookIn,'位置'),(QFileDialog.FileName,'文件名'),(QFileDialog.FileType,'类型'),(QFileDialog.Accept,'保存' if save else '选择'),(QFileDialog.Reject,'取消')):dialog.setLabelText(role,text)
        QApplication.instance()._anllm_dialog_chrome.decorate(dialog)
        dialog.setStyleSheet(dialog.styleSheet()+'\nQFileDialog QLineEdit { background: '+T['BG_ELEVATED']+'; border: 1px solid '+T['BORDER_GOLD']+'; border-radius: 12px; padding: 8px; } QFileDialog QToolButton { background: transparent; border: none; border-radius: 6px; padding: 4px; } QFileDialog QToolButton:hover { background: '+T['BG_HOVER']+'; } QFileDialog QHeaderView::section { background: '+T['BG_CARD']+'; color: '+T['TEXT_2']+'; border: none; padding: 6px; } QFileDialog QTreeView::item:selected, QFileDialog QListView::item:selected { background: rgba(181,139,53,0.16); color: '+T['TEXT']+'; border-radius: 6px; }')
        return dialog
    @staticmethod
    def getOpenFileNames(parent=None,caption='',dir='',filter='',selectedFilter='',options=QFileDialog.Options()):
        dialog=ThemedFileDialog.create(parent,caption,dir,filter,QFileDialog.ExistingFiles,options=options)
        if selectedFilter:dialog.selectNameFilter(selectedFilter)
        return (dialog.selectedFiles(),dialog.selectedNameFilter()) if dialog.exec()==QDialog.Accepted else ([], '')
    @staticmethod
    def getOpenFileName(parent=None,caption='',dir='',filter='',selectedFilter='',options=QFileDialog.Options()):
        dialog=ThemedFileDialog.create(parent,caption,dir,filter,options=options)
        if selectedFilter:dialog.selectNameFilter(selectedFilter)
        return (dialog.selectedFiles()[0],dialog.selectedNameFilter()) if dialog.exec()==QDialog.Accepted else ('', '')
    @staticmethod
    def getSaveFileName(parent=None,caption='',dir='',filter='',selectedFilter='',options=QFileDialog.Options()):
        dialog=ThemedFileDialog.create(parent,caption,dir,filter,QFileDialog.AnyFile,True,options)
        if selectedFilter:dialog.selectNameFilter(selectedFilter)
        return (dialog.selectedFiles()[0],dialog.selectedNameFilter()) if dialog.exec()==QDialog.Accepted else ('', '')
    @staticmethod
    def getExistingDirectory(parent=None,caption='',dir='',options=QFileDialog.ShowDirsOnly):
        dialog=ThemedFileDialog.create(parent,caption,dir,mode=QFileDialog.Directory,options=options)
        return dialog.selectedFiles()[0] if dialog.exec()==QDialog.Accepted else ''

def configure_taskbar_identity():
    if hasattr(ctypes,'windll'):
        setter=ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes=[wintypes.LPCWSTR];setter.restype=ctypes.c_long
        if setter('Anllm.Desktop')!=0:raise OSError('Unable to set Anllm taskbar identity')
