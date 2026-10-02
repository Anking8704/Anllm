"""Parallel desktop teammates, each with its own actual OpenHarness model loop."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
import uuid

from pydantic import BaseModel,Field
from openharness.tools.base import BaseTool,ToolResult,ToolRegistry
from openharness.engine.query import QueryContext,run_query
from openharness.engine.messages import ConversationMessage,TextBlock
from openharness.engine.stream_events import AssistantTurnComplete,ToolExecutionStarted,ToolExecutionCompleted,ErrorEvent


class TaskSpec(BaseModel):
    name: str = Field(min_length=1,max_length=45,description='Teammate name, such as reviewer, frontend, tests')
    task: str = Field(min_length=1,max_length=12000,description='Complete self-contained task. Explain expected results and constraints.')
    write_paths: list[str] = Field(default_factory=list,max_length=12,description='Explicit disjoint project files/directories this worker may edit. Empty means read-only. End a new directory with /. Commands are executed by the main agent after workers finish.')


class DelegateInput(BaseModel):
    tasks: list[TaskSpec] = Field(min_length=1,max_length=4,description='Independent parallel tasks. Do not assign overlapping write paths.')


class AgentIDInput(BaseModel):
    agent_id: str = Field(description='Agent identifier returned by delegate_tasks or agent_status')


class StatusInput(BaseModel):
    agent_id: str | None = None


class AgentTeam:
    def __init__(self,session,config,emit,approve,changed,*,client_factory=None,browser_service=None,permission_mode=None):
        import core
        self.core=core;self.session,self.config,self.emit,self.approve,self.changed=session,config,emit,approve,changed
        self.workspace=Path(session['workspace']).resolve()
        self.permission_mode=permission_mode or core.preferences()['permission_mode']
        self.client_factory=client_factory or (lambda _:core.CompatibleClient({**config,'provider_context':{}}));self.browser_service=browser_service
        self.running={};self.claims={};self.semaphore=asyncio.Semaphore(core.preferences().get('parallel_agents',3));self.total=0

    def allow_write(self,identity,path):
        if self.permission_mode=='readonly': raise ValueError('当前只读权限，不允许修改文件。')
        path=Path(path).resolve()
        if identity!='main':
            scopes=self.claims.get(identity,[])
            if not any(path==scope or (directory and path.is_relative_to(scope)) for scope,directory in scopes):
                raise ValueError('该助手仅可修改分配的文件 / 目录；未分配的路径禁止写入。')
        for other,scopes in self.claims.items():
            if other==identity: continue
            if any(path==scope or (directory and path.is_relative_to(scope)) for scope,directory in scopes):
                raise ValueError('该文件正在由其他助手处理，请等待其完成，避免覆盖修改。')

    def _publish(self,record):
        self.core.save_session(self.session)
        self.emit({'type':'agent','agent':dict(record)})

    def records(self): return self.session.setdefault('agents',[])

    async def delegate(self,specs):
        if self.total+len(specs)>12: raise ValueError('本条任务最多创建 12 个助手，避免无限拆分。')
        planned=[];used=[scope for scopes in self.claims.values() for scope in scopes]
        for spec in specs:
            if self.permission_mode=='readonly' and spec.write_paths: raise ValueError('只读权限下助手不能分配写入范围。')
            scopes=[]
            for candidate in spec.write_paths:
                path=self.core.guard_path(self.workspace,candidate,directory=candidate.endswith(('/','\\')) or Path(candidate).suffix=='')
                directory=candidate.endswith(('/','\\')) or path.is_dir()
                for previous,previous_directory in used:
                    if path==previous or (directory and previous.is_relative_to(path)) or (previous_directory and path.is_relative_to(previous)):
                        raise ValueError('并行助手的写入范围重叠，请划分不同的文件 / 目录，或按顺序委派。')
                scopes.append((path,directory));used.append((path,directory))
            identifier=uuid.uuid4().hex[:10]
            planned.append((identifier,spec,scopes))
        self.total+=len(planned)
        records=[]
        for identifier,spec,scopes in planned:
            self.claims[identifier]=scopes
            record={'id':identifier,'name':spec.name,'task':spec.task,'status':'queued','text':'','tools':0,
                'write_paths':spec.write_paths,'started':time.time(),'events':[]}
            self.records().append(record);self._publish(record);records.append(record)
            self.running[identifier]=asyncio.create_task(self._worker(record,spec),name='teammate-'+identifier)
        try:
            # Real independent model requests run concurrently; results all reach the coordinator.
            await asyncio.gather(*(self.running[record['id']] for record in records),return_exceptions=True)
        except asyncio.CancelledError:
            for record in records:
                task=self.running.get(record['id'])
                if task: task.cancel()
            await asyncio.gather(*(self.running[r['id']] for r in records if r['id'] in self.running),return_exceptions=True)
            raise
        finally:
            for record in records:
                self.running.pop(record['id'],None);self.claims.pop(record['id'],None)
                if record['status'] in ('queued','running'):
                    record['status']='stopped';record['text']+='\n助手已停止。';record['finished']=time.time();self._publish(record)
        return [{'agent_id':record['id'],'name':record['name'],'status':record['status'],'result':record['text'][:18000],
            'tools':record['tools'],'write_paths':record['write_paths']} for record in records]

    async def _worker(self,record,spec):
        import browser_bridge
        core=self.core;identity=record['id']
        def emit(event):
            item={**event,'agent_id':identity,'agent_name':record['name']}
            if item['type']=='browser':
                self.session.setdefault('browser_pages',{})[item['browser']['page_id']]=item['browser']
            self.emit(item)
        def changed(change):
            change['agent_id']=identity;change['agent_name']=record['name'];self.changed(change)
        try:
            async with self.semaphore:
                record['status']='running';self._publish(record)
                registry=ToolRegistry()
                from modal_tools import AnalyzeImagesTool
                registry.register(AnalyzeImagesTool(self.config,lambda:core.session_image_names(self.session),lambda:core.session_image_names(self.session),self.workspace,emit,
                    pages=lambda:self.session.get('browser_pages',{}),owner=self.session['id']+':'+identity))
                registry.register(core.SafeFileTool(core.FileReadTool(),self.session,changed))
                for tool in (core.ListFilesTool(),core.SearchFilesTool(),core.WebFetchTool(),core.WebSearchTool()): registry.register(tool)
                if spec.write_paths:
                    for tool in (core.FileWriteTool(),core.FileEditTool()):
                        registry.register(core.SafeFileTool(tool,self.session,changed,write_check=lambda path:self.allow_write(identity,path)))
                # Worker tabs are isolated by owner; browsing is read-only. The coordinator handles mutations.
                for tool in browser_bridge.tools(self.session['id']+':'+identity,emit,self.approve,read_only=True,service=self.browser_service): registry.register(tool)
                system=core.SYSTEM+f'\n你是协作助手 {spec.name}。只完成分配的子任务，不扩展任务，不再创建助手。\n当前工作目录：{self.workspace}\n允许修改的范围：{json.dumps(spec.write_paths,ensure_ascii=False) if spec.write_paths else "只读，不修改文件"}\n你不能执行命令或点击网页；测试命令和最终验证由主 Agent 执行。需要检查图片或自己浏览器页面截图时调用 analyze_images，它使用用户配置的视觉模型。最后提供具体结果、检查证据和未解决问题。'
                agent_file=self.workspace/'AGENTS.md'
                if agent_file.is_file(): system+='\n当前项目约定：\n'+agent_file.read_text('utf-8',errors='replace')[:12000]
                history=[ConversationMessage.from_user_text(spec.task)]
                context=QueryContext(api_client=self.client_factory(spec),tool_registry=registry,
                    permission_checker=core.DesktopPermissions(self.workspace,'agent',self.permission_mode),cwd=self.workspace,
                    model=self.config['chat_model'],system_prompt=system,max_tokens=8192,
                    max_turns=min(core.preferences()['max_turns'],20),tool_metadata={})
                async for event,_ in run_query(context,history):
                    if isinstance(event,AssistantTurnComplete) and event.message.text:
                        record['text']+=('\n\n' if record['text'] else '')+event.message.text
                    elif isinstance(event,ToolExecutionStarted):
                        record['tools']+=1
                        item={'type':'tool_start','name':event.tool_name,'input':event.tool_input,'time':time.time(),'agent_id':identity,'agent_name':record['name']}
                        record['events'].append(item);self.session['events'].append(item);emit(item)
                    elif isinstance(event,ToolExecutionCompleted):
                        item={'type':'tool_end','name':event.tool_name,'output':core.scrub(event.output)[:12000],'error':event.is_error,
                            'time':time.time(),'agent_id':identity,'agent_name':record['name']}
                        record['events'].append(item);self.session['events'].append(item);emit(item)
                    elif isinstance(event,ErrorEvent): raise ValueError(event.message)
                    self._publish(record)
                record['status']='completed'
        except asyncio.CancelledError:
            record['status']='stopped';record['text']+='\n助手已停止，已完成的文件修改保留。'
        except Exception as error:
            record['status']='failed';record['text']+='\n'+core.scrub(error)
        finally:
            record['finished']=time.time();self.claims.pop(identity,None);self._publish(record)

    def cancel(self,identifier):
        task=self.running.get(identifier)
        if task and not task.done(): task.cancel();return True
        return False

    async def close(self):
        tasks=list(self.running.values())
        for task in tasks:
            if not task.done(): task.cancel()
        if tasks: await asyncio.gather(*tasks,return_exceptions=True)


class DelegateTool(BaseTool):
    name='delegate_tasks'
    description='Delegate independent tasks to actual concurrent teammates and wait for all results. Give self-contained tasks, disjoint write_paths or read-only scopes. The main agent must synthesize and verify the results. Each teammate uses the configured model and consumes API tokens.'
    input_model=DelegateInput
    def __init__(self,team): self.team=team
    async def execute(self,args,context):
        try: return ToolResult(output=json.dumps(await self.team.delegate(args.tasks),ensure_ascii=False))
        except asyncio.CancelledError: raise
        except Exception as error: return ToolResult(output=str(error),is_error=True)


class StatusTool(BaseTool):
    name='agent_status';description='Inspect current teammate states, task assignments and collected results.';input_model=StatusInput
    def __init__(self,team): self.team=team
    def is_read_only(self,args): return True
    async def execute(self,args,context):
        records=[record for record in self.team.records() if not args.agent_id or record['id']==args.agent_id]
        return ToolResult(output=json.dumps([{key:record.get(key) for key in ('id','name','status','task','text','tools','write_paths')} for record in records],ensure_ascii=False)[:40000])


class CancelTool(BaseTool):
    name='stop_agent';description='Stop one running teammate by its returned id. Completed file changes are retained.';input_model=AgentIDInput
    def __init__(self,team): self.team=team
    async def execute(self,args,context):
        return ToolResult(output=json.dumps({'agent_id':args.agent_id,'stopped':self.team.cancel(args.agent_id)},ensure_ascii=False))
