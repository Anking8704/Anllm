"""Saved connections, provider catalogs, permissions and local wallpaper."""
from PySide6.QtCore import Qt,QThread,Signal
from PySide6.QtGui import QColor,QPainter,QPixmap
from PySide6.QtWidgets import (QCheckBox,QDialog,QFileDialog,QFrame,QGridLayout,QHBoxLayout,
    QLabel,QLineEdit,QMessageBox,QPushButton,QScrollArea,QSlider,QSpinBox,QTabWidget,QVBoxLayout,QWidget)
import core
from appearance import import_wallpaper,wallpaper_path
from app_version import APP_VERSION
from anchored_combo import AnchoredComboBox as QComboBox
from window_chrome import ThemedMessageBox as QMessageBox
from window_chrome import ThemedFileDialog as QFileDialog

PRESETS=[('自定义 / 中转 API','','auto'),
    ('GPT','https://api.openai.com/v1','auto'),('Grok','https://api.x.ai/v1','chat'),
    ('Claude','https://api.anthropic.com/v1','anthropic'),
    ('Gemini','https://generativelanguage.googleapis.com/v1beta/openai','chat'),
    ('GLM','https://open.bigmodel.cn/api/paas/v4','chat'),
    ('DeepSeek','https://api.deepseek.com/v1','chat'),('Kimi','https://api.moonshot.cn/v1','chat')]

def label(text,name=None,wrap=False):
    widget=QLabel(text);widget.setWordWrap(wrap)
    if name:widget.setObjectName(name)
    return widget

def form_label(text,buddy=None):
    """Fixed-width form label so every input in a tab starts on the same column."""
    widget=QLabel(text);widget.setObjectName('fieldLabel');widget.setMinimumWidth(92)
    if buddy is not None:widget.setBuddy(buddy);buddy.setAccessibleName(text)
    return widget

def section(layout,title,note=None):
    layout.addWidget(label(title,'role'))
    if note:layout.addWidget(label(note,'muted',True))

def button(text,callback,name=None):
    widget=QPushButton(text);widget.clicked.connect(callback)
    if name:widget.setObjectName(name)
    return widget

class Worker(QThread):
    result=Signal(object);failed=Signal(str)
    def __init__(self,function):super().__init__();self.function=function
    def run(self):
        try:self.result.emit(self.function())
        except Exception as error:self.failed.emit(core.scrub(error))

class SettingsDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('Anllm '+APP_VERSION+' · 设置');self.resize(760,800);self.setMinimumSize(640,560)
        self.workers=[];self.loading=True;self.dirty=False;self.profile_id=None;self.models=[];self.catalog_connection=None
        prefs=core.preferences();self.wallpaper_value=prefs['wallpaper']
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        head=QWidget();head_layout=QVBoxLayout(head);head_layout.setContentsMargins(30,24,30,14);head_layout.setSpacing(5)
        head_layout.addWidget(label('设置','dialogTitle'));head_layout.addWidget(label('管理 API 与模型、能力路由、执行权限和外观。每个对话会记住自己的 API 和模型。','muted',True))
        layout.addWidget(head)
        tabs=QTabWidget();tabs.setObjectName('settingsTabs');tabs.setDocumentMode(True);layout.addWidget(tabs,1)
        connection=QWidget();connect=QVBoxLayout(connection);connect.setContentsMargins(30,22,30,22);connect.setSpacing(14)
        connect.addWidget(label('已保存的 API','section'))
        saved_row=QHBoxLayout();saved_row.setSpacing(8);self.saved=QComboBox();self.saved.setObjectName('savedApiPicker');self.saved.setAccessibleName('已保存的 API');saved_row.addWidget(self.saved,1)
        self.new_button=button('＋  新增 API',self.new_profile);saved_row.addWidget(self.new_button);connect.addLayout(saved_row)
        self.preset=QComboBox();self.preset.addItems([item[0] for item in PRESETS]);self.preset.setObjectName('apiPreset')
        self.name=QLineEdit();self.name.setPlaceholderText('例如 GPT 工作账号、Claude、公司中转')
        self.base=QLineEdit();self.key=QLineEdit();self.key.setEchoMode(QLineEdit.Password)
        self.protocol=QComboBox()
        for text,data in [('OpenAI 兼容 · 自动选择','auto'),('OpenAI 兼容 · Chat Completions','chat'),('OpenAI · Responses','responses'),('Claude · 原生 Messages','anthropic')]:self.protocol.addItem(text,data)
        self.base.setPlaceholderText('https://…/v1')
        connect.addSpacing(6);connect.addWidget(label('① 连接信息','section'))
        grid=QGridLayout();grid.setHorizontalSpacing(14);grid.setVerticalSpacing(10);grid.setColumnStretch(1,1)
        for row,(text,widget) in enumerate([('快速添加',self.preset),('配置名称',self.name),('API 地址',self.base),('API 密钥',self.key),('接口类型',self.protocol)]):
            grid.addWidget(form_label(text,widget),row,0);grid.addWidget(widget,row,1)
        connect.addLayout(grid)
        connect.addSpacing(6);connect.addWidget(label('② 选择模型','section'))
        self.catalog=button('连接并读取模型',self.read_models);self.catalog.setToolTip('使用上面的地址和密钥，向服务读取可用模型列表')
        self.search=QLineEdit();self.search.setPlaceholderText('筛选模型名称…');self.search.setAccessibleName('筛选模型')
        fetch_row=QGridLayout();fetch_row.setHorizontalSpacing(14);fetch_row.setVerticalSpacing(10);fetch_row.setColumnStretch(1,1)
        fetch_row.addWidget(form_label('模型列表',self.catalog),0,0);tools=QHBoxLayout();tools.setSpacing(8);tools.addWidget(self.catalog);tools.addWidget(self.search,1);fetch_row.addLayout(tools,0,1)
        connect.addLayout(fetch_row)
        self.chat=QComboBox();self.chat.setObjectName('chatModelPicker');self.image=QComboBox();self.image.setObjectName('imageModelPicker')
        self.vision=QComboBox();self.vision.setObjectName('visionModelPicker');self.vision_api=QComboBox();self.vision_api.setObjectName('visionApiPicker')
        for combo in (self.chat,self.image,self.vision):combo.setEditable(False);combo.setMaxVisibleItems(12)
        self.image_api=QComboBox();self.image_api.setObjectName('imageApiPicker')
        self.size=QComboBox();self.size.addItems(['1024x1024','1536x1024','1024x1536'])
        models_grid=QGridLayout();models_grid.setHorizontalSpacing(14);models_grid.setVerticalSpacing(10);models_grid.setColumnStretch(1,1)
        models_grid.addWidget(form_label('聊天模型',self.chat),0,0);models_grid.addWidget(self.chat,0,1)
        self.count=label('','hint',True);models_grid.addWidget(self.count,1,1)
        connect.addLayout(models_grid)
        connect.addSpacing(6);connect.addWidget(label('③ 使用方式','section'))
        choices=QHBoxLayout();choices.setSpacing(24);self.default=QCheckBox('设为新对话的默认 API');self.use_current=QCheckBox('保存后用于当前对话');self.use_current.setChecked(True)
        choices.addWidget(self.default);choices.addWidget(self.use_current);choices.addStretch();connect.addLayout(choices)
        connect.addStretch()
        self.save_button=button('仅保存此 API',self.save);self.save_button.setToolTip('保存当前 API 配置，设置窗口保持打开')
        connection_scroll=QScrollArea();connection_scroll.setWidgetResizable(True);connection_scroll.setWidget(connection);tabs.addTab(connection_scroll,'API 与模型')
        routes=QWidget();route=QVBoxLayout(routes);route.setContentsMargins(30,22,30,22);route.setSpacing(14)
        route.addWidget(label('当前 API 负责聊天和 Agent 任务。遇到看图或生图时，会自动交给下面指定的服务。','muted',True))
        route.addSpacing(6);section(route,'看图与视觉分析')
        vision_grid=QGridLayout();vision_grid.setHorizontalSpacing(14);vision_grid.setVerticalSpacing(10);vision_grid.setColumnStretch(1,1)
        for row,(text,widget) in enumerate([('视觉 API',self.vision_api),('视觉模型',self.vision)]):vision_grid.addWidget(form_label(text,widget),row,0);vision_grid.addWidget(widget,row,1)
        route.addLayout(vision_grid)
        route.addWidget(label('例如主模型用 DeepSeek、视觉模型用 GPT 或 Gemini。附图会先交给视觉模型分析，主模型拿到文字结果后继续。','hint',True))
        route.addSpacing(10);section(route,'生图与图片编辑')
        image_grid=QGridLayout();image_grid.setHorizontalSpacing(14);image_grid.setVerticalSpacing(10);image_grid.setColumnStretch(1,1)
        for row,(text,widget) in enumerate([('生图 API',self.image_api),('生图模型',self.image),('图片尺寸',self.size)]):image_grid.addWidget(form_label(text,widget),row,0);image_grid.addWidget(widget,row,1)
        route.addLayout(image_grid)
        route.addWidget(label('模型都从已读取的列表中选择，请选服务实际支持看图或生图的模型。','hint',True));route.addStretch()
        routes_scroll=QScrollArea();routes_scroll.setWidgetResizable(True);routes_scroll.setWidget(routes);tabs.addTab(routes_scroll,'能力与路由')
        runtime=QWidget();run=QVBoxLayout(runtime);run.setContentsMargins(30,22,30,22);run.setSpacing(14)
        section(run,'执行权限','决定 Agent 能自动做哪些事。改动从下一条任务开始生效。');self.permission=QComboBox()
        for key,text in core.PERMISSION_LABELS.items():self.permission.addItem(text,key)
        self.permission.setCurrentIndex(self.permission.findData(prefs['permission_mode']))
        permission_grid=QGridLayout();permission_grid.setHorizontalSpacing(14);permission_grid.setColumnStretch(1,1)
        permission_grid.addWidget(form_label('权限档位',self.permission),0,0);permission_grid.addWidget(self.permission,0,1);run.addLayout(permission_grid)
        note_card=QFrame();note_card.setObjectName('card');note_layout=QVBoxLayout(note_card);note_layout.setContentsMargins(16,14,16,14)
        self.permission_note=label('','muted',True);note_layout.addWidget(self.permission_note);run.addWidget(note_card)
        self.permission.currentIndexChanged.connect(self.update_permission);self.update_permission()
        run.addSpacing(10);section(run,'任务与协作')
        self.turns=QSpinBox();self.turns.setRange(4,100);self.turns.setValue(prefs['max_turns'])
        self.parallel=QSpinBox();self.parallel.setRange(1,4);self.parallel.setValue(prefs['parallel_agents'])
        execution=QGridLayout();execution.setHorizontalSpacing(14);execution.setVerticalSpacing(10);execution.setColumnStretch(2,1)
        execution.addWidget(form_label('最多轮次',self.turns),0,0);execution.addWidget(self.turns,0,1);execution.addWidget(label('每条任务最多与模型往返的次数','hint'),0,2)
        execution.addWidget(form_label('并行助手',self.parallel),1,0);execution.addWidget(self.parallel,1,1);execution.addWidget(label('同时工作的协作助手数量（1–4）','hint'),1,2)
        for spin in (self.turns,self.parallel):spin.setFixedWidth(96)
        run.addLayout(execution)
        run.addWidget(label('协作助手沿用当前对话的 API 和模型，各自计入服务用量。缺少关键信息时，模型会提问并等待你的回答。','hint',True));run.addStretch();tabs.addTab(runtime,'运行与权限')
        appearance=QWidget();view=QVBoxLayout(appearance);view.setContentsMargins(30,22,30,22);view.setSpacing(14)
        section(view,'对话区壁纸','选择本地图片作为中央对话区的背景。图片会复制到 Anllm 数据目录，不会上传。')
        self.preview=QLabel();self.preview.setObjectName('wallpaperPreview');self.preview.setFixedHeight(220);self.preview.setAlignment(Qt.AlignCenter);view.addWidget(self.preview)
        self.wallpaper_note=label('','hint',True);view.addWidget(self.wallpaper_note)
        wallpaper_actions=QHBoxLayout();wallpaper_actions.setSpacing(8);wallpaper_actions.addWidget(button('选择本地壁纸…',self.choose_wallpaper));wallpaper_actions.addWidget(button('恢复默认背景',self.reset_wallpaper,'ghost'));wallpaper_actions.addStretch();view.addLayout(wallpaper_actions)
        view.addSpacing(8)
        self.shade=QSlider(Qt.Horizontal);self.shade.setRange(30,95);self.shade.setValue(prefs['wallpaper_shade']);self.shade.valueChanged.connect(self.preview_wallpaper);self.shade.setAccessibleName('遮罩深度')
        self.shade_label=label('','muted');view.addWidget(self.shade_label);view.addWidget(self.shade)
        view.addWidget(label('遮罩越深，文字越清晰。输入框和按钮始终保留不透明底色。','hint',True));view.addStretch();tabs.addTab(appearance,'外观与壁纸')
        footer=QFrame();footer.setObjectName('dialogFooter');foot=QVBoxLayout(footer);foot.setContentsMargins(30,12,30,16);foot.setSpacing(10)
        self.status=label('','status',True);foot.addWidget(self.status)
        actions=QHBoxLayout();actions.setSpacing(8);actions.addWidget(label('配置、密钥和壁纸只保存在本机','hint'));actions.addStretch()
        actions.addWidget(button('取消',self.reject,'ghost'));actions.addWidget(self.save_button)
        self.done_button=button('保存并完成',self.finish,'primary');self.done_button.setDefault(True);actions.addWidget(self.done_button);foot.addLayout(actions);layout.addWidget(footer)
        tabs.currentChanged.connect(lambda index:self.save_button.setVisible(index in (0,1)))
        self.connection_widgets=(self.saved,self.new_button,self.preset,self.name,self.base,self.key,self.protocol,self.catalog,self.search,self.chat,self.image,self.image_api,self.vision,self.vision_api,self.size,self.save_button,self.default,self.use_current,self.done_button)
        self.saved.currentIndexChanged.connect(self.select_saved);self.preset.activated.connect(self.apply_preset)
        for widget in (self.name,self.base,self.key):widget.textChanged.connect(self.mark_dirty)
        for widget in (self.base,self.key):widget.textChanged.connect(self.connection_changed)
        self.protocol.currentIndexChanged.connect(self.connection_changed)
        for widget in (self.chat,self.image,self.size):widget.currentIndexChanged.connect(self.mark_dirty)
        self.chat.currentTextChanged.connect(self.remember_chat);self.image.currentTextChanged.connect(self.remember_image);self.vision.currentIndexChanged.connect(self.remember_vision)
        self.vision_api.currentIndexChanged.connect(self.vision_api_changed)
        self.image_api.currentIndexChanged.connect(self.image_api_changed);self.default.toggled.connect(self.mark_dirty);self.search.textChanged.connect(self.filter_models)
        self.refresh_saved();session=getattr(parent,'current',None);self.load_profile(session.get('api_profile_id') if session else None);self.preview_wallpaper()

    def update_permission(self):
        descriptions={'readonly':'读取项目、分析资料、浏览页面、查看与切换桌面窗口。不能改文件、运行命令、输入、点击或拖动。',
            'standard':'简单检查、搜索、窗口切换与滚动自动执行。首次查看目标桌面窗口会说明截图用途，同一任务不重复确认；其他命令和桌面、网页操作说明目的与影响后确认。',
            'full':'自动修改项目文件、执行命令、操作网页与桌面软件，无需逐项确认。操作使用你的 Windows 用户权限；Ctrl+Alt+F10 可停止任务。'}
        self.permission_note.setText(descriptions[self.permission.currentData()]+'\n文件工具始终限制在项目目录，凭据路径始终受保护。')

    def mark_dirty(self,*_):
        if not self.loading:self.dirty=True

    def remember_chat(self,text):
        if not self.loading and text in self.models:self.chat_selected=text

    def remember_image(self,text):
        if self.loading:return
        if self.image_api.currentData():self.image_override=text;self.mark_dirty()
        elif text in self.models:self.image_selected=text

    def remember_vision(self):
        if not self.loading:self.vision_selected=self.vision.currentData() or '';self.mark_dirty()

    def refresh_saved(self):
        self.saved.blockSignals(True);self.saved.clear()
        for profile in core.shared.api_profiles():self.saved.addItem(profile['name']+(' · 默认' if profile['is_default'] else ''),profile['id'])
        self.saved.blockSignals(False)

    def load_profile(self,identifier=None):
        config=core.shared.public_settings(identifier);self.loading=True;self.profile_id=config['id']
        self.saved.blockSignals(True);self.saved.setCurrentIndex(self.saved.findData(self.profile_id));self.saved.blockSignals(False)
        self.name.setText(config['name']);self.base.setText(config['base_url']);self.key.clear();self.key.setPlaceholderText('留空保留此配置的密钥 · '+config['key_hint'])
        self.protocol.setCurrentIndex(self.protocol.findData(config['chat_api']));self.size.setCurrentText(config['size']);self.preset.setCurrentIndex(0)
        self.models=core.shared.cached_models(self.profile_id);self.catalog_connection=(config['base_url'],'',config['chat_api']) if self.models else None
        self.chat_selected=config['chat_model'];self.image_selected=config['image_model'];self.image_override=config.get('image_model_override','');self.vision_selected=config.get('vision_model','')
        self.search.clear();self.populate_image_apis(config.get('image_api_profile_id',''));self.populate_vision_apis(config.get('vision_api_profile_id',''))
        self.default.setChecked(next(p['is_default'] for p in core.shared.api_profiles() if p['id']==self.profile_id));self.populate_models();self.loading=False;self.dirty=False

    def discard_allowed(self):
        return not self.dirty or QMessageBox.question(self,'尚未保存','切换会放弃当前未保存的 API 修改。继续？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes

    def select_saved(self):
        if self.loading:return
        identifier=self.saved.currentData()
        if identifier==self.profile_id:return
        if not self.discard_allowed():
            self.saved.blockSignals(True);self.saved.setCurrentIndex(self.saved.findData(self.profile_id));self.saved.blockSignals(False);return
        self.load_profile(identifier);self.status.setText('正在编辑 '+self.name.text()+'。其他对话不会跟着切换。')

    def new_profile(self,checked=False,preset=None):
        if not self.discard_allowed():return
        title,base,protocol=preset or PRESETS[0];self.loading=True;self.profile_id=''
        self.saved.blockSignals(True);self.saved.setCurrentIndex(-1);self.saved.blockSignals(False)
        existing={p['name'] for p in core.shared.api_profiles()};name=title if base else '新 API';suffix=2
        while name in existing:name=f'{title} {suffix}';suffix+=1
        self.name.setText(name);self.base.setText(base);self.key.clear();self.key.setPlaceholderText('填写此服务的 API 密钥')
        self.protocol.setCurrentIndex(self.protocol.findData(protocol));self.preset.setCurrentIndex(PRESETS.index(preset) if preset else 0)
        self.models=[];self.catalog_connection=None;self.chat_selected='';self.image_selected='';self.image_override='';self.vision_selected='';self.search.clear();self.default.setChecked(False)
        image_source=next((p['id'] for p in core.shared.api_profiles() if p['chat_api']!='anthropic' and p.get('image_model') in core.shared.cached_models(p['id']) and 'image' in p['image_model'].casefold()),'')
        self.populate_image_apis(image_source);self.populate_vision_apis('');self.populate_models();self.loading=False;self.dirty=True
        self.status.setText('填写密钥后读取模型。也可以先保存连接，稍后再读取。')

    def apply_preset(self,index):self.new_profile(preset=PRESETS[index])

    def populate_image_apis(self,selected):
        self.image_api.blockSignals(True);self.image_api.clear();self.image_api.addItem('当前 API','')
        for profile in core.shared.api_profiles():
            if profile['id']!=self.profile_id and profile['chat_api']!='anthropic':self.image_api.addItem(profile['name'],profile['id'])
        self.image_api.setCurrentIndex(max(0,self.image_api.findData(selected)));self.image_api.blockSignals(False)

    def populate_vision_apis(self,selected):
        self.vision_api.blockSignals(True);self.vision_api.clear();self.vision_api.addItem('当前 API','')
        for profile in core.shared.api_profiles():
            if profile['id']!=self.profile_id:self.vision_api.addItem(profile['name'],profile['id'])
        self.vision_api.setCurrentIndex(max(0,self.vision_api.findData(selected)));self.vision_api.blockSignals(False)

    def vision_api_changed(self):
        if not self.loading:self.vision_selected='';self.mark_dirty()
        self.populate_models()

    def connection_changed(self,*_):
        if self.loading:return
        self.catalog_connection=None;self.models=[];self.search.clear();self.populate_models();self.mark_dirty();self.status.setText('连接或接口已更改，请重新读取该 API 的模型。')

    def populate_models(self):
        needle=self.search.text().strip().casefold();models=[m for m in self.models if needle in m.casefold()]
        self.chat.blockSignals(True);self.chat.clear();self.chat.addItems(sorted(models,key=lambda m:('image' in m.casefold(),m)))
        if self.chat_selected in models:self.chat.setCurrentText(self.chat_selected)
        if not models:self.chat.addItem('没有匹配模型' if self.models else '请先读取模型列表')
        self.chat.setEnabled(bool(models));self.chat.blockSignals(False)
        source=self.image_api.currentData();external=bool(source);image_models=core.shared.cached_models(source) if external else self.models
        native=self.protocol.currentData()=='anthropic' and not external;current=(self.image_override or core.shared.public_settings(source)['image_model']) if external else self.image_selected
        self.image.blockSignals(True);self.image.clear()
        if not native:self.image.addItems(sorted(image_models,key=lambda m:('image' not in m.casefold(),m)))
        if current in image_models and not native:self.image.setCurrentText(current)
        if native:self.image.addItem('Claude 原生接口不提供生图')
        elif not image_models:self.image.addItem('先为图片 API 读取模型')
        self.image.setEnabled(bool(image_models) and not native);self.image.blockSignals(False)
        vision_source=self.vision_api.currentData();vision_models=core.shared.cached_models(vision_source) if vision_source else self.models
        self.vision.blockSignals(True);self.vision.clear()
        if not vision_source:self.vision.addItem('跟随聊天模型（直接看图）','')
        for model in sorted(vision_models,key=lambda m:('image' in m.casefold(),m)):self.vision.addItem(model,model)
        selected=self.vision_selected or (core.shared.public_settings(vision_source)['chat_model'] if vision_source else '')
        index=self.vision.findData(selected);self.vision.setCurrentIndex(index if index>=0 else (0 if self.vision.count() else -1))
        if not self.vision.count():self.vision.addItem('请先为视觉 API 读取模型',None)
        self.vision.setEnabled(bool(vision_models) or not vision_source);self.vision.blockSignals(False)
        note=f'当前 API 已读取 {len(self.models)} 个模型。' if self.models else '可以先保存 API；读取模型后才能发起对话。'
        if external:note+=' 看图和生图服务在“能力与路由”中选择。'
        self.count.setText(note)

    def image_api_changed(self):
        if not self.loading:self.image_override='';self.mark_dirty()
        self.populate_models()

    def filter_models(self):
        if self.loading:return
        if self.chat.currentText() in self.models:self.chat_selected=self.chat.currentText()
        self.populate_models()

    def run_function(self,function,callback,finished=None):
        worker=Worker(function);self.workers.append(worker)
        for widget in self.connection_widgets:widget.setEnabled(False)
        success=[]
        def received(result):callback(result);success.append(True)
        worker.result.connect(received);worker.failed.connect(self.status.setText)
        def done():
            self.workers.remove(worker);worker.deleteLater()
            for widget in self.connection_widgets:widget.setEnabled(True)
            self.populate_models()
            if success and finished:finished()
        worker.finished.connect(done);worker.start()

    def read_models(self):
        base,key,protocol=self.base.text().strip().rstrip('/'),self.key.text().strip(),self.protocol.currentData();identifier=self.profile_id;self.status.setText('正在读取此 API 的模型…')
        def loaded(models):
            self.models=models;self.catalog_connection=(base,key,protocol);self.dirty=True;self.populate_models();self.status.setText('读取成功，选择模型后保存当前 API。')
        self.run_function(lambda:core.shared.read_models(base,key,identifier,protocol),loaded)

    def save(self,finish_after=False):
        if self.models and self.chat.currentText() not in self.models:self.status.setText('请选择当前 API 返回的聊天模型。');return
        native=self.protocol.currentData()=='anthropic';external=bool(self.image_api.currentData())
        value={'name':self.name.text(),'base_url':self.base.text(),'api_key':self.key.text(),'chat_model':self.chat.currentText() if self.models else '',
            'image_model':self.image_selected if external else (self.image.currentText() if self.models and not native else ''),
            'chat_api':self.protocol.currentData(),'size':self.size.currentText(),'image_api_profile_id':self.image_api.currentData() or '',
            'image_model_override':self.image.currentText() if external and self.image.isEnabled() else '',
            'vision_api_profile_id':self.vision_api.currentData() or '', 'vision_model':self.vision.currentData() or '', 'make_default':self.default.isChecked()}
        from api_profiles import ModelCatalog
        models=ModelCatalog(self.models,getattr(self.models,'capabilities',core.shared.public_settings(self.profile_id).get('model_capabilities',{}) if self.profile_id else {}));identifier=self.profile_id;apply=self.use_current.isChecked()
        def commit():
            result=core.shared.save_settings(value,identifier)
            if models:core.shared.cache_models(models,result['id'])
            return result
        def complete(result):
            self.profile_id=result['id'];self.refresh_saved();self.load_profile(self.profile_id);parent=self.parent()
            if apply and getattr(parent,'current',None) and not getattr(parent,'worker',None):
                parent.current.update(api_profile_id=result['id'],chat_model=result['chat_model']);core.save_session(parent.current);parent.update_models()
            self.status.setText('已保存 '+result['name']+'。可继续新增其他 API，或保存并完成。')
        self.run_function(commit,complete,self.finish if finish_after else None)

    def choose_wallpaper(self):
        filename,_=QFileDialog.getOpenFileName(self,'选择本地壁纸','','图片 (*.png *.jpg *.jpeg *.webp *.bmp)')
        if not filename:return
        try:self.wallpaper_value=import_wallpaper(filename);self.preview_wallpaper()
        except Exception as error:self.status.setText(str(error))

    def reset_wallpaper(self):self.wallpaper_value='';self.preview_wallpaper()

    def preview_wallpaper(self):
        path=wallpaper_path(self.wallpaper_value);shade=self.shade.value();self.shade_label.setText(f'背景遮罩深度：{shade}%')
        canvas=QPixmap(610,235);canvas.fill(QColor('#13151c'));painter=QPainter(canvas)
        if path:
            picture=QPixmap(str(path)).scaled(canvas.size(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation)
            painter.drawPixmap((610-picture.width())//2,(235-picture.height())//2,picture);painter.fillRect(canvas.rect(),QColor(10,14,23,round(255*shade/100)))
        painter.setPen(QColor('#eef3ff'));painter.drawText(canvas.rect(),Qt.AlignCenter,'Anllm  ·  想法，在这里成形。');painter.end()
        self.preview.setPixmap(canvas);self.wallpaper_note.setText('当前：自定义本地壁纸' if path else '当前：默认纯色背景')

    def finish(self):
        if self.workers:return
        if self.dirty:self.save(True);return
        try:
            core.save_preferences({**core.preferences(),'max_turns':self.turns.value(),'parallel_agents':self.parallel.value(),
                'permission_mode':self.permission.currentData(),'wallpaper':self.wallpaper_value,'wallpaper_shade':self.shade.value()});self.accept()
        except Exception as error:self.status.setText(core.scrub(error))

    def reject(self):
        if self.workers:self.status.setText('连接处理中，请稍候。');return
        super().reject()

    def closeEvent(self,event):
        if self.workers:event.ignore()
        else:event.accept()
