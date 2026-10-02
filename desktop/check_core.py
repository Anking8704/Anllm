"""Meaningful local safety, persistence and OpenHarness-loop checks."""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import core
from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage,TextBlock,ToolUseBlock
from openharness.tools.base import ToolExecutionContext


class FakeClient:
    def __init__(self): self.calls=0
    async def stream_message(self,req):
        steps=[('read_file',{'path':'calc.py'}),
               ('edit_file',{'path':'calc.py','old_str':'return a - b','new_str':'return a + b'}),
               ('run_command',{'command':'Set-Content -LiteralPath denied.txt -Value "COMMAND_SHOULD_BE_DENIED"'})]
        if self.calls<len(steps):
            name,args=steps[self.calls];blocks=[ToolUseBlock(id='test_'+str(self.calls),name=name,input=args)]
        else:
            assert any('用户拒绝' in block.content for message in req.messages for block in message.content if hasattr(block,'tool_use_id'))
            blocks=[TextBlock(text='已修复加法。测试命令未获批准，没有执行。')]
        self.calls+=1
        yield ApiMessageCompleteEvent(message=ConversationMessage(role='assistant',content=blocks),usage=UsageSnapshot())


async def main():
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent,prefix='check-') as temporary:
        root=Path(temporary);workspace=root/'project';workspace.mkdir()
        (workspace/'calc.py').write_text('def add(a,b):\n    return a - b\n',encoding='utf-8')
        (workspace/'.env').write_text('SECRET_TEST',encoding='utf-8')
        data=root/'sessions';backups=data/'backups';backups.mkdir(parents=True)
        with patch.object(core,'DATA',data),patch.object(core,'BACKUPS',backups),patch.object(core,'PREFS',root/'prefs.json'):
            core.save_preferences({'workspace':str(workspace),'max_turns':8})
            for target in ('../outside.txt','.env','../project/.env','R:/OpenHarness/config/studio.json'):
                try: core.guard_path(workspace,target)
                except ValueError: pass
                else: raise AssertionError('Forbidden path accepted: '+target)
            listed=list(core.eligible_files(workspace))
            assert [path.name for path in listed]==['calc.py']
            session=core.new_session();events=[];approvals=[]
            async def deny(title,command,detail): approvals.append(command);return False
            client=FakeClient()
            await core.execute_task(session,'修复加法并验证',[],'agent',events.append,deny,client)
            assert client.calls==4
            assert 'return a + b' in (workspace/'calc.py').read_text('utf-8')
            assert len(approvals)==1 and len(session['changes'])==1
            assert not (workspace/'denied.txt').exists()
            assert len([event for event in events if event['type']=='tool_end'])==3
            restored=core.load_session(session['id'])
            assert len(restored['history'])==8 and len(restored['changes'])==1
            change=session['changes'][0]
            (workspace/'calc.py').write_text('modified later',encoding='utf-8')
            try: core.restore_change(session,change)
            except ValueError: pass
            else: raise AssertionError('Undo overwrote a later edit')
            (workspace/'calc.py').write_text('def add(a,b):\n    return a + b\n',encoding='utf-8')
            core.restore_change(session,change)
            assert 'return a - b' in (workspace/'calc.py').read_text('utf-8')
            # New file undo retains the created file in recoverable storage.
            context=ToolExecutionContext(cwd=workspace)
            tool=core.SafeFileTool(core.FileWriteTool(),session,lambda _:None)
            result=await tool.execute(tool.input_model(path='new.md',content='keep recoverable'),context)
            assert not result.is_error
            change=session['changes'][-1];core.restore_change(session,change)
            assert not (workspace/'new.md').exists() and Path(change['undone_file']).read_text('utf-8')=='keep recoverable'
            # Stops pending approvals and saves a usable conversation.
            session=core.new_session();started=asyncio.Event()
            async def wait_approval(*args): started.set();await asyncio.Future()
            task=asyncio.create_task(core.execute_task(session,'取消验证',[],'agent',lambda _:None,wait_approval,FakeClient()))
            await asyncio.wait_for(started.wait(),5);task.cancel();await task
            assert '已停止' in session['messages'][-1]['text']
            assert core.load_session(session['id'])['history']
    print('PASS: real OpenHarness loop, sequential tools, denied commands, scope/secrets, persistent history, backup/diff, conflict-safe undo, recoverable new-file undo, cancellation.')


asyncio.run(main())
