"""Exercise close-to-tray, background requests, reopening and orderly exit."""
import json,os,threading,time
from unittest.mock import patch
from PySide6.QtCore import QThread,QTimer
from PySide6.QtWidgets import QApplication,QDialog,QSystemTrayIcon
import core,main

app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
native_available=QSystemTrayIcon.isSystemTrayAvailable()
if os.environ.get('ANLLM_EXPECT_NATIVE_TRAY')=='1':assert native_available,'Windows notification area is unavailable'

def pump_until(condition):
    deadline=time.monotonic()+8
    while not condition():
        app.processEvents();time.sleep(.005)
        assert time.monotonic()<deadline,'Shutdown or worker did not finish'
    app.processEvents()

class Worker(QThread):
    def __init__(self):
        super().__init__();self.cancelled=threading.Event();self.exited=threading.Event();self.answers=[]
    def run(self):
        self.cancelled.wait(8);time.sleep(.08);self.exited.set()
    def cancel(self):self.cancelled.set()
    def resolve(self,identifier,value):self.answers.append((identifier,value))

class AcceptDialog(QDialog):
    shown=0
    def __init__(self,event,parent):super().__init__(parent)
    def show(self):
        type(self).shown+=1;super().show();QTimer.singleShot(0,self.accept)

with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=True),patch.object(QApplication,'quit') as quit_app,patch.object(main.browser_bridge.SERVICE,'shutdown') as shutdown:
    window=main.MainWindow();window.show();app.processEvents()
    assert window.tray and window.tray.isVisible() and not window.tray.icon().isNull()
    assert [action.text() for action in window.tray_menu.actions() if not action.isSeparator()]==['打开 Anllm','停止所有任务 · Ctrl+Alt+F10','退出 Anllm']
    worker=Worker();window.worker=worker;worker.finished.connect(window.task_finished);worker.start()
    with patch.object(window.tray,'showMessage') as notification,patch.object(main.QMessageBox,'question',side_effect=AssertionError('Close-to-tray must not ask permission')):
        window.close();app.processEvents()
        assert not window.isVisible() and window.worker is worker and worker.isRunning()
        assert not worker.cancelled.is_set() and not quit_app.called and not shutdown.called
        assert notification.call_count==1
        window.on_event({'type':'approval','id':'tray-approval','title':'查看网页','text':'测试','detail':''})
        app.processEvents();assert len(window.approval_queue)==1 and window.approval_dialog is None
        assert notification.call_count==2
        with patch.object(main,'ApprovalDialog',AcceptDialog):
            window.tray.activated.emit(QSystemTrayIcon.Trigger);pump_until(lambda:bool(worker.answers))
        assert window.isVisible() and not window.approval_queue and worker.answers==[('tray-approval',True)]
        assert AcceptDialog.shown==1
        window.close();app.processEvents();assert notification.call_count==2,'Repeated close notification'
        window.tray.activated.emit(QSystemTrayIcon.DoubleClick);app.processEvents();assert window.isVisible()
        window.close();app.processEvents()
        window.tray.messageClicked.emit();app.processEvents();assert window.isVisible()
        window.close();app.processEvents()
        background=main.FunctionWorker(lambda:time.sleep(.18));window.background_workers.append(background)
        background.finished.connect(lambda:window.background_workers.remove(background));background.start()
        window.import_queue=[('file','not-imported-after-exit')]
        window.tray_menu.actions()[-1].trigger()
        assert window.exit_requested and worker.cancelled.is_set() and not window.import_queue
        assert not quit_app.called and not shutdown.called,'Exit destroyed live workers'
        pump_until(lambda:quit_app.called)
        assert worker.exited.is_set() and not window.background_workers
        assert shutdown.call_count==1 and quit_app.call_count==1 and not window.tray.isVisible()
        assert not window.exit_timer.isActive()
        window.request_exit();assert quit_app.call_count==1

with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=False),patch.object(QApplication,'quit') as quit_app,patch.object(main.browser_bridge.SERVICE,'shutdown') as shutdown:
    fallback=main.MainWindow();fallback.show();app.processEvents();assert fallback.tray is None
    fallback.close();app.processEvents()
    assert fallback.exit_requested and not fallback.isVisible() and quit_app.call_count==1 and shutdown.call_count==1

# Complete a task while hidden: notify once and keep the application in the tray.
with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=True),patch.object(main.browser_bridge.SERVICE,'shutdown'):
    completed=main.MainWindow();completed.show();app.processEvents();completed.close();app.processEvents()
    with patch.object(completed.tray,'showMessage') as notification:
        completed.task_finished();assert notification.call_count==1 and not completed.isVisible()
    completed.present_window();app.processEvents();assert completed.isVisible()
    QTimer.singleShot(0,completed.request_exit)
    app.exec()
    assert completed.exit_requested and not completed.tray.isVisible()

report={'status':'passed','native_tray_available':native_available,'close_hides_window_without_stopping_task':True,
    'tray_click_double_click_and_notification_restore_window':True,'readable_open_and_exit_menu':True,
    'hidden_requests_wait_for_user_to_open_window':True,'background_completion_notifies_user':True,
    'explicit_exit_cancels_task_and_waits_for_workers':True,'browser_resources_released_on_exit':True,
    'exit_has_no_idle_polling_timer':True,'no_tray_falls_back_to_real_exit':True}
core.shared.atomic_json(core.ROOT/'logs'/'tray-verification.json',report)
print(json.dumps(report,ensure_ascii=False))
