"""Persisted sidebar state, worker-save isolation, and confirmed task deletion."""
import json
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QMessageBox
import core
from main import MainWindow

app=QApplication([])
items=[]
for title in ('检查项目','设计海报','整理资料'):
    item=core.new_session();item['title']=title;core.save_session(item);items.append(item)
a,b,c=[item['id'] for item in items]
core.save_task_order([a,b,c]);assert [item['id'] for item in core.sessions()]==[a,b,c]
core.save_session(items[2]);assert [item['id'] for item in core.sessions()]==[a,b,c],'Worker save disturbed manual order'
core.favorite_session(b,True);assert [item['id'] for item in core.sessions()]==[b,a,c]
core.favorite_session(c,True);assert [item['id'] for item in core.sessions()]==[c,b,a]
core.move_session(b,-1);assert [item['id'] for item in core.sessions()]==[b,c,a]
core.move_session(b,1);assert [item['id'] for item in core.sessions()]==[c,b,a]
core.move_session(b,'top');assert [item['id'] for item in core.sessions()]==[b,c,a]
core.favorite_session(b,False);assert [item['id'] for item in core.sessions()]==[c,b,a]
core.save_task_order([a,b,c]);assert [item['id'] for item in core.sessions()]==[c,a,b],'Favorites no longer pinned'
try:core.save_task_order([a,a,c])
except ValueError:pass
else:raise AssertionError('Duplicate task order accepted')
window=MainWindow();window.open_session(a)
assert window.session_list.item(0).text().startswith('★')
assert window.session_list.currentItem().data(Qt.UserRole)==a
window.toggle_task_favorite(b,True);assert window.session_list.item(0).data(Qt.UserRole)==b
window.move_task(b,1);assert window.session_list.item(0).data(Qt.UserRole)==c
# Exercise the same signal emitted after a completed internal drag.
row=window.session_list.takeItem(1);window.session_list.insertItem(0,row)
window.session_list.orderChanged.emit();app.processEvents()
assert [item['id'] for item in core.sessions()]==[b,c,a]
window.open_session(a)
project=core.ROOT/'workspace'/'keep.txt';project.write_text('project preserved',encoding='utf-8')
picture=core.ROOT/'images'/'keep.png';picture.write_bytes(b'preserve image data')
with patch('main.QMessageBox.question',return_value=QMessageBox.No):window.delete_task(a)
assert core.load_session(a)['id']==a and window.current['id']==a
window.worker=object()
with patch('main.QMessageBox.question') as prompt:window.delete_task(a);prompt.assert_not_called()
window.worker=None
with patch('main.QMessageBox.question',return_value=QMessageBox.Yes):window.delete_task(b)
assert window.current['id']==a,'Deleting inactive task changed current conversation'
assert b not in [item['id'] for item in core.sessions()]
with patch('main.QMessageBox.question',return_value=QMessageBox.Yes):window.delete_task(a)
assert window.current['id']==c,'Deleting current task failed to open remaining task'
with patch('main.QMessageBox.question',return_value=QMessageBox.Yes):window.delete_task(c)
assert len(core.sessions())==1 and window.current['messages']==[],'Empty sidebar failed to create a new task'
assert project.read_text('utf-8')=='project preserved' and picture.read_bytes()==b'preserve image data'
assert len(list((core.DATA/'deleted').glob('*.json')))==3
state=core.task_index();assert not state['favorites'] and not state['order']
window.close()
report={'status':'passed','manual_order_survives_worker_save':True,'favorites_pinned_and_reorderable':True,'drag_signal_persists_order':True,
    'delete_confirmation_and_cancel':True,'running_task_protected':True,'active_and_inactive_delete':True,'last_delete_creates_empty_task':True,
    'project_and_image_files_preserved':True,'removed_records_recoverable':True}
core.shared.atomic_json(core.ROOT/'logs'/'task-list-verification.json',report);print(json.dumps(report,ensure_ascii=False))
