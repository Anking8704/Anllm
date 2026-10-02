"""Real QThreads and main event routing, using controlled tasks without paid APIs."""
import asyncio,copy,json,threading,time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QDialog,QSystemTrayIcon
import core,main
from theme import STYLE

app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False);app.setStyleSheet(STYLE)

# Separate event loops writing the same file must keep each backup accurate.
target=core.ROOT/'workspace'/'parallel.txt';target.write_text('original','utf-8')
class FileInner:
    name='write_file';description='fixture';input_model=None
    def is_read_only(self,args):return False
    async def execute(self,args,context):
        await asyncio.sleep(.06);target.write_text(args.text,'utf-8');return core.ToolResult(output=args.text)
sessions=[core.new_session(),core.new_session()];completed=[]
def write(index):
    session=sessions[index];tool=core.SafeFileTool(FileInner(),session,lambda change:completed.append((index,change)))
    result=asyncio.run(tool.execute(SimpleNamespace(path='parallel.txt',text='writer-'+str(index)),SimpleNamespace(cwd=target.parent)))
    assert not result.is_error
with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(write,range(2)))
assert len(completed)==2
assert __import__('pathlib').Path(completed[0][1]['backup']).read_text('utf-8')=='original'
assert __import__('pathlib').Path(completed[1][1]['backup']).read_text('utf-8')=='writer-'+str(completed[0][0])

from desktop_control import DesktopService
native=SimpleNamespace(windows=lambda:[{'id':'fixture'}],window=lambda identifier:{'id':identifier},focus=lambda identifier:identifier)
desktop=DesktopService(native=native);desktop.begin('one');desktop.begin('two');desktop.windows('one');desktop.windows('two')
desktop.focus('one','fixture')
try:desktop.focus('two','fixture')
except ValueError as error:assert '另一个任务' in str(error)
else:raise AssertionError('Two tasks took control of the desktop')
desktop.end('one');assert desktop.focus('two','fixture')=='fixture';desktop.end('two');assert desktop.input_owner is None

gates={};started=set();answers={};finished=set()

async def task(session,text,attachments,mode,emit,approve,**kwargs):
    identifier=session['id'];gate=gates[identifier]
    session['messages'].append({'id':'user-'+identifier,'role':'user','text':text,'attachments':attachments})
    session['title']=text;message={'id':'answer-'+identifier,'role':'assistant','text':'','images':[]}
    session['messages'].append(message);emit({'type':'message','message':copy.deepcopy(message)})
    session['plan']={'steps':[text+'步骤']};emit({'type':'plan','plan':session['plan']})
    message['text']=text+'正在执行';emit({'type':'text','message_id':message['id'],'text':message['text']});core.save_session(session);started.add(identifier)
    try:
        while not gate.is_set():await asyncio.sleep(.01)
        if text=='任务甲':answers[identifier]=await approve('确认修改',{'summary':'任务甲修改自己的文件','raw':'fixture'},'测试请求')
        message['text']=text+'已完成'
    except asyncio.CancelledError:message['text']=text+'已停止'
    emit({'type':'text','message_id':message['id'],'text':message['text']});core.save_session(session);finished.add(identifier);return session

def pump(condition,timeout=7):
    deadline=time.monotonic()+timeout
    while not condition():
        app.processEvents();time.sleep(.003)
        assert time.monotonic()<deadline,'Timed out waiting for task routing'
    app.processEvents()

with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=False),patch('main.core.execute_task',task),patch.object(core.shared,'public_settings',return_value={'id':'legacy','name':'验证 API','key_configured':True,'chat_model':'gpt-5.2','chat_api':'chat'}),patch.object(core.shared,'cached_models',return_value=['gpt-5.2']):
    window=main.MainWindow();window.show();app.processEvents()
    def launch(title):
        window.new_chat();identifier=window.current['id'];gates[identifier]=threading.Event()
        window.current['chat_model']='gpt-5.2';window.update_models();window.prompt.setPlainText(title);window.send();return identifier
    a=launch('任务甲');pump(lambda:a in started)
    for widget in (window.new_button,window.folder_button,window.settings_button,window.session_list,window.task_actions,window.attach_button):assert widget.isEnabled()
    assert not window.prompt.isReadOnly() and not window.send_button.isEnabled()
    window.prompt.setPlainText('甲的下一条草稿')
    b=launch('任务乙');pump(lambda:b in started)
    assert len(window.workers)==2 and window.worker is window.workers[b]
    window.prompt.setPlainText('乙的下一条草稿')
    window.open_session(a);assert window.prompt.toPlainText()=='甲的下一条草稿'
    assert '任务甲正在执行' in window.current['messages'][-1]['text'] and '任务甲步骤' in window.plan.text()
    window.open_session(b);assert window.prompt.toPlainText()=='乙的下一条草稿' and '任务乙步骤' in window.plan.text()
    gates[a].set();pump(lambda:window.approval_dialog is not None)
    assert window.current['id']==b and window.approval_owner==a
    assert window.approval_dialog.windowModality()==Qt.NonModal and not app.activeModalWidget()
    assert '任务甲' in window.approval_dialog.windowTitle()
    window.new_chat();c=window.current['id'];assert window.new_button.isEnabled() and window.send_button.isEnabled()
    window.approval_dialog.accept();pump(lambda:a not in window.workers)
    assert answers[a] is True and window.current['id']==c and b in window.workers
    window.open_session(a);assert window.current['messages'][-1]['text']=='任务甲已完成' and window.prompt.toPlainText()=='甲的下一条草稿'
    window.open_session(b);window.stop();pump(lambda:not window.workers)
    assert core.load_session(b)['messages'][-1]['text']=='任务乙已停止'
    assert window.prompt.toPlainText()=='乙的下一条草稿' and window.send_button.isEnabled()
    d=launch('任务丁');e=launch('任务戊');pump(lambda:d in started and e in started)
    window.open_session(a);window.stop_all();pump(lambda:not window.workers)
    assert window.current['id']==a and core.load_session(d)['messages'][-1]['text']=='任务丁已停止' and core.load_session(e)['messages'][-1]['text']=='任务戊已停止'
    assert not window.live_sessions and not window.approval_queue
    window.request_exit();app.processEvents()

report={'status':'passed','two_real_workers_run_concurrently':True,'switch_and_start_other_tasks':True,'drafts_and_live_events_isolated':True,'nonmodal_approval_resolves_origin_worker':True,'background_completion_does_not_switch_view':True,'stop_current_keeps_others_running':True,'stop_all_works_from_idle_task':True,'workers_and_live_caches_released':True,'concurrent_file_backups_are_consistent':True,'desktop_input_exclusive_until_owner_finishes':True}
core.shared.atomic_json(core.ROOT/'logs'/'multitask-verification.json',report);print(json.dumps(report,ensure_ascii=False))
