"""Register, dispatch and release the native stop shortcut without physical keys."""
import ctypes,json
from ctypes import wintypes
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from desktop_hotkey import StopShortcut
import core
app=QApplication([]);events=[]
shortcut=StopShortcut(app,lambda:(events.append('stop'),app.quit()))
assert shortcut.registered,'Ctrl+Alt+F10 could not be registered'
user=ctypes.WinDLL('user32',use_last_error=True)
user.PostThreadMessageW.argtypes=[wintypes.DWORD,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
user.PostThreadMessageW.restype=wintypes.BOOL
thread=ctypes.windll.kernel32.GetCurrentThreadId()
def dispatch():assert user.PostThreadMessageW(thread,0x312,shortcut.identifier,0)
QTimer.singleShot(50,dispatch);QTimer.singleShot(2500,app.quit);app.exec()
assert events==['stop'],'Native hotkey message did not reach Qt'
assert not shortcut.registered,'Hotkey was not released on exit'
report={'status':'passed','native_global_stop_registration':True,'native_message_dispatch_reaches_stop':True,'registration_released_on_exit':True,'idle_has_no_polling_or_keyboard_hook':True}
core.shared.atomic_json(core.ROOT/'logs'/'stop-shortcut-verification.json',report);print(json.dumps(report))
