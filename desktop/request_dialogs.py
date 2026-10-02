"""Plain-language Qt dialogs; technical command details stay collapsed."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget)
from request_presenter import readable
from app_version import APP_VERSION
from anchored_combo import AnchoredComboBox as QComboBox


def text_label(text, name='role'):
    widget = QLabel(readable(text))
    widget.setObjectName(name)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return widget


def action_button(text, callback, name=None):
    widget = QPushButton(text)
    if name is True:
        name = 'primary'
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(callback)
    return widget


def footer_bar(left=(), right=()):
    """Bottom action bar: secondary/destructive actions left, decision buttons right."""
    frame = QFrame(); frame.setObjectName('dialogFooter')
    row = QHBoxLayout(frame); row.setContentsMargins(26, 16, 26, 16); row.setSpacing(10)
    for widget in left:
        row.addWidget(widget)
    row.addStretch()
    for widget in right:
        row.addWidget(widget)
    return frame


class ApprovalDialog(QDialog):
    def __init__(self, event, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Anllm ' + APP_VERSION + ' · 确认这一步')
        self.setMinimumWidth(560); self.resize(600, 10)
        request = event.get('request') or {}
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        body = QWidget(); layout = QVBoxLayout(body); layout.setContentsMargins(26, 24, 26, 22); layout.setSpacing(18)

        header = QHBoxLayout(); header.setSpacing(12)
        icon = QLabel('!'); icon.setObjectName('warnIcon'); header.addWidget(icon, 0, Qt.AlignTop)
        titles = QVBoxLayout(); titles.setSpacing(3)
        titles.addWidget(text_label('需要你确认', 'section'))
        self.summary = text_label(request.get('summary', event.get('title', '执行下一步')), 'dialogTitle')
        titles.addWidget(self.summary); header.addLayout(titles, 1); layout.addLayout(header)

        # Key/value facts: what, why, where.
        facts = QFrame(); facts.setObjectName('card'); grid = QGridLayout(facts)
        grid.setContentsMargins(18, 16, 18, 16); grid.setHorizontalSpacing(16); grid.setVerticalSpacing(12); grid.setColumnStretch(1, 1)
        rows = [('为什么需要', request.get('reason', '为完成当前任务，需要执行这一步。'), 'value'),
                ('网页' if request.get('kind') == 'browser' else '执行位置', request.get('location', event.get('detail', '')), 'path')]
        if request.get('value'):
            rows.append(('填写内容', request['value'], 'value'))
        for row, (key, value, style) in enumerate(rows):
            grid.addWidget(text_label(key, 'keyLabel'), row, 0, Qt.AlignTop)
            grid.addWidget(text_label(value, style), row, 1)
        layout.addWidget(facts)

        impact = QFrame(); impact.setObjectName('warnCard'); impact_layout = QVBoxLayout(impact)
        impact_layout.setContentsMargins(16, 12, 16, 12); impact_layout.setSpacing(4)
        impact_layout.addWidget(text_label('可能影响', 'section'))
        impact_layout.addWidget(text_label(request.get('impact', '请确认操作内容后继续。'), 'value'))
        layout.addWidget(impact)

        self.toggle = QPushButton('▸  查看原始操作'); self.toggle.setObjectName('link'); self.toggle.setCursor(Qt.PointingHandCursor)
        self.details = QTextEdit(); self.details.setObjectName('mono'); self.details.setReadOnly(True)
        self.details.setPlainText(request.get('raw', event.get('text', ''))); self.details.setMaximumHeight(180); self.details.hide()
        def toggle():
            expanded = self.details.isHidden()
            self.details.setVisible(expanded)
            self.toggle.setText('▾  收起原始操作' if expanded else '▸  查看原始操作')
            if expanded and self.height() < self.sizeHint().height():
                self.resize(self.width(), self.sizeHint().height())
        self.toggle.clicked.connect(toggle)
        layout.addWidget(self.toggle, 0, Qt.AlignLeft); layout.addWidget(self.details)
        outer.addWidget(body)

        deny = action_button('不允许', self.reject, 'ghost')
        allow = action_button('允许这一步', self.accept, True)
        # Deny keeps keyboard default so Enter never silently approves.
        deny.setDefault(True); deny.setAutoDefault(True); allow.setAutoDefault(False)
        outer.addWidget(footer_bar(right=(deny, allow)))
        self.adjustSize()


class QuestionDialog(QDialog):
    def __init__(self, questions, stop, parent=None):
        super().__init__(parent)
        self.questions = questions; self.inputs = []
        self.setWindowTitle('Anllm ' + APP_VERSION + ' · 补充一项信息')
        self.setMinimumWidth(560); self.resize(600, 10)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        body = QWidget(); layout = QVBoxLayout(body); layout.setContentsMargins(26, 24, 26, 18); layout.setSpacing(16)
        # Same header structure as ApprovalDialog: round icon, eyebrow, title.
        header = QHBoxLayout(); header.setSpacing(12)
        icon = QLabel('?'); icon.setObjectName('askIcon'); header.addWidget(icon, 0, Qt.AlignTop)
        titles = QVBoxLayout(); titles.setSpacing(3)
        titles.addWidget(text_label('需要你的决定', 'section'))
        titles.addWidget(text_label('请补充下面的信息' if len(questions) > 1 else '请补充一项信息', 'dialogTitle'))
        titles.addWidget(text_label('选一个建议答案，或直接写下你的想法。回答后任务会继续。', 'muted'))
        header.addLayout(titles, 1); layout.addLayout(header)

        content = QWidget(); stack = QVBoxLayout(content); stack.setContentsMargins(0, 0, 0, 0); stack.setSpacing(14)
        for number, question in enumerate(questions):
            card = QFrame(); card.setObjectName('card'); block = QVBoxLayout(card)
            block.setContentsMargins(18, 16, 18, 16); block.setSpacing(10)
            prefix = (str(number + 1) + '. ') if len(questions) > 1 else ''
            block.addWidget(text_label(prefix + readable(question['question']), 'role'))
            if question.get('context'):
                block.addWidget(text_label(readable(question['context']), 'muted'))
            combo = QComboBox(); combo.addItem('选择建议答案…', ''); combo.addItems([readable(item) for item in question.get('options', [])])
            custom = QLineEdit(); custom.setPlaceholderText('写下你的答案…')
            if question.get('options'):
                block.addSpacing(2); block.addWidget(combo)
                block.addWidget(text_label('或者自己填写', 'hint'))
            block.addWidget(custom)
            self.inputs.append((question, combo, custom))
            stack.addWidget(card)
        stack.addStretch()
        if len(questions) > 1:
            scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(content)
            scroll.setMinimumHeight(min(460, 190 * len(questions))); layout.addWidget(scroll, 1)
        else:
            layout.addWidget(content)
        self.status = text_label('', 'error'); self.status.hide(); layout.addWidget(self.status)
        for _, combo, custom in self.inputs:
            combo.currentIndexChanged.connect(self.clear_marks); custom.textChanged.connect(self.clear_marks)
        outer.addWidget(body, 1)

        stop_button = action_button('停止整个任务', stop, 'danger')
        stop_button.setToolTip('结束这一轮任务，不再继续执行')
        later = action_button('暂不回答', self.reject)
        self.submit_button = action_button('回答并继续', self.submit, True)
        outer.addWidget(footer_bar(left=(stop_button,), right=(later, self.submit_button)))
        self.adjustSize()

    def clear_marks(self, *_):
        for _, combo, custom in self.inputs:
            if custom.text().strip() or combo.currentIndex() > 0:
                for widget in (combo, custom):
                    widget.setProperty('invalid', False); widget.style().unpolish(widget); widget.style().polish(widget)

    def submit(self):
        missing = [number for number, (_, combo, custom) in enumerate(self.inputs, 1)
                   if not custom.text().strip() and combo.currentIndex() == 0]
        if missing:
            for number in missing:
                _, combo, custom = self.inputs[number - 1]
                for widget in (combo, custom):
                    widget.setProperty('invalid', True); widget.style().unpolish(widget); widget.style().polish(widget)
            which = '' if len(self.inputs) == 1 else '第 ' + '、'.join(map(str, missing)) + ' 题'
            self.status.setText('还有问题没有回答' + ('：' + which if which else '') + '。请选择建议答案或填写内容。'); self.status.show(); return
        self.status.clear(); self.status.hide()
        self.accept()

    def answer(self, accepted):
        return {'cancelled': not accepted, 'answers': [
            {'question': question['question'], 'answer': custom.text().strip() or combo.currentText()}
            for question, combo, custom in self.inputs] if accepted else []}
