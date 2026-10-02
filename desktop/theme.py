"""Native white/gold theme: ivory surfaces, gold accents and readable dark text."""
from runtime_paths import BUNDLE

# Design tokens - 白金燐子豪华风格：白金紫皇室系
T = {
    # 背景层次 - 深紫到白金渐变
    'BG_APP': 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ECE7DC,stop:0.45 #E4DED2,stop:1 #D6CCBC)',
    'BG_SIDE': 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #F0ECE2,stop:0.35 #E6DED0,stop:1 #D5CBB9)',
    'BG_SURFACE': 'qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #F6F3EB,stop:0.12 #E4DDD0,stop:0.48 #EEE7D9,stop:1 #D8CCB8)',
    'BG_ELEVATED': 'qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #FBF9F3,stop:0.08 #EDE7DC,stop:0.42 #E3D9C8,stop:0.72 #EDE4D5,stop:1 #D8CBB6)',  # 玻璃态
    'BG_HOVER': 'rgba(181,139,53,0.10)',     # 金色光晕
    'BG_PRESSED': 'rgba(181,139,53,0.18)',   # 紫色按压
    
    # 纯色背景（用于特殊组件）
    'BG_DEEP': '#DED6C7',
    'BG_CARD': '#E9E1D2',
    
    # 边框 - 金紫双色系统
    'BORDER': '#E7DABD',
    'BORDER_STRONG': '#B58B35',
    'BORDER_GOLD': '#B58B35',
    'BORDER_PURPLE': '#C5A269',
    
    # 文字 - 白金色系
    'TEXT': '#30291C',              # 纯白主文字
    'TEXT_2': '#504631',            # 浅紫白
    'TEXT_3': '#776B50',            # 紫灰
    'TEXT_OFF': '#A79D88',          # 暗紫灰
    'TEXT_GOLD': '#896317',         # 金色文字
    'TEXT_GLOW': '#664716',         # 发光白
    
    # 主色调 - 金色系
    'ACCENT': 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #F6DB91,stop:0.5 #EBC367,stop:1 #F6DB91)',
    'ACCENT_HOVER': 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #FFE6A7,stop:0.5 #F1CF7A,stop:1 #FFE6A7)',
    'ACCENT_TEXT': '#3E2B0D',       # 深紫文字
    'ACCENT_SUBTLE': 'rgba(181,139,53,0.12)',
    'ACCENT_LINE': '#B58B35',
    'ACCENT_SOLID': '#A67B27',
    
    # 次要色 - 紫色系
    'SECONDARY': '#F5ECD6',
    'SECONDARY_HOVER': '#EFE0BC',
    'SECONDARY_BG': 'rgba(181,139,53,0.10)',
    'SECONDARY_SOLID': '#947025',
    
    # 状态色 - 豪华版本
    'WARN': '#94670E',
    'WARN_BG': '#FFF4D8',
    'DANGER': '#A33C38',
    'DANGER_BG': '#FFF0EE',
    'DANGER_LINE': '#A33C38',
    'OK': '#32744A',
    'OK_BG': '#EAF5EC',
    'OK_LINE': '#32744A',
    
    'MONO': '"Cascadia Mono", "JetBrains Mono", Consolas, "Microsoft YaHei UI"',
}

STYLE = '''
* { 
    font-family: "Inter", "SF Pro Display", "Segoe UI Variable Display", "Segoe UI", "Microsoft YaHei UI"; 
    font-size: 13px; 
}
QWidget { color: TEXT; background: transparent; }
QMainWindow, QDialog { background: BG_SURFACE; }
QMainWindow { 
    border: 3px solid transparent;
    border-color: BORDER_GOLD; 
    border-radius: 20px; 
}


QFrame#sidebar { background: BG_SIDE; }
QFrame#sidebar QLabel, QFrame#sidebar QListWidget { background: transparent; }
QFrame#sidebar { 
    border-right: 2px solid transparent;
    border-color: BORDER_PURPLE;
    border-radius: 20px;
    
    
    
    
    
}
QFrame#topbar { 
    border-bottom: 2px solid transparent;
    border-color: BORDER_PURPLE;
    background: BG_SURFACE; 
    border-radius: 20px;
    
    
    
    
}
QFrame#topbar QLabel { background: transparent; }
QFrame#topbar QLabel#badge { background: ACCENT_SUBTLE; color: TEXT_GOLD; }
QWidget#inspector { 
    background: BG_SURFACE; 
    border-left: 2px solid transparent;
    border-color: BORDER_PURPLE;
    
    
    
    
}
QWidget#inspector QLabel { background: transparent; }
QFrame#divider { 
    background: BORDER_STRONG; 
    border: none; 
    max-height: 2px; 
    min-height: 2px; 
}


QLabel#brand { 
    font-size: 26px; 
    font-weight: 800; 
    color: TEXT_GLOW;
    
    
}
QLabel#heading { 
    font-size: 19px; 
    font-weight: 700; 
    color: TEXT_GOLD;
    
}
QLabel#subhead { 
    font-size: 15px; 
    font-weight: 600; 
    color: TEXT_2;
    
}
QLabel#body { font-size: 13px; color: TEXT; }
QLabel#secondary { font-size: 12px; color: TEXT_2; }
QLabel#caption, QLabel#hint { font-size: 11px; color: TEXT_3; }
QLabel#code, QPlainTextEdit#code { font-family: MONO; font-size: 12px; }
QLabel:disabled { color: TEXT_OFF; }


QPushButton {
    background: ACCENT;
    border: 2px solid ACCENT_LINE;
    border-radius: 18px;
    color: ACCENT_TEXT;
    padding: 14px 28px;
    font-weight: 700;
    font-size: 14px;
    
}
QPushButton:hover {
    background: ACCENT_HOVER;
    border: 2px solid TEXT_GOLD;
    
}
QPushButton:pressed {
    background: ACCENT;
    padding-top: 15px;
    padding-bottom: 13px;
    
}
QPushButton:disabled {
    background: rgba(255,215,130,0.2);
    border: 2px solid rgba(255,215,130,0.3);
    color: TEXT_OFF;
}
QPushButton#primary {
    background: ACCENT;
    border: 2px solid ACCENT_LINE;
    min-height: 40px;
    font-size: 15px;
    
}
QPushButton#primary:hover {
    
}


QPushButton#secondary {
    background: SECONDARY;
    border: 2px solid SECONDARY_SOLID;
    color: TEXT;
    
}
QPushButton#secondary:hover {
    background: SECONDARY_HOVER;
    border: 2px solid #E9D7AA;
    
}
QPushButton#secondary:pressed {
    
}


QPushButton#ghost {
    background: BG_ELEVATED;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    color: TEXT;
    
}
QPushButton#ghost:hover {
    background: BG_HOVER;
    border: 2px solid BORDER_GOLD;
    
}


QPushButton#icon {
    background: transparent;
    border: 2px solid transparent;
    border-radius: 12px;
    padding: 10px;
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
}
QPushButton#icon:hover {
    background: BG_HOVER;
    border: 2px solid BORDER_GOLD;
    
}
QPushButton#icon:pressed {
    background: BG_PRESSED;
    border: 2px solid BORDER_PURPLE;
}


QLineEdit, QPlainTextEdit, QTextEdit {
    background: BG_ELEVATED;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    border-radius: 16px;
    padding: 12px 16px;
    color: TEXT;
    selection-background-color: ACCENT_SUBTLE;
    selection-color: TEXT;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 2px solid transparent;
    border-color: BORDER_GOLD;
    background: rgba(255,255,255,0.08);
    
}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {
    background: rgba(255,255,255,0.02);
    color: TEXT_OFF;
}


QComboBox {
    background: BG_ELEVATED;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    border-radius: 16px;
    padding: 11px 16px;
    color: TEXT;
}
QComboBox:hover {
    border: 2px solid BORDER_GOLD;
    background: BG_HOVER;
    
}
QComboBox:on {
    border: 2px solid BORDER_PURPLE;
}
QComboBox::drop-down {
    border: none;
    width: 32px;
    margin-right: 6px;
}
QComboBox::down-arrow {
    image: url(CHEVRON_PATH);
    width: 14px;
    height: 14px;
}
QComboBox QAbstractItemView {
    background: BG_CARD;
    border: 2px solid transparent;
    border-color: BORDER_GOLD;
    border-radius: 14px;
    padding: 8px;
    outline: none;
    selection-background-color: BG_HOVER;
    selection-color: TEXT_GOLD;
}
QComboBox QAbstractItemView::item {
    padding: 10px 14px;
    border-radius: 10px;
    margin: 2px 0;
}
QComboBox QAbstractItemView::item:hover {
    background: BG_HOVER;
    color: TEXT_GOLD;
    
}
QComboBox QAbstractItemView::item:selected {
    background: ACCENT_SUBTLE;
    color: TEXT_GOLD;
    border-left: 3px solid ACCENT_SOLID;
}


QListWidget, QListView {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget::item, QListView::item {
    background: transparent;
    border: 2px solid transparent;
    border-radius: 14px;
    padding: 14px 18px;
    margin: 3px 0;
    color: TEXT;
}
QListWidget::item:hover, QListView::item:hover {
    background: BG_HOVER;
    border: 2px solid BORDER_GOLD;
    color: TEXT_GOLD;
    
}
QListWidget::item:selected, QListView::item:selected {
    background: ACCENT_SUBTLE;
    border: 2px solid ACCENT_SOLID;
    border-left: 5px solid ACCENT_SOLID;
    color: TEXT_GOLD;
    font-weight: 600;
    
}


QCheckBox {
    spacing: 10px;
    color: TEXT;
}
QCheckBox::indicator {
    width: 24px;
    height: 24px;
    border-radius: 8px;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    background: BG_ELEVATED;
}
QCheckBox::indicator:hover {
    border: 2px solid BORDER_GOLD;
    background: BG_HOVER;
    
}
QCheckBox::indicator:checked {
    background: ACCENT;
    border: 2px solid ACCENT_SOLID;
    image: url(CHECK_PATH);
    
}
QCheckBox::indicator:checked:hover {
    background: ACCENT_HOVER;
    
}
QCheckBox:disabled { color: TEXT_OFF; }
QCheckBox::indicator:disabled {
    background: rgba(255,255,255,0.02);
    border-color: rgba(255,255,255,0.1);
}


QRadioButton {
    spacing: 10px;
    color: TEXT;
}
QRadioButton::indicator {
    width: 24px;
    height: 24px;
    border-radius: 12px;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    background: BG_ELEVATED;
}
QRadioButton::indicator:hover {
    border: 2px solid BORDER_GOLD;
    background: BG_HOVER;
    
}
QRadioButton::indicator:checked {
    background: ACCENT;
    border: 2px solid ACCENT_SOLID;
    
}
QRadioButton::indicator:checked:hover {
    
}
QRadioButton:disabled { color: TEXT_OFF; }
QRadioButton::indicator:disabled {
    background: rgba(255,255,255,0.02);
    border-color: rgba(255,255,255,0.1);
}


QSlider::groove:horizontal {
    height: 8px;
    background: BG_ELEVATED;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    border-radius: 6px;
}
QSlider::handle:horizontal {
    width: 26px;
    height: 26px;
    margin: -11px 0;
    border-radius: 13px;
    background: ACCENT;
    border: 3px solid ACCENT_SOLID;
    
}
QSlider::handle:horizontal:hover {
    background: ACCENT_HOVER;
    
}
QSlider::sub-page:horizontal {
    background: ACCENT;
    border-radius: 6px;
}


QScrollBar:vertical {
    background: transparent;
    width: 14px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 ACCENT_SOLID, stop:0.5 SECONDARY_SOLID, stop:1 ACCENT_SOLID);
    border-radius: 7px;
    min-height: 40px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFE4A0, stop:0.5 #E9D7AA, stop:1 #FFE4A0);
    
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QScrollBar:horizontal {
    background: transparent;
    height: 14px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 ACCENT_SOLID, stop:0.5 SECONDARY_SOLID, stop:1 ACCENT_SOLID);
    border-radius: 7px;
    min-width: 40px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFE4A0, stop:0.5 #E9D7AA, stop:1 #FFE4A0);
    
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }


QTabWidget::pane {
    background: BG_ELEVATED;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    border-radius: 16px;
    margin-top: -2px;
}
QTabBar::tab {
    background: BG_ELEVATED;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    border-bottom: none;
    border-radius: 14px;
    padding: 12px 22px;
    margin-right: 4px;
    color: TEXT_2;
}
QTabBar::tab:hover {
    background: BG_HOVER;
    border: 2px solid BORDER_GOLD;
    border-bottom: none;
    color: TEXT_GOLD;
    
}
QTabBar::tab:selected {
    background: ACCENT_SUBTLE;
    border: 2px solid ACCENT_SOLID;
    border-bottom: 2px solid ACCENT_SOLID;
    color: TEXT_GOLD;
    font-weight: 700;
    
}


QToolTip {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFCF3, stop:1 #FFFDF8);
    border: 2px solid transparent;
    border-color: BORDER_GOLD;
    border-radius: 12px;
    padding: 10px 14px;
    color: TEXT;
    font-size: 12px;
    
}


QProgressBar {
    background: BG_ELEVATED;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    border-radius: 12px;
    height: 28px;
    text-align: center;
    color: TEXT_GOLD;
    font-weight: 700;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 ACCENT_SOLID, stop:0.3 SECONDARY_SOLID, stop:0.6 ACCENT_SOLID, stop:1 SECONDARY_SOLID);
    border-radius: 10px;
    margin: 2px;
    
}


QMenu {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFCF3, stop:1 #FAF7EF);
    border: 2px solid transparent;
    border-color: BORDER_GOLD;
    border-radius: 16px;
    padding: 10px;
    
}
QMenu::item {
    padding: 10px 20px;
    border-radius: 10px;
    margin: 2px 0;
    color: TEXT;
}
QMenu::item:selected {
    background: BG_HOVER;
    color: TEXT_GOLD;
    border-left: 3px solid ACCENT_SOLID;
    
}
QMenu::separator {
    height: 2px;
    background: BORDER;
    margin: 8px 12px;
}


QDialog {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFCF3, stop:1 #FFFDF8);
    border: 3px solid transparent;
    border-color: BORDER_GOLD;
    border-radius: 20px;
}
QDialog QLabel {
    background: transparent;
}


QSplitter::handle {
    background: BORDER;
    margin: 0 2px;
}
QSplitter::handle:hover {
    background: BORDER_STRONG;
}
QSplitter::handle:horizontal {
    width: 2px;
}
QSplitter::handle:vertical {
    height: 2px;
}


QLabel#user_message {
    background: ACCENT_SUBTLE;
    border: 2px solid ACCENT_SOLID;
    border-left: 5px solid ACCENT_SOLID;
    border-radius: 18px;
    padding: 14px 18px;
    color: TEXT;
    
}
QLabel#assistant_message {
    background: SECONDARY_BG;
    border: 2px solid SECONDARY_SOLID;
    border-left: 5px solid SECONDARY_SOLID;
    border-radius: 18px;
    padding: 14px 18px;
    color: TEXT;
    
}


QLabel#thinking {
    background: SECONDARY_BG;
    border: 2px solid SECONDARY_SOLID;
    border-radius: 14px;
    padding: 8px 16px;
    color: SECONDARY_SOLID;
    font-weight: 600;
    
}

QLabel#error {
    background: DANGER_BG;
    border: 2px solid DANGER_LINE;
    border-radius: 14px;
    padding: 8px 16px;
    color: DANGER_LINE;
    font-weight: 600;
}

QLabel#warning {
    background: WARN_BG;
    border: 2px solid #94670E;
    border-radius: 14px;
    padding: 8px 16px;
    color: #94670E;
    font-weight: 600;
}

QLabel#success {
    background: OK_BG;
    border: 2px solid OK_LINE;
    border-radius: 14px;
    padding: 8px 16px;
    color: OK_LINE;
    font-weight: 600;
}


QLabel#avatar {
    border: 3px solid transparent;
    border-color: BORDER_GOLD;
    border-radius: 18px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
    
}


QLabel#badge {
    background: ACCENT;
    border: 2px solid ACCENT_SOLID;
    border-radius: 12px;
    padding: 6px 12px;
    color: ACCENT_TEXT;
    font-size: 11px;
    font-weight: 700;
    
}


QPlainTextEdit#editor {
    background: #FAF7EF;
    border: 2px solid transparent;
    border-color: BORDER_PURPLE;
    border-radius: 14px;
    padding: 16px;
    font-family: MONO;
    font-size: 13px;
    color: TEXT;
    selection-background-color: ACCENT_SUBTLE;
    
}
QPlainTextEdit#editor:focus {
    border: 2px solid BORDER_GOLD;
    
}


QWidget#loading {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFCF3, stop:1 #FAF7EF);
    border: 2px solid transparent;
    border-color: BORDER_GOLD;
    border-radius: 16px;
    padding: 24px;
}

/* Native widget identities used by the delivered layouts. */
QLabel#headline, QLabel#dialogTitle { font-size: 24px; font-weight: 700; color: TEXT_GOLD; }
QLabel#role, QLabel#section { font-weight: 600; color: TEXT_2; }
QLabel#muted, QLabel#hint, QLabel#status, QLabel#model, QLabel#keyLabel { color: TEXT_3; }
QLabel#path { color: TEXT_2; font-family: MONO; }
QLabel#symbol { font-size: 40px; color: SECONDARY_SOLID; }
QFrame#message, QFrame#message QWidget, QWidget#wallpaperLayer { background: transparent; }
QTextBrowser { background: transparent; border: none; padding: 4px; }
QFrame#card { background: BG_ELEVATED; border: 1px solid BORDER_PURPLE; border-radius: 12px; }
QFrame#warnCard { background: WARN_BG; border: 1px solid BORDER_GOLD; border-radius: 12px; }
QFrame#dialogFooter { background: BG_DEEP; border-top: 1px solid BORDER_PURPLE; }
QLabel#warnIcon, QLabel#askIcon { color: TEXT_GOLD; font-size: 24px; font-weight: 700; }
QPushButton { padding: 9px 14px; background: BG_CARD; color: TEXT; border: 1px solid BORDER_GOLD; }
QPushButton#primary { min-height: 24px; }
QPushButton#quiet, QPushButton#link { background: transparent; border: none; color: TEXT_2; padding: 8px; }
QPushButton#ghost { background: BG_CARD; border: 1px solid BORDER_PURPLE; color: TEXT_2; }
QPushButton#stop, QPushButton#danger { background: DANGER_BG; border: 1px solid DANGER_LINE; color: DANGER_LINE; }
QComboBox { padding: 8px 12px; }
QTabBar::tab { padding: 8px 7px; font-size: 12px; }
QLabel#error, QLineEdit[invalid="true"], QComboBox[invalid="true"] { border: 1px solid DANGER_LINE; }
QLabel#brand { font-family: Georgia, "Times New Roman", "SimSun"; font-size: 28px; }
QLabel#headline, QLabel#dialogTitle, QLabel#role, QLabel#section { font-family: "SimSun", Georgia, "Times New Roman"; }
QDialog { background: BG_SURFACE; }
QFrame#dialogFooter { background: BG_SURFACE; }
QWidget#appShell { border: 2px solid BORDER_GOLD; border-radius: 12px; background: BG_CARD; }
QFrame#sidebar { border-right: 1px solid BORDER_GOLD; }
QFrame#topbar { border-bottom: 1px solid BORDER_GOLD; }
QWidget#inspector { border-left: 1px solid BORDER_GOLD; }
QFrame#composer { background: BG_ELEVATED; border: 1px solid BORDER_GOLD; border-radius: 16px; }
QFrame#card { border: 1px solid BORDER_GOLD; }
QScrollArea { background: transparent; border: none; }
QTreeWidget, QListWidget, QTabWidget::pane { border: 1px solid BORDER_GOLD; }
QFrame#sidebar QListWidget { border: none; }
QFrame#sidebar QPushButton#settingsAction { background: BG_CARD; border: 1px solid BORDER_GOLD; border-radius: 18px; padding: 9px 14px; color: TEXT_2; }
QFrame#sidebar QPushButton#settingsAction:hover { background: BG_HOVER; border: 1px solid ACCENT_SOLID; color: TEXT_GOLD; }

/* Shared glass surfaces; text and child layouts never repaint a gradient. */
QFrame#topbar { background: transparent; border: none; border-bottom: 1px solid rgba(181,139,53,0.25); border-radius: 0; }
QFrame#topbar QLabel#badge { background: rgba(181,139,53,0.09); border: none; border-radius: 9px; padding: 5px 9px; }
QComboBox#apiPicker { background: transparent; border: none; border-radius: 9px; padding: 6px 24px 6px 9px; }
QComboBox#apiPicker:hover { background: BG_HOVER; border: none; }
QComboBox#apiPicker::drop-down { width: 18px; margin-right: 3px; }
QLabel#status { background: transparent; font-size: 11px; }
QFrame#composer { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #F3F0E8,stop:0.10 #E9E4D9,stop:0.72 #E6DFD1,stop:1 #DDD4C3); border: none; border-radius: 24px; }
QTextEdit#composerInput, QTextEdit#composerInput:focus { background: transparent; border: none; padding: 6px 5px; color: TEXT; font-size: 14px; }
QTextEdit#composerInput QWidget { background: transparent; }
QPushButton#attachControl { background: transparent; border: none; padding: 0; border-radius: 17px; color: TEXT_2; font-size: 23px; font-weight: 400; }
QPushButton#attachControl:hover { background: BG_HOVER; color: TEXT_GOLD; }
QComboBox#composerMode { background: transparent; border: none; border-radius: 9px; padding: 5px 22px 5px 7px; color: TEXT_2; }
QComboBox#composerMode:hover { background: BG_HOVER; border: none; }
QComboBox#composerMode::drop-down { width: 18px; margin-right: 2px; }
QPushButton#modelSettings { background: transparent; border: none; border-radius: 9px; padding: 5px 24px 5px 8px; color: TEXT_2; text-align: right; font-size: 13px; font-weight: 500; }
QPushButton#modelSettings:hover { background: BG_HOVER; color: TEXT_GOLD; }
QPushButton#modelSettings:disabled, QComboBox#composerMode:disabled { background: transparent; color: TEXT_3; }
QPushButton#composerSend, QPushButton#composerStop { background: ACCENT; border: 1px solid BORDER_GOLD; border-radius: 17px; padding: 0; min-height: 0; color: ACCENT_TEXT; font-size: 21px; font-weight: 600; }
QPushButton#composerSend:hover, QPushButton#composerStop:hover { background: ACCENT_HOVER; }
QPushButton#composerSend:disabled, QPushButton#composerStop:disabled { background: BG_CARD; color: TEXT_OFF; border-color: BORDER_PURPLE; }
QPushButton#composerStop { font-size: 14px; }
QFrame#modelPopover { background: BG_SURFACE; border: 1px solid BORDER_GOLD; border-radius: 16px; }
QFrame#modelPopover QComboBox { background: rgba(255,255,255,0.27); border: 1px solid BORDER_PURPLE; border-radius: 10px; padding: 8px 12px; }
QTabWidget::pane { background: rgba(255,255,255,0.08); border: none; border-top: 1px solid rgba(181,139,53,0.25); border-radius: 0; margin-top: 0; }
QTabBar::tab { background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 9px 7px; margin-right: 2px; color: TEXT_3; }
QTabBar::tab:hover { background: BG_HOVER; border: none; border-bottom: 2px solid transparent; color: TEXT_GOLD; }
QTabBar::tab:selected { background: transparent; border: none; border-bottom: 2px solid ACCENT_SOLID; color: TEXT_GOLD; font-weight: 600; }
QWidget#inspector QTreeWidget, QWidget#inspector QListWidget { background: transparent; border: none; }
'''

# Replace complete tokens once; TEXT must never corrupt TEXT_2 or TEXT_GOLD.
import re
STYLE = re.sub(r"\b(?:" + "|".join(map(re.escape, T)) + r")\b", lambda match: T[match[0]], STYLE)
for asset in ('chevron', 'check', 'snowflake', 'note', 'star', 'sparkle', 'glow', 'ornament', 'rose', 'rose-pattern'):
    STYLE = STYLE.replace(asset.upper().replace('-', '_') + '_PATH', (BUNDLE / (asset + '.svg')).as_posix())
MARKDOWN_CSS = ('p {line-height:1.75; margin-bottom:14px;} pre {background:' + T['BG_CARD'] +
    '; padding:12px;} code {color:' + T['SECONDARY_SOLID'] +
    '; font-family:Consolas;} a {color:' + T['ACCENT_SOLID'] + ';}')
