"""Anllm — a native Qt Widgets application, without a browser."""
from __future__ import annotations

import asyncio
import base64
import copy
import html
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import traceback
import uuid

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QSize, QPoint
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPalette, QPixmap, QShortcut, QPen
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QMenu, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTabWidget, QTextBrowser,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QSystemTrayIcon, QStyle, QStyleOption)

import core
import browser_bridge
import reasoning

from theme import STYLE, MARKDOWN_CSS, T as THEME
from settings_panel import SettingsDialog
from appearance import WallpaperSurface
from request_dialogs import ApprovalDialog, QuestionDialog
from image_assets import ImageList, thumbnail
from app_version import APP_VERSION,APP_TITLE
from thinking_indicator import ThinkingIndicator
from decorations import DecoratedFrame, OrnamentedTree, ornament
from anchored_combo import AnchoredComboBox
from window_chrome import WindowChrome,native_resize_hit,install_dialog_chrome,configure_taskbar_identity
from window_chrome import ThemedMessageBox as QMessageBox
from window_chrome import ThemedFileDialog as QFileDialog

def import_attachments(entries):
    attachments=[];errors=[]
    for kind,value in entries:
        try:
            if kind=='file':attachment=core.shared.import_image(value)
            else:
                filename=core.shared.UPLOADS/('clipboard-'+uuid.uuid4().hex+'.png')
                if not value.save(str(filename),'PNG'):raise ValueError('无法保存剪贴板图片。')
                attachment={'name':filename.name,'label':'剪贴板图片','url':'/assets/'+filename.name}
            attachments.append(attachment)
        except Exception as error:errors.append(str(error))
    return {'attachments':attachments,'errors':errors}


def label(text, name=None, wrap=False):
    widget=QLabel(text)
    if name: widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback=None, name=None):
    widget=QPushButton(text)
    if name: widget.setObjectName(name)
    if callback: widget.clicked.connect(callback)
    return widget


class ModelSettingsPopup(QFrame):
    def paintEvent(self,event):
        # Translucent native popup windows require an explicit styled surface.
        option=QStyleOption();option.initFrom(self)
        painter=QPainter(self);self.style().drawPrimitive(QStyle.PE_Widget,option,painter,self)


class ModelSettingsButton(QPushButton):
    """One compact entry; full model names remain available to assistive tools."""
    def setSummary(self, model, effort):
        self.summary=model+'  '+effort
        self.setAccessibleName('模型与思考强度：'+self.summary)
        self.setToolTip(self.summary+'\n点击选择模型和思考强度')
        self._fit_text()

    def _fit_text(self):
        self.setText(self.fontMetrics().elidedText(getattr(self,'summary','选择模型'),Qt.ElideRight,max(24,self.width()-36)))

    def resizeEvent(self,event):
        super().resizeEvent(event);self._fit_text()

    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(THEME['TEXT_3']),1.2))
        x,y=self.width()-12,self.height()//2
        painter.drawLine(x-4,y-2,x,y+2);painter.drawLine(x,y+2,x+4,y-2)


class AgentWorker(QThread):
    event=Signal(object)
    result=Signal(object)

    def __init__(self,session,text,attachments,mode):
        super().__init__()
        self.session,self.text,self.attachments,self.mode=session,text,attachments,mode
        self.loop=None;self.task=None;self.pending={};self.stopping=threading.Event();self.team=None

    async def approve(self,title,text,detail):
        future=self.loop.create_future()
        identifier=uuid.uuid4().hex
        self.pending[identifier]=future
        request={key:core.scrub(value) if isinstance(value,str) else value for key,value in text.items()} if isinstance(text,dict) else {}
        self.event.emit({'type':'approval','id':identifier,'title':title,'text':request.get('raw',core.scrub(text)),'detail':core.scrub(detail),'request':request})
        try: return await future
        finally: self.pending.pop(identifier,None)

    async def ask(self,questions):
        future=self.loop.create_future();identifier=uuid.uuid4().hex
        self.pending[identifier]=future;self.event.emit({'type':'question','id':identifier,'questions':questions})
        try:return await future
        finally:self.pending.pop(identifier,None)

    def resolve(self,identifier,approved):
        if self.loop:
            def complete():
                future=self.pending.get(identifier)
                if future and not future.done(): future.set_result(approved)
            self.loop.call_soon_threadsafe(complete)

    def cancel(self):
        self.stopping.set()
        from desktop_control import SERVICE
        SERVICE.cancel(self.session['id']+':main')
        if self.loop and self.task: self.loop.call_soon_threadsafe(self.task.cancel)

    def cancel_agent(self,identifier):
        if self.loop and self.team: self.loop.call_soon_threadsafe(self.team.cancel,identifier)

    def run(self):
        async def run():
            self.loop=asyncio.get_running_loop()
            self.task=asyncio.create_task(core.execute_task(self.session,self.text,self.attachments,self.mode,self.event.emit,self.approve,control=lambda team:setattr(self,'team',team),ask=self.ask))
            if self.stopping.is_set(): self.task.cancel()
            try: return await self.task
            except asyncio.CancelledError: return self.session
        try: self.result.emit(asyncio.run(run()))
        except Exception as error:
            self.event.emit({'type':'status','text':core.scrub(error)})
            self.result.emit(self.session)


class FunctionWorker(QThread):
    result=Signal(object)
    failed=Signal(str)
    def __init__(self,function): super().__init__();self.function=function
    def run(self):
        try: self.result.emit(self.function())
        except Exception as error: self.failed.emit(core.scrub(error))


class Prompt(QTextEdit):
    submitted=Signal()
    attached=Signal(object)
    pasted_image=Signal(object)
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Return,Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.submitted.emit();return
        super().keyPressEvent(event)
    def canInsertFromMimeData(self,source): return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)
    def insertFromMimeData(self,source):
        if source.hasImage(): self.pasted_image.emit(source.imageData());return
        if source.hasUrls():
            self.attached.emit([url.toLocalFile() for url in source.urls() if url.isLocalFile()]);return
        super().insertFromMimeData(source)


class MessageCard(QFrame):
    def __init__(self,message):
        super().__init__();self.setObjectName('message');self.message_id=message['id']
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,12,0,18);layout.setSpacing(10)
        header=QHBoxLayout();header.addWidget(label('你' if message['role']=='user' else '✧  Anllm','role'))
        header.addWidget(label(' · '.join(filter(None,[message.get('api_name'),message.get('model')])),'model'));header.addStretch();layout.addLayout(header)
        self.text=QTextBrowser();self.text.setReadOnly(True);self.text.setOpenExternalLinks(False)
        self.text.anchorClicked.connect(self.open_link)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text.document().setDefaultStyleSheet(MARKDOWN_CSS)
        layout.addWidget(self.text)
        self._pending_text=None;self._rendered_text=None
        self.text_timer=QTimer(self);self.text_timer.setSingleShot(True);self.text_timer.setInterval(60);self.text_timer.timeout.connect(self.flush_text)
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.timeout.connect(self.fit_text)
        self.set_text(message.get('text',''))
        if message['role']=='user' and not message.get('text'):self.text.hide()
        self.images=QVBoxLayout();layout.addLayout(self.images)
        if message.get('attachments'):
            layout.addWidget(label('参考图 · '+str(len(message['attachments']))+' 张','muted'))
            gallery=ImageList();layout.addWidget(gallery)
            for attachment in message['attachments']:
                try:gallery.add_image({**attachment,'path':str(core.shared.image_path(attachment['name']))})
                except ValueError:continue
            gallery.itemDoubleClicked.connect(lambda item:self.show_image(Path(item.data(Qt.UserRole)['path'])))
        for image in message.get('images',[]): self.add_image(image)

    def open_link(self,url):
        if url.scheme() in ('https','http'):
            if QMessageBox.question(self,'打开链接',url.toString())==QMessageBox.Yes: QDesktopServices.openUrl(url)

    def set_text(self,text):
        self._pending_text=text or '正在处理…'
        if self._rendered_text is None:self.flush_text()
        elif not self.text_timer.isActive():self.text_timer.start()

    def flush_text(self):
        if self._pending_text!=self._rendered_text:
            self.text.setMarkdown(self._pending_text);self._rendered_text=self._pending_text
            if not self.fit_timer.isActive():self.fit_timer.start(0)

    def fit_text(self):
        width=max(300,self.text.viewport().width())
        self.text.document().setTextWidth(width)
        height=self.text.document().size().height()
        desired=min(560,max(36,int(height)+12))
        if self.text.height()!=desired: self.text.setFixedHeight(desired)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'fit_timer') and not self.fit_timer.isActive():self.fit_timer.start(0)

    def add_image(self,image):
        try: path=core.shared.image_path(image['name'])
        except Exception: return
        holder=QFrame();layout=QVBoxLayout(holder);layout.setContentsMargins(0,5,0,5)
        pixmap=thumbnail(path,QSize(470,320))
        preview=QPushButton();preview.setIcon(QIcon(pixmap));preview.setIconSize(pixmap.size().scaled(QSize(470,320),Qt.KeepAspectRatio))
        preview.setFixedSize(preview.iconSize()+QSize(16,16));preview.clicked.connect(lambda:self.show_image(path))
        layout.addWidget(preview,0,Qt.AlignLeft)
        footer=QHBoxLayout();footer.addWidget(label(image.get('caption') or '✦ '+image.get('model','')+' · 已保存到图片目录','muted'))
        footer.addStretch();footer.addWidget(button('另存为',lambda:self.save_image(path),'quiet'));layout.addLayout(footer)
        self.images.addWidget(holder)

    def show_image(self,path):
        dialog=QDialog(self);dialog.setWindowTitle(path.name);dialog.resize(850,760)
        layout=QVBoxLayout(dialog);scroll=QScrollArea();view=QLabel();view.setPixmap(thumbnail(path,QSize(1600,1340)).scaled(800,670,Qt.KeepAspectRatio,Qt.SmoothTransformation));view.setAlignment(Qt.AlignCenter)
        scroll.setWidget(view);scroll.setWidgetResizable(True);layout.addWidget(scroll)
        layout.addWidget(button('另存为',lambda:self.save_image(path)))
        dialog.exec()

    def save_image(self,path):
        target,_=QFileDialog.getSaveFileName(self,'保存图片',str(Path.home()/'Downloads'/path.name),'图片 (*.png *.jpg *.webp)')
        if target and Path(target).resolve()!=path.resolve(): shutil.copy2(path,target)


TOOL_NAMES={'ask_user':'向你提问','read_file':'读取文件','write_file':'创建 / 写入文件','edit_file':'修改文件','list_files':'查找文件',
    'search_files':'搜索内容','run_command':'执行命令','update_plan':'更新计划','generate_image':'图片创作','analyze_images':'视觉分析','web_fetch':'读取网页','web_search':'搜索网页',
    'delegate_tasks':'分配并行任务','agent_status':'查看助手进度','stop_agent':'停止助手',
    'browser_open':'打开页面','browser_read':'读取页面','browser_click':'点击页面','browser_fill':'填写页面','browser_select':'选择选项',
    'browser_press':'页面按键','browser_scroll':'滚动页面','browser_close':'关闭页面',
    'desktop_windows':'查看软件窗口','desktop_focus':'切换软件窗口','desktop_inspect':'观察桌面','desktop_action':'操作桌面软件'}


class TaskList(QListWidget):
    orderChanged=Signal()
    def __init__(self):
        super().__init__();self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction);self.setDropIndicatorShown(True)
    def dropEvent(self,event):
        super().dropEvent(event)
        if event.isAccepted():self.orderChanged.emit()
    def paintEvent(self,event):
        super().paintEvent(event)
        if self.verticalScrollBar().maximum()>0:return
        bottom=self.visualItemRect(self.item(self.count()-1)).bottom()+8 if self.count() else 0
        room=self.viewport().height()-bottom-8
        if room<90:return
        emblem=ornament('grand-piano.svg',min(178,self.viewport().width()-12),min(125,room))
        painter=QPainter(self.viewport());painter.setOpacity(.8)
        painter.drawPixmap((self.viewport().width()-emblem.width())//2,bottom+(room-emblem.height())//2,emblem)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();install_dialog_chrome();self.setWindowTitle(APP_TITLE);self.setWindowFlag(Qt.FramelessWindowHint);self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet('QMainWindow { background: transparent; }');self.resize(1400,870);self.setMinimumSize(1040,680)
        self.workers={};self.live_sessions={};self.drafts={};self.task_status={};self.current=None;self.attachments=[];self.cards={};self.approval_queue=[];self.approval_dialog=None;self.approval_owner=None
        self.agent_items={};self.browser_state=None;self.desktop_state=None;self.background_workers=[];self.global_stop=None
        self.import_queue=[];self.import_worker=None;self.visible_messages=40
        self.tray=None;self.exit_requested=False;self.tray_notice_shown=False
        self.exit_timer=QTimer(self);self.exit_timer.setSingleShot(True);self.exit_timer.setInterval(100)
        self.exit_timer.timeout.connect(self.finish_exit)
        self.scroll_timer=QTimer(self);self.scroll_timer.setSingleShot(True);self.scroll_timer.setInterval(80)
        self.scroll_timer.timeout.connect(lambda:self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))
        self.thinking_indicator=ThinkingIndicator(self)
        self.setWindowIcon(app_icon())
        wrapper=DecoratedFrame('shell');wrapper.setObjectName('appShell');self.setCentralWidget(wrapper)
        shell_layout=QVBoxLayout(wrapper);shell_layout.setContentsMargins(6,4,6,6);shell_layout.setSpacing(0)
        self.window_chrome=WindowChrome(self,APP_TITLE);shell_layout.addWidget(self.window_chrome)
        body=QWidget();body.setObjectName('wallpaperLayer');shell_layout.addWidget(body,1)
        outer=QHBoxLayout(body);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        sidebar=DecoratedFrame('sidebar');sidebar.setObjectName('sidebar');sidebar.setFixedWidth(238)
        side=QVBoxLayout(sidebar);side.setContentsMargins(20,28,20,22);side.setSpacing(22)
        side.addWidget(label('✧  Anllm','brand'));side.addWidget(label('D E S K T O P   A G E N T','section'))
        self.new_button=button('＋  新任务',self.new_chat);side.addWidget(self.new_button)
        side.addSpacing(6)
        task_heading=QHBoxLayout();task_heading.addWidget(label('任务','section'));task_heading.addStretch()
        self.task_actions=button('⋯',self.show_task_menu,'quiet');self.task_actions.setFixedWidth(34);self.task_actions.setStyleSheet('padding: 4px; text-align: center;');self.task_actions.setToolTip('收藏、移动或删除选中的任务');task_heading.addWidget(self.task_actions);side.addLayout(task_heading)
        self.session_list=TaskList();self.session_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.session_list.setTextElideMode(Qt.ElideRight);self.session_list.itemClicked.connect(self.select_session)
        self.session_list.setContextMenuPolicy(Qt.CustomContextMenu);self.session_list.customContextMenuRequested.connect(self.show_task_menu);self.session_list.orderChanged.connect(self.persist_task_order);side.addWidget(self.session_list,1)
        side.addWidget(label('拖动排序 · 右键收藏 / 删除','muted'))
        side.addWidget(label('当前工作目录','section'));self.folder_label=label('','muted',True);side.addWidget(self.folder_label)
        self.folder_button=button('▱  选择项目文件夹',self.choose_folder);side.addWidget(self.folder_button)
        self.settings_button=button('⚙  API 与模型设置',self.show_settings,'settingsAction');side.addWidget(self.settings_button)
        side.addWidget(label('原生桌面 · 本地会话与文件','muted'));side.addWidget(label('版本 '+APP_VERSION,'muted'));outer.addWidget(sidebar)
        splitter=QSplitter(Qt.Horizontal);outer.addWidget(splitter,1)
        center=WallpaperSurface();self.wallpaper_surface=center;center.apply(core.preferences());center_layout=QVBoxLayout(center);center_layout.setContentsMargins(0,0,0,0);center_layout.setSpacing(0)
        topbar=DecoratedFrame('topbar');topbar.setObjectName('topbar');top=QHBoxLayout(topbar);top.setContentsMargins(28,12,28,12)
        self.title=label('新任务','role');self.title.setMinimumWidth(0);self.title.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);top.addWidget(self.title,1)
        self.permission_badge=label('标准','badge');top.addWidget(self.permission_badge)
        self.api_button=AnchoredComboBox();self.api_button.setObjectName('apiPicker');self.api_button.setEditable(False);self.api_button.setMaximumWidth(150)
        self.api_button.setToolTip('为当前对话选择已保存的 API');self.api_button.currentIndexChanged.connect(self.select_api);top.addWidget(self.api_button)
        self.model_button=AnchoredComboBox();self.model_button.setObjectName('modelPicker');self.model_button.setEditable(False)
        self.model_button.setMaxVisibleItems(12);self.model_button.currentTextChanged.connect(self.select_model)
        center_layout.addWidget(topbar)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().setObjectName('wallpaperLayer')
        self.content=QWidget();self.content.setObjectName('wallpaperLayer');self.conversation=QVBoxLayout(self.content);self.conversation.setContentsMargins(32,26,32,20);self.conversation.setSpacing(8)
        self.scroll.setWidget(self.content);center_layout.addWidget(self.scroll,1)
        status_bar=QWidget();status_bar.setObjectName('wallpaperLayer');status_layout=QHBoxLayout(status_bar);status_layout.setContentsMargins(33,9,26,8);status_layout.setSpacing(14)
        self.status=label('准备就绪','status');status_layout.addWidget(self.status,1);status_layout.addWidget(self.thinking_indicator);center_layout.addWidget(status_bar)
        bottom=QWidget();bottom.setObjectName('wallpaperLayer');bottom_layout=QVBoxLayout(bottom);bottom_layout.setContentsMargins(28,7,28,18);bottom_layout.setSpacing(10)
        composer=DecoratedFrame('composer');composer.setObjectName('composer');compose=QVBoxLayout(composer);compose.setContentsMargins(16,14,14,12);compose.setSpacing(8)
        self.attachment_list=ImageList();self.attachment_list.hide();self.attachment_list.setToolTip('双击图片可移除；图片较多时可横向滚动')
        self.attachment_list.itemDoubleClicked.connect(lambda item:self.remove_attachment(self.attachment_list.row(item)));compose.addWidget(self.attachment_list)
        self.prompt=Prompt();self.prompt.setObjectName('composerInput');self.prompt.setFixedHeight(70);self.prompt.setPlaceholderText('随心输入，或拖入参考图…');self.prompt.setToolTip('Enter 发送 · Shift+Enter 换行 · 支持粘贴、拖入图片及纯图片发送');self.prompt.submitted.connect(self.send)
        self.prompt.attached.connect(self.add_files);self.prompt.pasted_image.connect(self.paste_image);compose.addWidget(self.prompt)
        self.model_popover=ModelSettingsPopup(self,Qt.Popup|Qt.FramelessWindowHint);self.model_popover.setObjectName('modelPopover')
        self.model_popover.setAttribute(Qt.WA_TranslucentBackground)
        options=QVBoxLayout(self.model_popover);options.setContentsMargins(18,16,18,16);options.setSpacing(10)
        options.addWidget(label('模型','section'));options.addWidget(self.model_button)
        options.addWidget(label('思考强度','section'))
        self.reasoning_button=AnchoredComboBox();self.reasoning_button.setAccessibleName('思考强度')
        self.reasoning_button.currentIndexChanged.connect(self.select_reasoning);options.addWidget(self.reasoning_button)
        self.reasoning_note=label('按模型能力提供选项','muted',True);options.addWidget(self.reasoning_note);self.model_popover.hide()
        toolbar=QHBoxLayout();toolbar.setSpacing(6)
        self.attach_button=button('＋',self.choose_images,'attachControl');self.attach_button.setFixedSize(34,34);self.attach_button.setAccessibleName('添加图片');self.attach_button.setToolTip('添加图片 · 也可以直接粘贴或拖入');toolbar.addWidget(self.attach_button)
        self.mode=AnchoredComboBox();self.mode.setObjectName('composerMode');self.mode.addItem('Agent','agent');self.mode.addItem('对话','chat');self.mode.addItem('生图','image');self.mode.setFixedWidth(90);self.mode.setAccessibleName('任务模式');toolbar.addWidget(self.mode)
        toolbar.addStretch(1)
        self.model_settings=ModelSettingsButton();self.model_settings.setObjectName('modelSettings');self.model_settings.setMinimumWidth(60);self.model_settings.setMaximumWidth(280);self.model_settings.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed);self.model_settings.setFixedHeight(34);self.model_settings.clicked.connect(self.show_model_settings);toolbar.addWidget(self.model_settings,3)
        self.stop_button=button('■',self.stop,'composerStop');self.stop_button.setFixedSize(36,36);self.stop_button.setAccessibleName('停止当前任务');self.stop_button.setToolTip('停止当前任务');self.stop_button.hide();toolbar.addWidget(self.stop_button)
        self.send_button=button('↑',self.send,'composerSend');self.send_button.setFixedSize(36,36);self.send_button.setAccessibleName('发送');toolbar.addWidget(self.send_button);compose.addLayout(toolbar)
        bottom_layout.addWidget(composer)
        center_layout.addWidget(bottom);splitter.addWidget(center)
        inspector=DecoratedFrame('inspector');inspector.setObjectName('inspector');inspector.setMinimumWidth(340);panel=QVBoxLayout(inspector);panel.setContentsMargins(18,24,18,18);panel.setSpacing(18)
        panel.addWidget(label('任务工作台','role'));panel.addWidget(label('工具 · 文件 · 浏览器 · 协作','muted'))
        self.plan=label('模型会根据任务安排步骤。','muted',True);panel.addWidget(self.plan)
        self.tabs=QTabWidget();self.tools=OrnamentedTree();self.tools.setHeaderHidden(True);self.tools.itemClicked.connect(self.tool_selected)
        self.changes=QListWidget();self.changes.itemClicked.connect(self.change_selected)
        self.tabs.addTab(self.tools,'工具记录');self.tabs.addTab(self.changes,'文件变更');panel.addWidget(self.tabs,1)
        self.browser_panel=QWidget();browser_layout=QVBoxLayout(self.browser_panel);browser_layout.setContentsMargins(10,15,10,13)
        self.browser_title=label('尚未打开页面','role',True);self.browser_url=label('Agent 会按任务打开独立浏览器。','muted',True)
        browser_layout.addWidget(self.browser_title);browser_layout.addWidget(self.browser_url)
        self.browser_preview=QPushButton('页面截图会显示在这里');self.browser_preview.setMinimumHeight(185);self.browser_preview.clicked.connect(self.view_browser_capture);browser_layout.addWidget(self.browser_preview)
        browser_actions=QHBoxLayout();self.browser_show=button('显示浏览器',self.show_browser);browser_actions.addWidget(self.browser_show)
        self.browser_refresh=button('刷新预览',self.refresh_browser);browser_actions.addWidget(self.browser_refresh);browser_layout.addLayout(browser_actions)
        browser_layout.addWidget(label('独立浏览器配置。密码、验证码等可在浏览器窗口手动处理。','muted',True));browser_layout.addStretch()
        self.tabs.addTab(self.browser_panel,'浏览器')
        self.desktop_panel=QWidget();desktop_layout=QVBoxLayout(self.desktop_panel);desktop_layout.setContentsMargins(10,15,10,13)
        self.desktop_title=label('尚未观察桌面','role',True);desktop_layout.addWidget(self.desktop_title)
        self.desktop_preview=QPushButton('Agent 的桌面截图会显示在这里');self.desktop_preview.setMinimumHeight(185);self.desktop_preview.clicked.connect(self.view_desktop_capture);desktop_layout.addWidget(self.desktop_preview)
        self.desktop_note=label('按需截图 · 主 Agent 统一控制鼠标键盘','muted',True);desktop_layout.addWidget(self.desktop_note)
        desktop_layout.addWidget(button('停止当前任务',self.stop,'stop'))
        desktop_layout.addWidget(label('Ctrl+Alt+F10 全局停止。密码和安全提示请手动处理。','muted',True));desktop_layout.addStretch()
        self.tabs.addTab(self.desktop_panel,'桌面')
        self.agents=QListWidget();self.agents.itemClicked.connect(self.agent_selected);self.tabs.addTab(self.agents,'协作')
        self.detail=QTextBrowser();self.detail.setMinimumHeight(160);self.detail.setMaximumHeight(310);self.detail.setOpenExternalLinks(False)
        self.detail.setPlaceholderText('选中记录，查看执行详情');self.detail.setFont(QFont('Microsoft YaHei UI',10));panel.addWidget(self.detail)
        actions=QHBoxLayout();self.diff_button=button('查看完整差异',self.show_diff);self.undo_button=button('撤销修改',self.undo_change)
        actions.addWidget(self.diff_button);actions.addWidget(self.undo_button);panel.addLayout(actions)
        self.diff_button.setEnabled(False);self.undo_button.setEnabled(False);splitter.addWidget(inspector)
        self.agent_stop_button=button('停止选中助手',self.stop_selected_agent);self.agent_stop_button.setEnabled(False);panel.addWidget(self.agent_stop_button)
        splitter.setSizes([815,345]);splitter.setStretchFactor(0,1);splitter.setStretchFactor(1,0)
        QShortcut(QKeySequence('Ctrl+N'),self,activated=self.new_chat)
        QShortcut(QKeySequence('Ctrl+,'),self,activated=self.show_settings)
        self.mode.currentIndexChanged.connect(self.update_status)
        self.load_sessions();self.update_models()
        items=core.sessions()
        if items: self.open_session(items[0]['id'])
        else: self.new_chat()
        self.setup_tray()

    def nativeEvent(self,eventType,message):
        if os.name=='nt':
            hit=native_resize_hit(self,message)
            if hit is not None:return True,hit
        return super().nativeEvent(eventType,message)

    @property
    def worker(self):
        return self.workers.get(self.current['id']) if self.current else None

    @worker.setter
    def worker(self,value):
        # Also supports diagnostic workers; production registers by task id.
        if self.current:
            if value is None:self.workers.pop(self.current['id'],None)
            else:self.workers[self.current['id']]=value

    def remember_draft(self):
        if self.current:
            self.drafts[self.current['id']]={'text':self.prompt.toPlainText(),'attachments':self.attachments,'mode':self.mode.currentData()}

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():return
        self.tray=QSystemTrayIcon(self.windowIcon(),self)
        self.tray.setToolTip(APP_TITLE+' · 点击打开，右键退出')
        self.tray_menu=QMenu(self)
        self.tray_menu.addAction('打开 Anllm',self.present_window)
        self.tray_stop=self.tray_menu.addAction('停止所有任务 · Ctrl+Alt+F10',self.stop_all)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction('退出 Anllm',self.request_exit)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.messageClicked.connect(self.present_window)
        self.tray.show()

    def tray_activated(self,reason):
        if reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick):self.present_window()

    def present_window(self):
        if self.exit_requested:return
        self.showNormal();self.raise_();self.activateWindow()
        if self.approval_dialog:
            self.approval_dialog.show();self.approval_dialog.raise_();self.approval_dialog.activateWindow()
        else:QTimer.singleShot(0,self.next_approval)

    def notify_background(self,title,text):
        if self.tray and not self.isVisible() and not self.exit_requested:
            self.tray.showMessage(title,text,QSystemTrayIcon.Information,5000)

    def hide_to_tray(self):
        if self.approval_dialog:self.approval_dialog.hide()
        self.hide()
        if not self.tray_notice_shown:
            self.notify_background('Anllm 已收起到托盘','任务会继续运行。点击图标打开，右键选择“退出 Anllm”可结束程序。')
            self.tray_notice_shown=True

    def request_exit(self):
        if self.exit_requested:return
        self.exit_requested=True;self.import_queue.clear();self.stop_all()
        if self.approval_dialog:self.approval_dialog.reject()
        self.status.setText('正在结束任务并退出…')
        if self.tray:self.tray.setToolTip('Anllm · 正在退出…')
        self.finish_exit()

    def finish_exit(self):
        if not self.exit_requested:return
        if self.workers or self.background_workers:
            self.exit_timer.start();return
        browser_bridge.SERVICE.shutdown()
        if self.tray:self.tray.hide()
        if self.global_stop:self.global_stop.close()
        self.hide();self.close()
        QApplication.instance().quit()

    def update_models(self):
        identifier=self.current.get('api_profile_id') if self.current else None
        config=core.shared.public_settings(identifier);models=core.shared.cached_models(config['id'])
        self.api_button.blockSignals(True);self.api_button.clear()
        for profile in core.shared.api_profiles():self.api_button.addItem(profile['name'],profile['id'])
        self.api_button.setCurrentIndex(self.api_button.findData(config['id']));self.api_button.blockSignals(False)
        self.model_button.blockSignals(True);self.model_button.clear();self.model_button.addItems(models)
        selected=self.current.get('chat_model') if self.current else config['chat_model']
        if selected in models:self.model_button.setCurrentText(selected)
        elif models:self.model_button.setCurrentIndex(-1);self.model_button.setPlaceholderText('请选择模型')
        elif not models:self.model_button.addItem('请在设置中读取模型')
        self.model_button.setEnabled(bool(models));self.model_button.blockSignals(False)
        self.permission_badge.setText(core.PERMISSION_LABELS[core.preferences()['permission_mode']])
        self.api_button.setEnabled(not bool(self.worker));self.model_button.setEnabled(bool(models) and not self.worker)
        self.model_settings.setEnabled(bool(models) and not self.worker)
        self.update_reasoning(config)

    def update_reasoning(self,config=None):
        config=config or core.shared.public_settings(self.current.get('api_profile_id') if self.current else None)
        model=self.current.get('chat_model','') if self.current else config.get('chat_model','')
        choices=reasoning.options(config,model);key=config['id']+'/'+model
        selected=self.current.get('reasoning_choices',{}).get(key,'') if self.current else ''
        self.reasoning_button.blockSignals(True);self.reasoning_button.clear();self.reasoning_button.addItem('默认（模型决定）','')
        for value in choices:self.reasoning_button.addItem(reasoning.LABELS.get(value,value)+' · '+value,value)
        self.reasoning_button.setCurrentIndex(max(0,self.reasoning_button.findData(selected)));self.reasoning_button.blockSignals(False)
        self.reasoning_button.setEnabled(bool(choices) and not self.worker and self.mode.currentData()!='image')
        self.reasoning_note.setText('按模型原生档位' if choices else '此模型未提供可调档位')
        self.reasoning_button.setToolTip('默认使用模型自己的设置；较高强度通常需要更多时间和 API 用量。' if choices else '未确认可用的思考强度，使用模型默认设置。')
        self.update_model_summary()

    def update_model_summary(self):
        value=self.reasoning_button.currentData() or ''
        effort=reasoning.LABELS.get(value,value) if value else '默认'
        self.model_settings.setSummary(self.model_button.currentText() or '选择模型',effort)

    def show_model_settings(self):
        if not self.model_settings.isEnabled():return
        self.model_popover.ensurePolished();self.model_popover.setFixedWidth(320);self.model_popover.adjustSize()
        screen=self.model_settings.screen().availableGeometry();size=self.model_popover.size()
        anchor=self.model_settings.mapToGlobal(QPoint(self.model_settings.width(),0))
        x=max(screen.left(),min(anchor.x()-size.width(),screen.right()-size.width()+1))
        y=anchor.y()-size.height()-8
        if y<screen.top():y=self.model_settings.mapToGlobal(QPoint(0,self.model_settings.height())).y()+8
        y=max(screen.top(),min(y,screen.bottom()-size.height()+1))
        self.model_popover.move(x,y);self.model_popover.show();self.model_button.setFocus()

    def select_reasoning(self):
        if not self.current or self.worker:return
        key=self.current['api_profile_id']+'/'+self.current.get('chat_model','')
        self.current.setdefault('reasoning_choices',{})[key]=self.reasoning_button.currentData() or ''
        core.save_session(self.current)
        self.update_model_summary()

    def select_model(self,name):
        if self.worker:return
        if not self.current or name not in core.shared.cached_models(self.current['api_profile_id']):return
        try:self.current['chat_model']=name;core.save_session(self.current);self.update_reasoning();self.update_status()
        except Exception as error:self.status.setText(core.scrub(error));self.update_models()

    def select_api(self):
        if self.worker or not self.current:return
        identifier=self.api_button.currentData()
        if not identifier or identifier==self.current.get('api_profile_id'):return
        config=core.shared.settings(identifier)
        self.current.update(api_profile_id=identifier,chat_model=config['chat_model']);core.save_session(self.current);self.update_models();self.update_status()

    def update_status(self):
        self.update_reasoning()
        if self.worker:
            self.status.setText(self.task_status.get(self.current['id'],'任务正在后台执行…'));self.thinking_indicator.start('正在执行')
        else:
            self.thinking_indicator.stop()
            messages={'agent':'Agent · 桌面、浏览器与协作已就绪','chat':'对话 · 根据请求自动生图','image':'生图 · 使用附图或上一张图作为参考'}
            self.status.setText(messages[self.mode.currentData()]+' · '+core.PERMISSION_LABELS[core.preferences()['permission_mode']])

    def clear_conversation(self):
        while self.conversation.count():
            item=self.conversation.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        self.cards={}

    def welcome(self):
        widget=QWidget();widget.setObjectName('wallpaperLayer');layout=QVBoxLayout(widget);layout.setContentsMargins(8,60,8,38);layout.setSpacing(20)
        layout.addWidget(label('✧','symbol'));layout.addWidget(label('A N L L M   /   Y O U R   W O R K S P A C E','eyebrow'))
        layout.addWidget(label('想法，在这里成形。','headline'))
        layout.addWidget(label('读写项目、操作网页、协作完成任务。\n需要图片时，自动交给创作模型。','muted',True))
        suggestions=[('▱  检查项目','分析当前项目结构，找出主要入口和可以改进的地方，先不要修改文件。'),
            ('⌘  实现功能','请先检查当前项目，告诉我你需要了解哪些需求，然后帮助我实现功能并验证。'),
            ('✦  创作图片','帮我生成一张银白色未来建筑的图片，宁静沙丘、电影质感、不要文字。')]
        suggestions.extend([('↗  浏览网页','打开指定网页，先读取并总结内容，再告诉我可执行的下一步。'),('✧  并行协作','让两个助手分别检查项目结构和测试覆盖，最后汇总具体发现。')])
        grid=QGridLayout();grid.setSpacing(10)
        for i,(title,text) in enumerate(suggestions):
            item=button(title,lambda checked=False,t=text:self.fill_prompt(t),'suggestion');item.setMinimumHeight(65);grid.addWidget(item,i//3,i%3)
        layout.addSpacing(12);layout.addLayout(grid)
        layout.addWidget(label('先选择项目文件夹，再描述任务。API 与模型可以随时调整。','muted',True))
        self.conversation.addWidget(widget);self.conversation.addStretch()

    def fill_prompt(self,text): self.prompt.setPlainText(text);self.prompt.setFocus()

    def render_conversation(self,scroll=True):
        self.clear_conversation()
        if not self.current['messages']: self.welcome();return
        if len(self.current['messages'])>self.visible_messages:
            remaining=len(self.current['messages'])-self.visible_messages
            self.conversation.addWidget(button('查看更早的消息（'+str(remaining)+' 条）',self.show_more_messages,'quiet'))
        for message in self.current['messages'][-self.visible_messages:]:
            card=MessageCard(message);self.cards[message['id']]=card;self.conversation.addWidget(card)
        self.conversation.addStretch()
        if scroll:self.scroll_bottom()

    def show_more_messages(self):
        self.visible_messages+=40;self.render_conversation(scroll=False)
        QTimer.singleShot(0,lambda:self.scroll.verticalScrollBar().setValue(0))

    def scroll_bottom(self):
        if not self.scroll_timer.isActive():self.scroll_timer.start()

    def load_sessions(self):
        self.session_list.clear()
        for session in core.sessions():
            title=self.live_sessions.get(session['id'],session)['title']
            item=QListWidgetItem(('★  ' if session['favorite'] else '◷  ')+title+(' · 运行中' if session['id'] in self.workers else ''));item.setData(Qt.UserRole,session['id']);item.setData(Qt.UserRole+1,session['favorite'])
            item.setToolTip(title+'\n'+session.get('workspace','')+'\n'+('已收藏 · ' if session['favorite'] else '')+'右键管理，同组拖动排序')
            if session['favorite']:item.setForeground(QColor('#e8cc87'))
            self.session_list.addItem(item)
            if self.current and session['id']==self.current['id']: self.session_list.setCurrentItem(item)

    def persist_task_order(self):
        try:
            core.save_task_order([self.session_list.item(row).data(Qt.UserRole) for row in range(self.session_list.count())])
            QTimer.singleShot(0,self.load_sessions);self.status.setText('任务顺序已保存 · 收藏任务置顶，同组可自由排序')
        except Exception as error:self.status.setText(core.scrub(error));self.load_sessions()

    def show_task_menu(self,position=None):
        item=self.session_list.itemAt(position) if position is not None and not isinstance(position,bool) else self.session_list.currentItem()
        if not item:return
        identifier=item.data(Qt.UserRole);favorite=bool(item.data(Qt.UserRole+1));menu=QMenu(self)
        action=menu.addAction('取消收藏' if favorite else '收藏任务');action.triggered.connect(lambda:self.toggle_task_favorite(identifier,not favorite))
        group=[self.session_list.item(row).data(Qt.UserRole) for row in range(self.session_list.count()) if bool(self.session_list.item(row).data(Qt.UserRole+1))==favorite]
        index=group.index(identifier);menu.addSeparator()
        for text,direction,enabled in [('上移',-1,index>0),('下移',1,index<len(group)-1),('移到顶部','top',index>0)]:
            action=menu.addAction(text);action.setEnabled(enabled);action.triggered.connect(lambda checked=False,value=direction:self.move_task(identifier,value))
        menu.addSeparator();action=menu.addAction('删除任务…');action.setEnabled(identifier not in self.workers);action.triggered.connect(lambda:self.delete_task(identifier))
        point=self.session_list.viewport().mapToGlobal(position) if position is not None and not isinstance(position,bool) else self.task_actions.mapToGlobal(self.task_actions.rect().bottomLeft())
        menu.exec(point)

    def toggle_task_favorite(self,identifier,favorite):
        try:core.favorite_session(identifier,favorite);self.load_sessions();self.status.setText('任务已收藏并置顶' if favorite else '已取消收藏')
        except Exception as error:self.status.setText(core.scrub(error))

    def move_task(self,identifier,direction):
        try:core.move_session(identifier,direction);self.load_sessions();self.status.setText('任务顺序已保存')
        except Exception as error:self.status.setText(core.scrub(error))

    def delete_task(self,identifier):
        if identifier in self.workers:
            self.status.setText('请先停止这个任务，再删除它。');return
        try:
            session=core.load_session(identifier)
            if QMessageBox.question(self,'删除任务','删除“'+session['title']+'”？\n聊天记录将从任务列表移除。项目文件和生成图片会保留。',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
            core.delete_session(identifier);self.drafts.pop(identifier,None);self.live_sessions.pop(identifier,None)
            if self.current and self.current['id']==identifier:
                remaining=core.sessions()
                if remaining:self.open_session(remaining[0]['id'])
                else:self.new_chat()
            else:self.load_sessions()
            self.status.setText('任务已删除 · 项目文件和图片已保留')
        except Exception as error:self.status.setText(core.scrub(error))

    def select_session(self,item):
        self.open_session(item.data(Qt.UserRole))

    def open_session(self,identifier):
        if self.import_worker:return
        self.remember_draft()
        self.visible_messages=40;self.current=self.live_sessions.get(identifier) or core.load_session(identifier)
        draft=self.drafts.get(identifier,{})
        self.attachments=draft.get('attachments',[]);self.prompt.setPlainText(draft.get('text',''))
        self.mode.setCurrentIndex(max(0,self.mode.findData(draft.get('mode','agent'))))
        self.render_attachments();self.render_conversation();self.render_inspector()
        self.folder_label.setText(self.current['workspace']);self.title.setText(self.current['title']);self.load_sessions();self.set_busy(bool(self.worker));self.update_status()

    def new_chat(self):
        if self.import_worker or self.exit_requested:return
        session=core.new_session();self.open_session(session['id']);self.prompt.setFocus()

    def choose_folder(self):
        if self.import_worker: return
        selected=QFileDialog.getExistingDirectory(self,'选择工作项目',self.current['workspace'])
        if not selected: return
        try: prefs=core.save_preferences({**core.preferences(),'workspace':selected})
        except Exception as error: QMessageBox.warning(self,'工作目录',str(error));return
        # Workspace is immutable for a task once it has history.
        if self.current['messages']:
            session=core.new_session(prefs['workspace']);self.open_session(session['id'])
        else:
            self.current['workspace']=prefs['workspace'];core.save_session(self.current);self.folder_label.setText(prefs['workspace']);self.load_sessions()

    def show_settings(self):
        if self.import_worker: return
        dialog=SettingsDialog(self)
        if self.worker:dialog.use_current.setChecked(False);dialog.use_current.setEnabled(False)
        dialog.exec();self.update_models();self.wallpaper_surface.apply(core.preferences());self.update_status()

    def choose_images(self):
        files,_=QFileDialog.getOpenFileNames(self,'添加参考图','','图片 (*.png *.jpg *.jpeg *.webp)');self.add_files(files)

    def add_files(self,files):
        self.import_queue.extend(('file',filename) for filename in files);self.start_import()

    def paste_image(self,image):
        from PySide6.QtGui import QImage
        self.import_queue.append(('clipboard',QImage(image)));self.start_import()

    def start_import(self):
        if self.exit_requested or self.import_worker or not self.import_queue:return
        batch=self.import_queue;self.import_queue=[]
        worker=FunctionWorker(lambda:import_attachments(batch));self.import_worker=worker;self.background_workers.append(worker)
        for widget in (self.new_button,self.folder_button,self.settings_button,self.session_list,self.task_actions):widget.setEnabled(False)
        self.send_button.setEnabled(False);self.status.setText('正在后台添加 '+str(len(batch))+' 张图片…')
        def received(result):
            self.attachments.extend(result['attachments']);self.render_attachments()
            self.status.setText(core.scrub('；'.join(result['errors'])) if result['errors'] else '已添加 '+str(len(self.attachments))+' 张图片，可直接发送。')
        worker.result.connect(received);worker.failed.connect(lambda error:self.status.setText(core.scrub(error)))
        def finished():
            self.background_workers.remove(worker);self.import_worker=None;worker.deleteLater()
            if self.import_queue:self.start_import()
            else:
                for widget in (self.new_button,self.folder_button,self.settings_button,self.session_list,self.task_actions,self.send_button):widget.setEnabled(True)
                self.set_busy(bool(self.worker));self.prompt.setFocus()
        worker.finished.connect(finished);worker.start()

    def render_attachments(self):
        self.attachment_list.clear();self.attachment_list.setVisible(bool(self.attachments))
        for attachment in self.attachments:
            self.attachment_list.add_image({**attachment,'path':str(core.shared.image_path(attachment['name']))})

    def remove_attachment(self,index):
        self.attachments.pop(index);self.render_attachments()

    def set_busy(self,busy):
        self.model_popover.hide()
        for widget in (self.new_button,self.folder_button,self.settings_button,self.task_actions,self.session_list,self.attach_button):widget.setEnabled(not bool(self.import_worker))
        self.update_models();self.mode.setEnabled(not busy)
        self.send_button.setEnabled(not busy and not self.import_worker)
        self.send_button.setToolTip('当前任务执行中；可以切换到其他任务发送，或在此保留下一条草稿。' if busy else '发送到当前任务')
        self.prompt.setReadOnly(False);self.send_button.setVisible(not busy);self.stop_button.setVisible(busy);self.stop_button.setEnabled(busy and not getattr(self.worker,'stopping',threading.Event()).is_set())
        self.browser_refresh.setEnabled(True)
        self.undo_button.setEnabled(not self.workspace_busy() and bool(self.selected_change()) and not self.selected_change().get('restored'))

    def workspace_busy(self):
        if not self.current:return False
        workspace=str(Path(self.current['workspace']).resolve()).casefold()
        return bool(self.worker) or any(str(Path(session['workspace']).resolve()).casefold()==workspace for identifier,session in self.live_sessions.items() if identifier in self.workers)

    def send(self):
        text=self.prompt.toPlainText().strip()
        if self.worker or self.import_worker or (not text and not self.attachments): return
        if len(text)>16000: self.status.setText('消息最长 16000 字。');return
        identifier=self.current['api_profile_id']
        if not core.shared.public_settings(identifier)['key_configured']: self.show_settings();return
        if self.mode.currentData()!='image' and self.current.get('chat_model') not in core.shared.cached_models(identifier):
            self.status.setText('请先为当前 API 读取模型，再选择聊天模型。');return
        if not Path(self.current['workspace']).is_dir(): self.status.setText('项目目录不存在，请重新选择。');return
        self.prompt.clear();attachments=self.attachments;self.attachments=[];self.render_attachments()
        # Worker owns an independent session snapshot, so UI mutations cannot race persistence.
        snapshot=copy.deepcopy(self.current)
        snapshot.setdefault('reasoning_choices',{})[identifier+'/'+snapshot.get('chat_model','')]=self.reasoning_button.currentData() or ''
        self.worker=AgentWorker(snapshot,text,attachments,self.mode.currentData());self.worker.task_id=self.current['id']
        self.live_sessions[self.current['id']]=self.current
        self.worker.event.connect(self.on_event);self.worker.result.connect(self.task_result);self.worker.finished.connect(self.task_finished)
        self.current['messages'].append({'id':'pending-user','role':'user','text':text,'attachments':attachments})
        if len(self.current['messages'])==1:self.current['title']=text[:32] or '图片消息 · '+str(len(attachments))+' 张'
        self.title.setText(self.current['title'])
        self.task_status[self.current['id']]='正在思考任务…';self.drafts.pop(self.current['id'],None)
        self.current.pop('plan',None);self.show_plan({'steps':['正在分析任务…']})
        self.render_conversation();self.set_busy(True);self.status.setText('正在思考任务…');self.thinking_indicator.start('正在思考');self.load_sessions();self.worker.start()

    def stop_task(self,identifier):
        worker=self.workers.get(identifier)
        if worker:
            worker.cancel();self.task_status[identifier]='正在停止…'
            if self.approval_dialog and self.approval_owner==identifier:self.approval_dialog.reject()
            if self.current and self.current['id']==identifier:
                self.stop_button.setEnabled(False);self.status.setText('正在停止…');self.thinking_indicator.stop()

    def stop(self):
        if self.current:self.stop_task(self.current['id'])

    def stop_all(self):
        for identifier in list(self.workers):self.stop_task(identifier)

    def record_event(self,identifier,event):
        session=self.live_sessions.get(identifier)
        if not session:return
        kind=event['type']
        if kind=='message':session['messages'].append(copy.deepcopy(event['message']))
        elif kind in ('text','image'):
            message=next((m for m in session['messages'] if m['id']==event['message_id']),None)
            if message is not None:
                if kind=='text':message['text']=event['text']
                else:message.setdefault('images',[]).append(copy.deepcopy(event['image']))
        elif kind in ('tool_start','tool_end'):session['events'].append(copy.deepcopy(event))
        elif kind=='change':session['changes'].append(copy.deepcopy(event['change']))
        elif kind=='plan':session['plan']=copy.deepcopy(event['plan'])
        elif kind=='browser':session.setdefault('browser_pages',{})[event['browser']['page_id']]=copy.deepcopy(event['browser'])
        elif kind=='desktop':session['desktop_capture']=copy.deepcopy(event['desktop'])
        elif kind=='agent':
            rows=session.setdefault('agents',[]);record=copy.deepcopy(event['agent'])
            index=next((i for i,r in enumerate(rows) if r['id']==record['id']),None)
            if index is None:rows.append(record)
            else:rows[index]=record
        if kind=='status':self.task_status[identifier]=event['text']
        elif kind in ('tool_start','tool_end'):self.task_status[identifier]=('正在调用：' if kind=='tool_start' else '已完成：')+TOOL_NAMES.get(event['name'],event['name'])
        elif kind in ('approval','question'):self.task_status[identifier]='等待你的'+('回答' if kind=='question' else '确认')+'…'

    def on_event(self,event):
        sender=self.sender();identifier=getattr(sender,'task_id',self.current['id'] if self.current else None)
        if identifier not in self.workers:return
        self.record_event(identifier,event)
        kind=event['type']
        if kind in ('approval','question'):
            if self.exit_requested:return
            self.task_status[identifier]='等待你的'+('回答' if kind=='question' else '确认')+'…'
            event={**event,'session_id':identifier,'task_title':self.live_sessions.get(identifier,self.current).get('title','任务')}
            self.approval_queue.append(event)
            self.notify_background('Anllm 需要你的'+('回答' if kind=='question' else '确认'),event['task_title']+'：打开窗口查看请求。')
            QTimer.singleShot(0,self.next_approval)
        if not self.current or identifier!=self.current['id']:return
        if kind in ('approval','question'):self.status.setText(self.task_status[identifier]);self.thinking_indicator.stop()
        if kind=='message':
            card=MessageCard(event['message']);self.cards[event['message']['id']]=card
            self.conversation.insertWidget(max(0,self.conversation.count()-1),card);self.scroll_bottom()
        elif kind=='text':
            card=self.cards.get(event['message_id'])
            if card: card.set_text(event['text']);self.scroll_bottom()
        elif kind=='image':
            card=self.cards.get(event['message_id'])
            if card: card.add_image(event['image']);self.scroll_bottom()
        elif kind in ('tool_start','tool_end'):
            self.add_tool_event(event);self.status.setText(('正在调用：' if kind=='tool_start' else '已完成：')+TOOL_NAMES.get(event['name'],event['name']))
            if kind=='tool_start': self.thinking_indicator.start('正在执行')
            else: self.thinking_indicator.stop()
        elif kind=='change': self.add_change(event['change'])
        elif kind=='plan': self.show_plan(event['plan'])
        elif kind=='status': self.status.setText(event['text'])
        elif kind=='browser': self.update_browser(event['browser'])
        elif kind=='desktop':
            self.current['desktop_capture']=event['desktop'];self.update_desktop(event['desktop'])
        elif kind=='agent': self.update_agent(event['agent'])
    def next_approval(self):
        if self.exit_requested or (self.tray and not self.isVisible()) or self.approval_dialog:return
        while self.approval_queue:
            event=self.approval_queue.pop(0);identifier=event['session_id'];worker=self.workers.get(identifier)
            if not worker or getattr(worker,'stopping',threading.Event()).is_set():continue
            if event['type']=='question':
                dialog=QuestionDialog(event['questions'],lambda:self.stop_task(identifier),self)
            else:dialog=ApprovalDialog(event,self)
            dialog.setWindowTitle(event.get('task_title','任务')+' · '+dialog.windowTitle())
            dialog.setModal(False);dialog.setWindowModality(Qt.NonModal)
            self.approval_dialog=dialog;self.approval_owner=identifier
            def answered(result,dialog=dialog,event=event,worker=worker):
                accepted=result==QDialog.Accepted
                value=dialog.answer(accepted) if event['type']=='question' else accepted
                if self.workers.get(event['session_id']) is worker:worker.resolve(event['id'],value)
                self.approval_dialog=None;self.approval_owner=None;dialog.deleteLater()
                QTimer.singleShot(0,self.next_approval)
            dialog.finished.connect(answered);dialog.show();return

    def task_result(self,session):
        identifier=session['id'];self.live_sessions[identifier]=session
        if self.current and self.current['id']==identifier:
            self.current=session;self.render_conversation();self.render_inspector();self.title.setText(session['title'])
        self.load_sessions()

    def task_finished(self):
        sender=self.sender();identifier=getattr(sender,'task_id',None)
        if identifier is None:identifier=next((k for k,v in self.workers.items() if v is sender),self.current['id'] if self.current else None)
        worker=self.workers.pop(identifier,None)
        if worker:worker.deleteLater()
        self.approval_queue=[event for event in self.approval_queue if event['session_id']!=identifier]
        if self.approval_dialog and self.approval_owner==identifier:self.approval_dialog.reject()
        title=self.live_sessions.get(identifier,{}).get('title','任务')
        self.task_status.pop(identifier,None);self.live_sessions.pop(identifier,None)
        self.set_busy(bool(self.worker));self.update_status();self.load_sessions()
        self.notify_background('Anllm 任务已结束',title+'：打开窗口查看结果。')
        QTimer.singleShot(0,self.next_approval)

    def show_plan(self,plan):
        self.plan.setText('\n'.join(('✓  ' if i<plan.get('completed',0) else '○  ')+text for i,text in enumerate(plan.get('steps',[]))))

    def render_inspector(self):
        self.tools.clear();self.changes.clear();self.detail.clear();self.diff_button.setEnabled(False);self.undo_button.setEnabled(False)
        self.agent_stop_button.setEnabled(False)
        self.show_plan(self.current.get('plan',{'steps':['模型会根据任务安排步骤。']}))
        for event in self.current.get('events',[]): self.add_tool_event(event)
        for change in self.current.get('changes',[]): self.add_change(change)
        self.agents.clear();self.agent_items={}
        for record in self.current.get('agents',[]): self.update_agent(record)
        pages=list(self.current.get('browser_pages',{}).values())
        if pages: self.update_browser(pages[-1])
        else:
            self.browser_state=None;self.browser_title.setText('尚未打开页面');self.browser_url.setText('Agent 会按任务打开独立浏览器。')
            self.browser_preview.setIcon(QIcon());self.browser_preview.setText('页面截图会显示在这里')
        self.update_desktop(self.current.get('desktop_capture'))

    def update_desktop(self,value):
        self.desktop_state=value
        if not value:
            self.desktop_title.setText('尚未观察桌面');self.desktop_preview.setIcon(QIcon());self.desktop_preview.setText('Agent 的桌面截图会显示在这里');return
        self.desktop_title.setText(value['window']['title'])
        self.desktop_note.setText('最近观察 · '+str(len(value.get('elements',[])))+' 个可见控件 · 操作前会重新查看')
        pixmap=thumbnail(value['screenshot'],QSize(550,370))
        if not pixmap.isNull():
            self.desktop_preview.setText('');self.desktop_preview.setIcon(QIcon(pixmap));self.desktop_preview.setIconSize(QSize(275,185))
        else:self.desktop_preview.setIcon(QIcon());self.desktop_preview.setText('旧截图已清理；可让 Agent 重新查看')

    def view_desktop_capture(self):
        if not self.desktop_state:return
        dialog=QDialog(self);dialog.setWindowTitle('桌面观察 · '+self.desktop_state['window']['title']);dialog.resize(1000,740)
        layout=QVBoxLayout(dialog);picture=QLabel();picture.setAlignment(Qt.AlignCenter)
        picture.setPixmap(thumbnail(self.desktop_state['screenshot'],QSize(1600,1340)).scaled(950,650,Qt.KeepAspectRatio,Qt.SmoothTransformation));layout.addWidget(picture)
        layout.addWidget(label('这是最近一次截图；Agent 的下一步操作会使用最新观察。','muted',True));dialog.exec()

    def add_tool_event(self,event):
        name=TOOL_NAMES.get(event['name'],event['name'])
        marker='○' if event['type']=='tool_start' else ('!' if event.get('error') else '✓')
        agent=' · '+event['agent_name'] if event.get('agent_name') else ''
        item=QTreeWidgetItem([marker+'  '+name+agent]);item.setData(0,Qt.UserRole,event)
        if event.get('error'): item.setForeground(0,QColor('#e5a3ae'))
        self.tools.addTopLevelItem(item);self.tools.scrollToBottom()

    def tool_selected(self,item):
        event=item.data(0,Qt.UserRole)
        self.detail.setPlainText(core.scrub(json.dumps(event.get('input'),ensure_ascii=False,indent=2) if event['type']=='tool_start' else event.get('output','')))

    def update_agent(self,record):
        statuses={'queued':'等待','running':'工作中','completed':'已完成','failed':'失败','stopped':'已停止'}
        item=self.agent_items.get(record['id'])
        if not item:
            item=QListWidgetItem();self.agents.addItem(item);self.agent_items[record['id']]=item
        item.setText(record['name']+' · '+statuses.get(record['status'],record['status'])+'\n'+str(record.get('tools',0))+' 次工具调用')
        item.setData(Qt.UserRole,record);item.setToolTip(record['task'])
        if self.agents.currentItem()==item: self.agent_selected(item)

    def agent_selected(self,item):
        record=item.data(Qt.UserRole)
        self.detail.setPlainText('任务：'+record['task']+'\n\n允许写入：'+str(record.get('write_paths',[]))+'\n\n'+record.get('text',''))
        self.agent_stop_button.setEnabled(bool(self.worker) and record['status'] in ('queued','running'))

    def stop_selected_agent(self):
        item=self.agents.currentItem()
        if item and self.worker: self.worker.cancel_agent(item.data(Qt.UserRole)['id'])

    def update_browser(self,value):
        self.browser_state=value;self.browser_title.setText(value.get('title') or '浏览器页面');self.browser_url.setText(value['url'])
        pixmap=thumbnail(value['screenshot'],QSize(550,370))
        if not pixmap.isNull():
            self.browser_preview.setText('');self.browser_preview.setIcon(QIcon(pixmap));self.browser_preview.setIconSize(QSize(275,185))

    def view_browser_capture(self):
        if not self.browser_state: return
        dialog=QDialog(self);dialog.setWindowTitle('浏览器页面预览');dialog.resize(1000,740)
        layout=QVBoxLayout(dialog);image=QLabel();image.setPixmap(QPixmap(self.browser_state['screenshot']).scaled(950,650,Qt.KeepAspectRatio,Qt.SmoothTransformation));image.setAlignment(Qt.AlignCenter);layout.addWidget(image)
        layout.addWidget(label(self.browser_state['url'],'muted',True));dialog.exec()

    def browser_function(self,method):
        if not self.browser_state: self.status.setText('请先让 Agent 打开一个网页。');return
        state=self.browser_state.copy()
        worker=FunctionWorker(lambda:browser_bridge.SERVICE.call_sync(method,state['owner'],state['page_id']))
        self.background_workers.append(worker)
        identifier=self.current['id']
        worker.result.connect(lambda result:self.update_browser(result) if isinstance(result,dict) and self.current['id']==identifier else None)
        worker.failed.connect(self.status.setText)
        def done(): self.background_workers.remove(worker);worker.deleteLater()
        worker.finished.connect(done);worker.start()

    def show_browser(self): self.browser_function('show')
    def refresh_browser(self):
        self.browser_function('read')

    def add_change(self,change):
        item=QListWidgetItem(('↶  ' if change.get('restored') else '±  ')+Path(change['path']).name)
        item.setData(Qt.UserRole,change);item.setToolTip(change['path']);self.changes.addItem(item)

    def selected_change(self): return self.changes.currentItem().data(Qt.UserRole) if self.changes.currentItem() else None

    def change_selected(self,item):
        change=item.data(Qt.UserRole);self.detail.setPlainText(change['diff']);self.diff_button.setEnabled(True)
        self.undo_button.setEnabled(not self.workspace_busy() and not change.get('restored'))

    def show_diff(self):
        change=self.selected_change()
        if not change: return
        dialog=QDialog(self);dialog.setWindowTitle('文件差异 · '+change['path']);dialog.resize(940,650)
        layout=QVBoxLayout(dialog);text=QTextEdit();text.setReadOnly(True);text.setFont(QFont('Consolas',11));text.setPlainText(change['diff']);layout.addWidget(text)
        layout.addWidget(button('关闭',dialog.accept));dialog.exec()

    def undo_change(self):
        change=self.selected_change()
        if not change or self.workspace_busy(): return
        if QMessageBox.question(self,'撤销此修改','恢复这一步修改之前的内容？\n'+change['path'])!=QMessageBox.Yes: return
        try:
            core.restore_change(self.current,change)
            # Include the user's undo action in future agent context.
            self.current['history'].append(core.ConversationMessage.from_user_text('我已撤销对 '+change['path']+' 的这一步修改。后续请重新读取文件。').model_dump())
            core.save_session(self.current);self.render_inspector();self.status.setText('已撤销。')
        except Exception as error: QMessageBox.warning(self,'无法撤销',str(error))

    def closeEvent(self,event):
        if self.exit_requested:
            event.accept();return
        event.ignore()
        if self.tray and QSystemTrayIcon.isSystemTrayAvailable():self.hide_to_tray()
        else:self.request_exit()


def app_icon():
    pixmap=QPixmap(128,128);pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(THEME['BG_CARD']));painter.setPen(Qt.NoPen);painter.drawRoundedRect(0,0,128,128,29,29)
    from PySide6.QtGui import QLinearGradient,QPainterPath
    gradient=QLinearGradient(20,18,105,110);gradient.setColorAt(0,QColor('#F6DB91'));gradient.setColorAt(.6,QColor(THEME['ACCENT_SOLID']));gradient.setColorAt(1,QColor('#EBC367'))
    painter.setBrush(gradient);path=QPainterPath();path.moveTo(64,20);path.lineTo(78,50);path.lineTo(108,64);path.lineTo(78,78);path.lineTo(64,108);path.lineTo(50,78);path.lineTo(20,64);path.lineTo(50,50);path.closeSubpath();painter.drawPath(path)
    painter.setBrush(QColor(THEME['BG_CARD']));painter.drawEllipse(56,56,16,16);painter.end()
    return QIcon(pixmap)


def main():
    configure_taskbar_identity()
    application=QApplication(sys.argv);application.setApplicationName('Anllm');application.setOrganizationName('Anllm')
    application.setApplicationVersion(APP_VERSION)
    application.setQuitOnLastWindowClosed(False)
    application.setStyle('Fusion');application.setStyleSheet(STYLE);application.setWindowIcon(app_icon())
    palette=QPalette();palette.setColor(QPalette.Window,QColor(THEME['BG_DEEP']));palette.setColor(QPalette.WindowText,QColor(THEME['TEXT']));palette.setColor(QPalette.Base,QColor(THEME['BG_CARD']));palette.setColor(QPalette.Text,QColor(THEME['TEXT']));application.setPalette(palette)
    # One native window. A second launch activates the running instance.
    import hashlib
    channel='Anllm-Desktop-'+hashlib.sha256((str(core.ROOT)+str(os.getlogin())).encode()).hexdigest()[:16]
    probe=QLocalSocket();probe.connectToServer(channel)
    if probe.waitForConnected(250): probe.write(b'activate');probe.waitForBytesWritten(500);return 0
    server=QLocalServer();QLocalServer.removeServer(channel);server.listen(channel)
    core.migrate_sessions();window=MainWindow()
    from desktop_hotkey import StopShortcut
    window.global_stop=StopShortcut(application,window.stop_all)
    if not window.global_stop.registered:
        window.desktop_note.setText('全局停止快捷键未能注册；可用停止按钮或托盘“停止所有任务”。')
    available=application.primaryScreen().availableGeometry()
    window.resize(min(1400,available.width()-50),min(870,available.height()-70))
    def activate():
        socket=server.nextPendingConnection()
        if socket: socket.disconnectFromServer();socket.deleteLater()
        window.present_window()
    server.newConnection.connect(activate);window.show()
    QTimer.singleShot(150,window.present_window)
    return application.exec()


if __name__=='__main__':
    try:
        if '--verify-package' in sys.argv:
            from diagnostics import verify_package
            verify_package();sys.exit(0)
        sys.exit(main())
    except Exception:
        (core.ROOT/'logs'/'desktop-error.log').write_text(core.scrub(traceback.format_exc()),encoding='utf-8')
        raise

