"""A native global stop shortcut, with no keyboard hook or polling loop."""
import ctypes
from ctypes import wintypes
import os
from PySide6.QtCore import QAbstractNativeEventFilter,QTimer

class StopShortcut(QAbstractNativeEventFilter):
    identifier=0x4a11
    def __init__(self,application,callback):
        super().__init__();self.application=application;self.callback=callback;self.registered=False
        if os.name=='nt':
            self.api=ctypes.WinDLL('user32',use_last_error=True)
            self.api.RegisterHotKey.argtypes=[wintypes.HWND,ctypes.c_int,wintypes.UINT,wintypes.UINT]
            self.api.RegisterHotKey.restype=wintypes.BOOL
            self.api.UnregisterHotKey.argtypes=[wintypes.HWND,ctypes.c_int];self.api.UnregisterHotKey.restype=wintypes.BOOL
            self.registered=bool(self.api.RegisterHotKey(None,self.identifier,0x4000|1|2,0x79))
            if self.registered:application.installNativeEventFilter(self)
        application.aboutToQuit.connect(self.close)
    def nativeEventFilter(self,event_type,message):
        record=wintypes.MSG.from_address(int(message))
        if record.message==0x312 and record.wParam==self.identifier:
            QTimer.singleShot(0,self.callback);return True,0
        return False,0
    def close(self):
        if self.registered:
            self.api.UnregisterHotKey(None,self.identifier);self.application.removeNativeEventFilter(self);self.registered=False
