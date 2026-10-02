"""On-demand Windows screenshots, UI Automation and physical input."""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import os,time
from pathlib import Path

class MouseInput(C.Structure):
    _fields_=[('dx',W.LONG),('dy',W.LONG),('mouseData',W.DWORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',C.c_size_t)]
class KeyboardInput(C.Structure):
    _fields_=[('wVk',W.WORD),('wScan',W.WORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',C.c_size_t)]
class HardwareInput(C.Structure):
    _fields_=[('uMsg',W.DWORD),('wParamL',W.WORD),('wParamH',W.WORD)]
class InputUnion(C.Union):
    _fields_=[('mi',MouseInput),('ki',KeyboardInput),('hi',HardwareInput)]
class Input(C.Structure):
    _anonymous_=('value',);_fields_=[('type',W.DWORD),('value',InputUnion)]
class BitmapHeader(C.Structure):
    _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),('bits',W.WORD),('compression',W.DWORD),('image_size',W.DWORD),('xppm',W.LONG),('yppm',W.LONG),('used',W.DWORD),('important',W.DWORD)]
class BitmapInfo(C.Structure):
    _fields_=[('header',BitmapHeader),('colors',W.DWORD*3)]
class GUIInfo(C.Structure):
    _fields_=[('size',W.DWORD),('flags',W.DWORD),('active',W.HWND),('focus',W.HWND),('capture',W.HWND),('menu_owner',W.HWND),('move_size',W.HWND),('caret',W.HWND),('caret_rect',W.RECT)]

def signature(dll,name,result,*arguments):
    function=getattr(dll,name);function.restype=result;function.argtypes=list(arguments);return function

class WindowsDesktop:
    def __init__(self):
        if os.name!='nt':raise RuntimeError('桌面控制需要 Windows。')
        self.user=C.WinDLL('user32',use_last_error=True);self.gdi=C.WinDLL('gdi32',use_last_error=True)
        u=self.user;g=self.gdi;ptr=C.c_void_p
        self.enum_callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
        signature(u,'EnumWindows',W.BOOL,self.enum_callback,W.LPARAM)
        signature(u,'IsWindow',W.BOOL,W.HWND);signature(u,'IsWindowVisible',W.BOOL,W.HWND);signature(u,'IsIconic',W.BOOL,W.HWND)
        signature(u,'GetWindowRect',W.BOOL,W.HWND,C.POINTER(W.RECT));signature(u,'GetWindowTextW',C.c_int,W.HWND,W.LPWSTR,C.c_int)
        signature(u,'GetClassNameW',C.c_int,W.HWND,W.LPWSTR,C.c_int)
        signature(u,'GetWindowThreadProcessId',W.DWORD,W.HWND,C.POINTER(W.DWORD));signature(u,'GetForegroundWindow',W.HWND)
        signature(u,'GetWindowLongW',W.LONG,W.HWND,C.c_int);signature(u,'GetAncestor',W.HWND,W.HWND,W.UINT)
        signature(u,'WindowFromPoint',W.HWND,W.POINT);signature(u,'GetCursorPos',W.BOOL,C.POINTER(W.POINT))
        signature(u,'SendInput',W.UINT,W.UINT,C.POINTER(Input),C.c_int);signature(u,'GetAsyncKeyState',W.SHORT,C.c_int)
        signature(u,'ShowWindow',W.BOOL,W.HWND,C.c_int);signature(u,'SetForegroundWindow',W.BOOL,W.HWND)
        signature(u,'BringWindowToTop',W.BOOL,W.HWND);signature(u,'SetWindowPos',W.BOOL,W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT)
        signature(u,'AttachThreadInput',W.BOOL,W.DWORD,W.DWORD,W.BOOL);signature(u,'GetGUIThreadInfo',W.BOOL,W.DWORD,C.POINTER(GUIInfo))
        signature(u,'GetDC',ptr,W.HWND);signature(u,'ReleaseDC',C.c_int,W.HWND,ptr);signature(u,'PrintWindow',W.BOOL,W.HWND,ptr,W.UINT)
        signature(u,'GetSystemMetrics',C.c_int,C.c_int);signature(u,'SetThreadDpiAwarenessContext',ptr,ptr)
        signature(u,'OpenInputDesktop',ptr,W.DWORD,W.BOOL,W.DWORD);signature(u,'CloseDesktop',W.BOOL,ptr)
        signature(u,'GetUserObjectInformationW',W.BOOL,ptr,C.c_int,ptr,W.DWORD,C.POINTER(W.DWORD))
        signature(g,'CreateCompatibleDC',ptr,ptr);signature(g,'CreateCompatibleBitmap',ptr,ptr,C.c_int,C.c_int)
        signature(g,'SelectObject',ptr,ptr,ptr);signature(g,'DeleteObject',W.BOOL,ptr);signature(g,'DeleteDC',W.BOOL,ptr)
        signature(g,'BitBlt',W.BOOL,ptr,C.c_int,C.c_int,C.c_int,C.c_int,ptr,C.c_int,C.c_int,W.DWORD)
        signature(g,'GetDIBits',C.c_int,ptr,ptr,W.UINT,W.UINT,ptr,C.POINTER(BitmapInfo),W.UINT)

    @contextmanager
    def physical_pixels(self):
        previous=self.user.SetThreadDpiAwarenessContext(C.c_void_p(-4))
        try:yield
        finally:
            if previous:self.user.SetThreadDpiAwarenessContext(previous)

    def assert_input_desktop(self):
        handle=self.user.OpenInputDesktop(0,False,1)
        if not handle:raise ValueError('当前桌面不可用；请先解锁电脑或手动完成 UAC 提示。')
        try:
            name=C.create_unicode_buffer(256);size=W.DWORD()
            if not self.user.GetUserObjectInformationW(handle,2,name,C.sizeof(name),C.byref(size)) or name.value.lower()!='default':
                raise ValueError('不能操作锁屏、UAC 或其他安全桌面。请手动处理后继续。')
        finally:self.user.CloseDesktop(handle)

    def window(self,identifier):
        parts=identifier.split('-')
        if len(parts)!=3 or parts[0]!='w':raise ValueError('窗口编号无效，请先获取窗口列表。')
        try:handle=int(parts[1],16);expected=int(parts[2])
        except ValueError:raise ValueError('窗口编号无效。') from None
        if not self.user.IsWindow(handle):raise ValueError('窗口已关闭，请重新查看窗口列表。')
        pid=W.DWORD();self.user.GetWindowThreadProcessId(handle,C.byref(pid))
        if pid.value!=expected:raise ValueError('窗口已变化，请重新获取。')
        title=C.create_unicode_buffer(1024);self.user.GetWindowTextW(handle,title,len(title))
        class_name=C.create_unicode_buffer(128);self.user.GetClassNameW(handle,class_name,len(class_name))
        with self.physical_pixels():
            rect=W.RECT()
            if not self.user.GetWindowRect(handle,C.byref(rect)):raise ValueError('无法读取窗口位置。')
        return {'id':identifier,'hwnd':handle,'pid':pid.value,'title':title.value or ('Windows 桌面' if class_name.value in ('Progman','WorkerW') else 'Windows 任务栏' if class_name.value=='Shell_TrayWnd' else '无标题窗口'),'class':class_name.value,
            'rect':[rect.left,rect.top,rect.right,rect.bottom],'minimized':bool(self.user.IsIconic(handle)),
            'foreground':handle==self.user.GetForegroundWindow()}

    def windows(self):
        values=[]
        @self.enum_callback
        def visit(handle,_):
            if not self.user.IsWindowVisible(handle):return True
            title=C.create_unicode_buffer(1024);self.user.GetWindowTextW(handle,title,len(title))
            kind=C.create_unicode_buffer(128);self.user.GetClassNameW(handle,kind,len(kind))
            if not title.value and kind.value not in ('Progman','WorkerW','Shell_TrayWnd'):return True
            pid=W.DWORD();self.user.GetWindowThreadProcessId(handle,C.byref(pid))
            try:values.append(self.window(f'w-{handle:x}-{pid.value}'))
            except ValueError:pass
            return True
        self.user.EnumWindows(visit,0);return values

    def virtual_rect(self):
        with self.physical_pixels():return [self.user.GetSystemMetrics(i) for i in (76,77,78,79)]

    def focus(self,identifier):
        self.assert_input_desktop();window=self.window(identifier);handle=window['hwnd']
        if window['pid']==os.getpid():raise ValueError('桌面输入不能操作 Anllm 自身或它的权限弹窗。')
        self.user.ShowWindow(handle,9 if window['minimized'] else 5)
        self.user.SetForegroundWindow(handle)
        if self.user.GetForegroundWindow()!=handle:
            foreground=self.user.GetForegroundWindow();thread=self.user.GetWindowThreadProcessId(foreground,None)
            current=C.windll.kernel32.GetCurrentThreadId()
            attached=bool(thread and thread!=current and self.user.AttachThreadInput(current,thread,True))
            try:self.user.BringWindowToTop(handle);self.user.SetForegroundWindow(handle)
            finally:
                if attached:self.user.AttachThreadInput(current,thread,False)
        if self.user.GetForegroundWindow()!=handle:raise ValueError('Windows 未允许切换窗口，请手动点开目标窗口后继续。')
        return self.window(identifier)

    @contextmanager
    def automation(self):
        import sys
        sys.coinit_flags=0
        import comtypes,comtypes.client
        from comtypes.gen import UIAutomationClient as M
        comtypes.CoInitializeEx(0)
        try:
            api=comtypes.client.CreateObject(M.CUIAutomation8,interface=M.IUIAutomation6)
            api.ConnectionTimeout=500;api.TransactionTimeout=700
            yield api,M
        finally:comtypes.CoUninitialize()

    def elements(self,identifier):
        window=self.window(identifier);rows=[]
        try:
            with self.physical_pixels(),self.automation() as (api,M):
                root=api.ElementFromHandle(window['hwnd'])
                condition=api.CreatePropertyCondition(M.UIA_IsControlElementPropertyId,True)
                found=root.FindAll(M.TreeScope_Descendants,condition)
                deadline=time.monotonic()+2
                for index in range(min(found.Length,200)):
                    if time.monotonic()>deadline:break
                    element=found.GetElement(index)
                    if element.CurrentIsOffscreen:continue
                    r=element.CurrentBoundingRectangle
                    if r.right<=r.left or r.bottom<=r.top:continue
                    password=bool(element.CurrentIsPassword)
                    rows.append({'ref':str(index),'name':'受保护的输入框' if password else (element.CurrentName or '')[:180],
                        'type':int(element.CurrentControlType),'rect':[r.left,r.top,r.right,r.bottom],
                        'password':password,'enabled':bool(element.CurrentIsEnabled),'runtime_id':list(element.GetRuntimeId())})
            return rows,''
        except Exception as error:
            self.last_automation_error=str(error)
            return rows,'该软件未完整提供控件信息，可用最新截图中的坐标操作。'

    def focused_sensitive(self,identifier):
        window=self.window(identifier)
        thread=self.user.GetWindowThreadProcessId(window['hwnd'],None);info=GUIInfo();info.size=C.sizeof(info)
        if self.user.GetGUIThreadInfo(thread,C.byref(info)) and info.focus:
            # ES_PASSWORD also covers native edit controls without UIA.
            name=C.create_unicode_buffer(64)
            self.user.GetClassNameW(info.focus,name,64)
            if 'edit' in name.value.lower() and self.user.GetWindowLongW(info.focus,-16)&0x20:return True
        try:
            with self.automation() as (api,_):return bool(api.GetFocusedElement().CurrentIsPassword)
        except Exception:return False

    def screenshot(self,rect,path,identifier=None):
        self.assert_input_desktop()
        left,top,right,bottom=rect;width=right-left;height=bottom-top
        if width<1 or height<1 or width*height>32_000_000:raise ValueError('截图区域无效或过大，请选择具体窗口。')
        with self.physical_pixels():
            source=self.user.GetDC(None);target=self.gdi.CreateCompatibleDC(source);bitmap=self.gdi.CreateCompatibleBitmap(source,width,height)
            original=self.gdi.SelectObject(target,bitmap)
            try:
                if identifier:
                    window=self.window(identifier)
                    if window['minimized']:raise ValueError('窗口已最小化，请先打开窗口。')
                    if self.user.GetForegroundWindow()!=window['hwnd']:raise ValueError('请先切换到目标窗口，再截图。')
                if not self.gdi.BitBlt(target,0,0,width,height,source,left,top,0x00CC0020|0x40000000):raise ValueError('无法获取桌面截图。')
                self.gdi.SelectObject(target,original);original=None
                info=BitmapInfo();info.header=BitmapHeader(C.sizeof(BitmapHeader),width,-height,1,32,0,0,0,0,0,0)
                buffer=C.create_string_buffer(width*height*4)
                if self.gdi.GetDIBits(target,bitmap,0,height,buffer,C.byref(info),0)!=height:raise ValueError('无法读取截图像素。')
                from PySide6.QtCore import Qt
                from PySide6.QtGui import QImage
                image=QImage(memoryview(buffer).cast('B'),width,height,width*4,QImage.Format_RGB32)
                # Keep captures useful for small text without retaining full-resolution buffers.
                if max(width,height)>2560:image=image.scaled(2560,2560,Qt.KeepAspectRatio,Qt.SmoothTransformation)
                path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
                if not image.save(str(path),'PNG'):raise ValueError('无法保存截图。')
                return [image.width(),image.height()]
            finally:
                if original:self.gdi.SelectObject(target,original)
                self.gdi.DeleteObject(bitmap);self.gdi.DeleteDC(target);self.user.ReleaseDC(None,source)

    def send(self,items):
        values=(Input*len(items))(*items)
        sent=self.user.SendInput(len(values),values,C.sizeof(Input))
        if sent!=len(values):
            release=[]
            for item in items[:sent]:
                if item.type==1 and not item.ki.dwFlags&2:release.append(self.keyboard(item.ki.wVk,True,item.ki.wScan))
                elif item.type==0:
                    for down,up in ((2,4),(8,16),(32,64)):
                        if item.mi.dwFlags&down:release.append(self.mouse(up))
            if release:
                cleanup=(Input*len(release))(*release);self.user.SendInput(len(cleanup),cleanup,C.sizeof(Input))
            raise ValueError('Windows 阻止了输入；目标可能以管理员权限运行，请手动处理。')

    def keyboard(self,key,up=False,scan=0):
        return Input(type=1,ki=KeyboardInput(key,scan,(2 if up else 0)|(4 if scan else 0),0,0))

    def mouse(self,flags,data=0,x=0,y=0):return Input(type=0,mi=MouseInput(x,y,data&0xffffffff,flags,0,0))

    def move(self,x,y):
        left,top,width,height=self.virtual_rect()
        if not (left<=x<left+width and top<=y<top+height):raise ValueError('鼠标坐标在屏幕范围之外。')
        self.send([self.mouse(0x8000|0x4000|1,x=round((x-left)*65535/max(1,width-1)),y=round((y-top)*65535/max(1,height-1)))])

    def act(self,identifier,action,check,*,point=None,end=None,text='',keys=None,button='left',amount=3,horizontal=False,duration=.4,select_all=False):
        self.assert_input_desktop();check();window=self.focus(identifier);handle=window['hwnd']
        def guard():
            check()
            if self.user.GetForegroundWindow()!=handle:raise ValueError('前台窗口已变化，已停止输入；请重新截图。')
            if self.user.GetAsyncKeyState(0x79)&0x8000 and self.user.GetAsyncKeyState(0x11)&0x8000 and self.user.GetAsyncKeyState(0x12)&0x8000:
                raise ValueError('已通过 Ctrl+Alt+F10 停止桌面操作。')
        guard()
        if any(self.user.GetAsyncKeyState(key)&0x8000 for key in (0x10,0x11,0x12,0x5b,0x5c)):
            raise ValueError('检测到用户正在按修饰键，请松开键盘后继续操作。')
        with self.physical_pixels():
            if point:
                self.move(*point)
                child=self.user.WindowFromPoint(W.POINT(*point))
                if self.user.GetAncestor(child,2)!=handle:raise ValueError('目标位置被其他窗口遮挡，请重新截图。')
            if action=='type' and point:self.send([self.mouse(2),self.mouse(4)]);time.sleep(.04)
            if action in ('type','press') and self.focused_sensitive(identifier):raise ValueError('密码等受保护输入请手动填写。')
            if action in ('click','double_click'):
                down,up={'left':(2,4),'right':(8,16),'middle':(32,64)}[button]
                for _ in range(2 if action=='double_click' else 1):guard();self.send([self.mouse(down),self.mouse(up)]);time.sleep(.045)
            elif action=='scroll':guard();self.send([self.mouse(0x1000 if horizontal else 0x800,amount*120)])
            elif action=='drag':
                self.send([self.mouse(2)])
                try:
                    steps=max(2,round(duration/.02))
                    for step in range(1,steps+1):
                        guard();self.move(round(point[0]+(end[0]-point[0])*step/steps),round(point[1]+(end[1]-point[1])*step/steps));time.sleep(duration/steps)
                finally:self.send([self.mouse(4)])
            elif action=='type':
                if select_all:self.send([self.keyboard(0x11),self.keyboard(0x41),self.keyboard(0x41,True),self.keyboard(0x11,True)])
                encoded=text.replace('\r\n','\n').encode('utf-16-le');units=[int.from_bytes(encoded[i:i+2],'little') for i in range(0,len(encoded),2)]
                for start in range(0,len(units),32):
                    guard();events=[]
                    for unit in units[start:start+32]:
                        if unit in (9,10,13):key=9 if unit==9 else 13;events.extend([self.keyboard(key),self.keyboard(key,True)])
                        else:events.extend([self.keyboard(0,scan=unit),self.keyboard(0,True,unit)])
                    self.send(events);time.sleep(.005)
            elif action=='press':
                guard();held=[]
                try:
                    for key in keys:self.send([self.keyboard(key)]);held.append(key)
                finally:
                    if held:self.send([self.keyboard(key,True) for key in reversed(held)])
            elif action=='move':guard()
        return {'completed':True,'action':action,'window':self.window(identifier)}
