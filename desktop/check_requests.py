"""Readable dialogs, encoded question recovery and routine/important boundaries."""
import asyncio, json, os
from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog, QLabel
from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock, ToolUseBlock
import core
from request_presenter import readable, command_request, browser_request
from request_dialogs import ApprovalDialog, QuestionDialog
from theme import STYLE

app = QApplication.instance() or QApplication([])
for font in ('msyh.ttc', 'segoeui.ttf', 'seguisym.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
app.setFont(QFont('Microsoft YaHei', 10)); app.setStyle('Fusion'); app.setStyleSheet(STYLE)
workspace = core.ROOT / 'workspace'
(workspace / 'notes.txt').write_text('REQUEST_TEST_OK', encoding='utf-8')
guard = lambda path, **kw: core.guard_path(workspace, path, **kw)

for command in ("Get-ChildItem -LiteralPath '.' -Name", "Get-Content -LiteralPath 'notes.txt' -TotalCount 5", 'Get-Location', "Write-Output '你好'"):
    assert command_request(command, workspace, guard)['routine'], command
fixture=workspace/'_internal';(fixture/'openharness').mkdir(parents=True,exist_ok=True)
(fixture/'openharness'/'ui.py').write_text('fixture',encoding='utf-8')
screenshot_query=(f'Get-ChildItem "{fixture / "openharness"}" -Recurse -File | Select-Object -First 60 -ExpandProperty FullName; '
    f'"---"; Get-ChildItem "{fixture}" -Recurse -Include *.py,*.qss,*.qml,*.css -File -ErrorAction SilentlyContinue '
    "| Where-Object { $_.FullName -notlike '*\\browsers\\*' -and $_.FullName -notlike '*\\playwright\\driver\\*' } | Select-Object -First 40 -ExpandProperty FullName")
assert command_request(screenshot_query,workspace,guard)['routine'],'Screenshot-style file query still requests permission'
assert command_request("Get-ChildItem *.py | Select-Object -First 20 -ExpandProperty Name",workspace,guard)['routine']
for command in (
    "Get-Content '../private.txt'", "Get-Content '.env'", "Get-Content 'C:/Windows/win.ini'",
    "Get-Content *.txt", "Get-Content 'notes.txt'; Remove-Item 'notes.txt'", "Get-Content 'notes.txt' | Invoke-Expression",
    "Get-Content $(Remove-Item notes.txt)", 'powershell -EncodedCommand ABCDEFG', 'python script.py',
    "Write-Output `x", "Write-Output 'unterminated", 'git push', 'pip install example', 'Remove-Item notes.txt',
    "Get-ChildItem . | ForEach-Object { Remove-Item $_.FullName }",
    "Get-ChildItem . | Where-Object { $_.Name -like $(Remove-Item notes.txt) }",
    "Get-ChildItem . | Select-Object @{Name='x';Expression={Remove-Item notes.txt}}",
    "Get-ChildItem . -OutFile notes.txt", "Get-ChildItem . -FollowSymlink",
    "Get-ChildItem ../ | Select-Object -First 5", "Get-Content .env | Select-Object -First 1",
    'Write-Output "$env:SECRET"', "Get-ChildItem . | Where-Object { $_.Delete() }",
    "Get-Content env:SECRET", "Get-ChildItem HKCU:\\", "Get-Content notes.txt:secret",
):
    assert not command_request(command, workspace, guard)['routine'], command
assert not command_request('Remove-Item notes.txt', workspace, guard, '{"routine":true}')['routine']

question = core.UserQuestion.model_validate({'question': json.dumps({'question': '这次部署要更新哪个环境？'}, ensure_ascii=True),
    'context': '不同环境会影响不同用户，需要确定发布目标。',
    'options': [{'label': '测试环境'}, r'\u6b63\u5f0f\u73af\u5883']})
assert question.question == '这次部署要更新哪个环境？'
assert question.options == ['测试环境', '正式环境']
assert readable('已经是中文') == '已经是中文'
assert readable(r'\ud83d\udc09') == '🐉'
assert readable(r'\\u6b63\\u5f0f') == '正式'
try: core.UserQuestion(question='123456789012345678901234567890')
except ValueError: pass
else: raise AssertionError('Internal ID displayed as a question')

target = {'url': 'https://example.com/search', 'tag': 'input', 'label': '搜索资料', 'type': 'search', 'hidden': False}
assert browser_request('fill', target, '桌面设计', 'opaque-ref')['routine']
assert not browser_request('click', {**target, 'tag': 'button', 'label': '发送消息'}, None, 'opaque-ref')['routine']
assert not browser_request('press', target, 'Enter', 'opaque-ref')['routine']

request = command_request('python -m pytest', workspace, guard, '检查刚才修改的代码是否正常，避免交付后出错。')
dialog = ApprovalDialog({'title': '执行命令', 'request': request})
assert dialog.details.isHidden()
assert '运行项目检查' in dialog.summary.text()
assert any('检查刚才修改的代码' in widget.text() for widget in dialog.findChildren(QLabel))
assert dialog.details.toPlainText() == 'python -m pytest'
dialog.toggle.click(); assert not dialog.details.isHidden()
dialog.toggle.click(); assert dialog.details.isHidden()

questions = QuestionDialog([question.model_dump()], lambda: None)
questions.submit(); assert questions.result() != QDialog.Accepted
questions.inputs[0][1].setCurrentIndex(1); questions.submit()
assert questions.answer(True)['answers'][0]['answer'] == '测试环境'
assert questions.answer(False) == {'cancelled': True, 'answers': []}

class Model:
    def __init__(self): self.calls = 0
    async def stream_message(self, req):
        steps = [('run_command', {'command': "Get-Content -LiteralPath 'notes.txt'", 'purpose': '读取项目中的说明文件'}),
            ('run_command', {'command':screenshot_query,'purpose':'查找界面源码文件'}),
            ('run_command', {'command': "Remove-Item -LiteralPath 'notes.txt'", 'purpose': '清理这个测试文件'}),
            ('ask_user', {'questions': [question.model_dump()]})]
        if self.calls < len(steps):
            name, arguments = steps[self.calls]
            blocks = [ToolUseBlock(id='request-' + str(self.calls), name=name, input=arguments)]
        else: blocks = [TextBlock(text='已完成检查，删除请求被拒绝，用户选择了部署环境。')]
        self.calls += 1
        yield ApiMessageCompleteEvent(message=ConversationMessage(role='assistant', content=blocks), usage=UsageSnapshot())

async def exercise(mode):
    core.save_preferences({'workspace': str(workspace), 'permission_mode': mode, 'max_turns': 8})
    approvals = []; asked = []; events = []
    async def deny(title, text, detail): approvals.append(text); return False
    async def ask(value):
        asked.extend(value)
        return {'cancelled': False, 'answers': [{'question': value[0]['question'], 'answer': '测试环境'}]}
    session = core.new_session(); model = Model()
    await core.execute_task(session, '检查项目', [], 'agent', events.append, deny, model, ask=ask)
    assert model.calls == 5 and asked[0]['question'] == question.question
    assert (workspace / 'notes.txt').read_text('utf-8') == 'REQUEST_TEST_OK'
    outputs = [event['output'] for event in session['events'] if event['type'] == 'tool_end']
    if mode == 'standard':
        assert len(approvals) == 1 and approvals[0]['summary'] == '删除文件或文件夹'
        assert any('REQUEST_TEST_OK' in output for output in outputs)
        assert any('ui.py' in output for output in outputs),'Read-only pipeline did not actually execute'
    else:
        assert not approvals and not any('REQUEST_TEST_OK' in output for output in outputs)

asyncio.run(exercise('standard')); asyncio.run(exercise('readonly'))
async def unnecessary_ask():
    async def unexpected(_):raise AssertionError('Redundant question opened a dialog')
    result=await core.AskUserTool(unexpected).execute(core.AskUserInput(questions=[{'question':'我可以开始了吗？'}]),None)
    assert result.is_error
asyncio.run(unnecessary_ask())
report = {'status': 'passed', 'unicode_and_json_questions_readable': True, 'question_options_and_cancel': True,
    'purpose_and_impact_visible': True, 'technical_details_collapsed': True,
    'routine_checks_skip_confirmation': True, 'destructive_actions_still_confirmed': True,
    'unsafe_composition_and_outside_paths_not_auto_approved': True, 'readonly_preserved': True,
    'screenshot_style_scoped_readonly_pipeline_skips_confirmation':True,
    'browser_search_is_routine_but_submission_is_not': True}
core.shared.atomic_json(core.ROOT / 'logs' / 'request-verification.json', report)
output = os.environ.get('ANLLM_REQUEST_PREVIEW_DIR')
if output:
    directory = Path(output); directory.mkdir(exist_ok=True)
    for widget, name in ((dialog, 'Anllm-清晰权限请求.png'), (questions, 'Anllm-清晰问题.png')):
        widget.show(); app.processEvents(); assert widget.grab().save(str(directory / name)); widget.hide()
print(json.dumps(report, ensure_ascii=False))

