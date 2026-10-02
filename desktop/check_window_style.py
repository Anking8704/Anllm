import faulthandler
faulthandler.dump_traceback_later(8,repeat=False)
from pathlib import Path
import os,sys,json,ctypes
from ctypes import wintypes
from runtime_paths import ROOT as root
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication,QMessageBox,QFileDialog,QDialog,QVBoxLayout,QLabel
from PySide6.QtTest import QTest
from window_chrome import configure_taskbar_identity,native_resize_hit,install_dialog_chrome,WindowChrome,ConfirmationDialog,ThemedMessageBox,ThemedFileDialog
from settings_panel import SettingsDialog
from request_dialogs import ApprovalDialog,QuestionDialog
from theme import STYLE
import core,main
configure_taskbar_identity()
identity=ctypes.c_void_p();getter=ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID
getter.argtypes=[ctypes.POINTER(ctypes.c_void_p)];getter.restype=ctypes.c_long
assert getter(ctypes.byref(identity))==0 and ctypes.wstring_at(identity)=='Anllm.Desktop'
ctypes.windll.ole32.CoTaskMemFree.argtypes=[ctypes.c_void_p];ctypes.windll.ole32.CoTaskMemFree(identity)
app=QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE);app.setFont(QFont('Microsoft YaHei',10));app.setQuitOnLastWindowClosed(False);install_dialog_chrome()
out=root/'logs/window-style-previews';out.mkdir(parents=True,exist_ok=True)
verified=[]
from unittest.mock import patch
with patch.object(core.shared,'cached_models',return_value=['gpt-6.1-sol']):
    window=main.MainWindow();window.show();QTest.qWait(100)
    assert window.windowFlags()&Qt.FramelessWindowHint
    assert not ctypes.windll.user32.GetWindowLongW(wintypes.HWND(int(window.winId())),-16)&0x00c00000
    QTest.mouseClick(window.window_chrome.maximize,Qt.LeftButton);QTest.qWait(50);assert window.isMaximized()
    QTest.mouseClick(window.window_chrome.maximize,Qt.LeftButton);QTest.qWait(50);assert not window.isMaximized()
    QTest.mouseClick(window.window_chrome.minimize,Qt.LeftButton);QTest.qWait(50);assert window.isMinimized();window.showNormal()
    QTest.mouseClick(window.window_chrome.close_button,Qt.LeftButton);app.processEvents();assert not window.isVisible() and not window.exit_requested
    window.present_window();window.request_exit();app.processEvents()

def check(dialog,name):
    dialog.show();QTest.qWait(100)
    assert dialog.isVisible() and dialog.windowFlags()&Qt.FramelessWindowHint
    assert not ctypes.windll.user32.GetWindowLongW(wintypes.HWND(int(dialog.winId())),-16)&0x00c00000
    chrome=dialog._anllm_chrome;assert isinstance(chrome,WindowChrome) and chrome.isVisible() and chrome.height()==30
    frame=dialog.grab().toImage();assert all(frame.pixelColor(x,y).alpha()==0 for x,y in [(0,0),(frame.width()-1,0),(0,frame.height()-1),(frame.width()-1,frame.height()-1)]),(name,'Corners are not transparent')
    assert all(frame.pixelColor(x,y).alpha()==255 for x in range(24,frame.width()-24,53) for y in range(24,frame.height()-24,37)),(name,'Missing opaque rounded background')
    dialog.grab().save(str(out/(name+'.png')));verified.append(name)

box=ConfirmationDialog(None,'删除任务','删除“新任务”？\n聊天记录将从任务列表移除。项目文件和生成图片会保留。',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
check(box,'删除任务')
assert box.defaultButton()==box.button(QMessageBox.No) and box.button(QMessageBox.Yes).text()=='确定'
QTest.keyClick(box,Qt.Key_Return);assert box.result()==QMessageBox.No
box2=ConfirmationDialog(None,'操作未完成','测试提示',QMessageBox.Ok,QMessageBox.Ok);check(box2,'警告提示');QTest.keyClick(box2,Qt.Key_Escape);assert not box2.isVisible()
settings=SettingsDialog(None);check(settings,'API设置');QTest.mouseClick(settings._anllm_chrome.close_button,Qt.LeftButton);assert settings.result()==QDialog.Rejected
approval=ApprovalDialog({'request':{'summary':'执行需要确认的操作','reason':'这是测试请求','location':'测试项目','impact':'测试不会修改真实文件'}});check(approval,'权限请求');QTest.keyClick(approval,Qt.Key_Return);assert approval.result()==QDialog.Rejected
question=QuestionDialog([{'question':'选择测试方案','options':['方案一','方案二']}],lambda:None);check(question,'补充信息');QTest.keyClick(question,Qt.Key_Escape);assert question.result()==QDialog.Rejected
picker=ThemedFileDialog.create(None,'选择项目',str(root),mode=QFileDialog.Directory);check(picker,'文件选择');picker.reject()
preview=QDialog();preview.setWindowTitle('图片 / 差异预览');QVBoxLayout(preview).addWidget(QLabel('测试预览'));check(preview,'内容预览');preview.reject()
QTimer.singleShot(20,lambda: next(w for w in app.topLevelWidgets() if isinstance(w,ConfirmationDialog) and w.isVisible()).button(QMessageBox.No).click())
result=ThemedMessageBox.question(None,'静态确认','静态接口也会应用主题。',QMessageBox.Yes|QMessageBox.No,QMessageBox.No);assert result==QMessageBox.No
faulthandler.cancel_dump_traceback_later()
report={'status':'passed','version':'1.4','dialogs_without_native_white_frames':verified,'transparent_smooth_corners':True,'confirmation_default_remains_no':True,'close_and_escape_reject':True,'static_messagebox_still_works':True,'file_picker_uses_same_chrome':True}
core.shared.atomic_json(core.ROOT/'logs/window-style-verification.json',report);print(json.dumps(report,ensure_ascii=False))
