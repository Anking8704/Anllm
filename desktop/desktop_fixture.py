"""A disposable application used exclusively by desktop-control verification."""
import json,sys
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLineEdit,QPushButton,QLabel,QFrame

def run():
    app=QApplication([]);path=Path(sys.argv[-1]);state={'text':'','clicks':0,'pressed':0,'released':0,'double':0,'right':0,'wheel':0,'keys':[]}
    def save():
        temporary=path.with_suffix('.tmp')
        try:temporary.write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8');temporary.replace(path)
        except PermissionError:QTimer.singleShot(30,save)
    class Pad(QFrame):
        def mousePressEvent(self,event):
            state['pressed']+=1
            if event.button()==Qt.RightButton:state['right']+=1
            save();super().mousePressEvent(event)
        def mouseReleaseEvent(self,event):state['released']+=1;save();super().mouseReleaseEvent(event)
        def mouseDoubleClickEvent(self,event):state['double']+=1;save();super().mouseDoubleClickEvent(event)
        def wheelEvent(self,event):state['wheel']+=event.angleDelta().y();save();event.accept()
    window=QWidget();window.setWindowTitle('Anllm Desktop Verification');window.resize(600,460)
    body=QVBoxLayout(window);body.addWidget(QLabel('专用测试窗口；不操作其他应用'))
    field=QLineEdit();field.setAccessibleName('测试文本');body.addWidget(field)
    field.textChanged.connect(lambda value:(state.update(text=value),save()))
    field.returnPressed.connect(lambda:(state.update(enter=state.get('enter',0)+1),save()))
    password=QLineEdit();password.setEchoMode(QLineEdit.Password);password.setAccessibleName('密码验证');body.addWidget(password)
    button=QPushButton('普通按钮');body.addWidget(button)
    button.clicked.connect(lambda:(state.update(clicks=state['clicks']+1),save()))
    pad=Pad();pad.setAccessibleName('测试拖动区域');pad.setMinimumHeight(220);pad.setStyleSheet('background:#cee1f0');body.addWidget(pad)
    window.show();window.raise_();window.activateWindow()
    def ready():
        state['ready']=True;state['pad']=[pad.x(),pad.y(),pad.width(),pad.height()];save()
    QTimer.singleShot(200,ready);QTimer.singleShot(120000,app.quit)
    return app.exec()

if __name__=='__main__':sys.exit(run())
