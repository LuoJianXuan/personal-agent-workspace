"""Deterministic MODEL only; all tools and persistence remain real."""
import asyncio,json,re
from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage,AIMessageChunk,ToolMessage
from langchain_core.outputs import ChatResult,ChatGeneration,ChatGenerationChunk
from pydantic import Field
from .models import RunError

class MockChatModel(BaseChatModel):
    engine: Any=Field(exclude=True)
    start: dict=Field(exclude=True)
    available: list[str]=Field(default_factory=list,exclude=True)
    @property
    def _llm_type(self):return 'workspace-mock'
    def _get_ls_params(self,**kwargs):return {'ls_provider':'workspace-mock','ls_model_name':'workspace-mock','ls_model_type':'chat'}
    def bind_tools(self,tools,**kwargs):
        names=[t.name if hasattr(t,'name') else t.get('function',t).get('name','') for t in tools]
        return self.model_copy(update={'available':names})
    def answer(self,messages):
        prompt=str(next((m.content for m in reversed(messages) if m.type=='human'),''))
        calls=[c['name'] for m in messages if isinstance(m,AIMessage) for c in m.tool_calls]
        def tool(name,args,id):return AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':id,'type':'tool_call'}])
        lookup=next((n for n in self.available if n.startswith('mcp_')),None)
        if prompt.startswith('<role>\nContext Extraction Assistant'):
            return AIMessage(content='合成摘要：保留约束 P1-KEEP。没有待执行的写入。原始历史由受控文件保留。')
        if prompt.startswith('mock:context'):
            return AIMessage(content='上下文验收完成；约束：P1-KEEP。')
        if 'mock:documents-skill' in prompt and 'mock:documents-skill-write' not in prompt:
            system='\n'.join(str(m.content) for m in messages if m.type=='system')
            full_in_prompt='先用 `builtin_read_material` 读取用户本轮明确授权' in system
            if 'read_file' not in calls:
                return tool('read_file',{'file_path':'/skills/documents/SKILL.md'},'documents-skill-read')
            loaded=any(isinstance(m,ToolMessage) and '# 文档工作' in str(m.content) for m in messages)
            return AIMessage(content=f'技能摘要装配={str(not full_in_prompt).lower()}；正文按需读取={str(loaded).lower()}。')
        if 'mock:documents-skill-write' in prompt:
            if 'write_file' not in calls:
                return tool('write_file',{'file_path':'/skills/documents/SKILL.md','content':'tamper'},'documents-skill-write')
            denied=any(isinstance(m,ToolMessage) and 'WORKFILE_READ_ONLY' in str(m.content) for m in messages)
            return AIMessage(content=f'技能只读拒绝={str(denied).lower()}。')
        if 'mock:workspace' in prompt:
            path='/work/acceptance-'+self.start['run_id']+'.md'
            if 'write_todos' not in calls:return tool('write_todos',{'todos':[{'content':'核对工作文件金额','status':'in_progress'}]},'workspace-plan')
            if 'write_file' not in calls:return tool('write_file',{'file_path':path,'content':'原始金额100'},'workspace-write')
            if 'edit_file' not in calls:return tool('edit_file',{'file_path':path,'old_string':'100','new_string':'150'},'workspace-edit')
            if 'read_file' not in calls:return tool('read_file',{'file_path':path},'workspace-read')
            if calls.count('write_todos')==1:return tool('write_todos',{'todos':[{'content':'核对工作文件金额','status':'completed'}]},'workspace-done')
            return AIMessage(content='工作文件已读取核对，金额为150。')
        if 'mock:offload' in prompt and 'builtin_read_material' not in calls:
            return tool('builtin_read_material',{'file_id':self.start['file_refs'][0]['id'],'limit':10},'offload-read')
        if 'mock:xlsx' in prompt and 'builtin_csv_summary' not in calls:
            return tool('builtin_csv_summary',{'file_id':self.start['file_refs'][0]['id'],'dimension':'地区','measure':'金额','aggregation':'sum','chart_type':'bar','sheet':'数据'},'xlsx-summary')
        if 'mock:budget' in prompt:
            return tool('read_file',{'file_path':'/work/missing-budget-fixture'},'budget-'+str(len(calls)))
        if 'mock:research' in prompt:
            if 'builtin_web_search' not in calls:return tool('builtin_web_search',{'query':'合成验收方案对比','max_results':3},'research-search')
            count=calls.count('builtin_fetch_page')
            discovered=[]
            for message in messages:
                if isinstance(message,ToolMessage):
                    try:discovered.extend(s for s in json.loads(str(message.content)).get('sources',[]) if s['read_status']=='search_only')
                    except (ValueError,AttributeError):pass
            if len(discovered)<3:return AIMessage(content='搜索未提供足够来源，无法继续研究或生成研究报告。')
            if count<3:return tool('builtin_fetch_page',{'url':discovered[count]['url']},f'research-fetch-{count}')
        if 'mock:compare' in prompt:
            count=calls.count('builtin_read_material')
            if count<len(self.start['file_refs']):return tool('builtin_read_material',{'file_id':self.start['file_refs'][count]['id']},f'compare-read-{count}')
        if any(k in prompt for k in ('mock:research','mock:compare','mock:report')) and 'builtin_publish_report' not in calls:
            sources=[]
            for m in messages:
                if isinstance(m,ToolMessage):
                    try:sources.extend(json.loads(str(m.content)).get('sources',[]))
                    except (ValueError,AttributeError):pass
            sources=[s for s in sources if s['read_status']!='search_only']
            body='# 合成验收报告\n\n'+('\n\n'.join(s['excerpt'][:400]+' [source:'+s['source_id']+']' for s in sources) if sources else '本报告用于确认真实产物链路，不代表模型质量。')
            args={'title':'合成验收报告','content':body,'source_ids':[s['source_id'] for s in sources],'docx':True}
            if 'mock:version' in prompt and self.start['file_refs']:args['parent_file_id']=self.start['file_refs'][0]['id']
            return tool('builtin_publish_report',args,'publish-report')
        if 'mock:python' in prompt and 'builtin_python' not in calls:
            code="from pathlib import Path\nfrom decimal import Decimal\nimport csv,json\nmanifest=json.loads(Path('/work/manifest.json').read_text())\nsource=Path(manifest['files'][0]['path'])\ntotals={}\nwith source.open(encoding='utf-8-sig',newline='') as f:\n for row in csv.DictReader(f):totals[row['group']]=totals.get(row['group'],Decimal(0))+Decimal(row['value'])\nwith Path('/work/outputs/result.csv').open('w',encoding='utf-8',newline='') as f:\n writer=csv.writer(f);writer.writerow(['group','total']);writer.writerows(sorted(totals.items()))\nprint('computed from authorized input')"
            if 'mock:python-cancel' in prompt:code='import time;time.sleep(25)'
            return tool('builtin_python',{'code':code,'file_ids':[f['id'] for f in self.start['file_refs']]},'compute-1')
        if 'mock:ticket' in prompt:
            if lookup and lookup not in calls:return tool(lookup,{'order_id':'DEMO-1001'},'order-lookup')
            if 'builtin_create_demo_ticket' not in calls:return tool('builtin_create_demo_ticket',{'order_id':'DEMO-1001','title':'订单跟进','description':'根据合成订单信息创建跟进工单'},'ticket-1')
        if 'mock:read' in prompt and not isinstance(messages[-1],ToolMessage):
            match=re.search(r'mock:read ([0-9a-f-]{36})',prompt)
            if match:return tool('builtin_read_material',{'file_id':match[1]},'read-1')
        if 'mock:tool' in prompt and not isinstance(messages[-1],ToolMessage):
            if not lookup:raise RunError('TOOL_DENIED')
            return tool(lookup,{'order_id':'DEMO-1001'},'mock-call-1')
        if 'mock:fetch' in prompt and 'builtin_fetch_page' not in calls:
            return tool('builtin_fetch_page',{'url':prompt.split('mock:fetch',1)[1].strip().split()[0]},'fetch-1')
        text=('工具查询结果：'+str(messages[-1].content)) if isinstance(messages[-1],ToolMessage) else ('Mock 回答：'+prompt+'。历史用户轮数：'+str(sum(m.type=='human' for m in messages)))
        if 'mock:long' in prompt:text='用于验证持久化增量和断线补读。'*40
        return AIMessage(content=text)
    def _generate(self,messages,stop=None,run_manager=None,**kwargs):raise RunError('ASYNC_MODEL_REQUIRED')
    async def _agenerate(self,messages,stop=None,run_manager=None,**kwargs):
        call=await self.engine.reserve_model(self.start)
        result=self.answer(messages);await self.engine.model_result(call,'SUCCEEDED',{},'')
        return ChatResult(generations=[ChatGeneration(message=result)])
    async def _astream(self,messages,stop=None,run_manager=None,**kwargs):
        call=await self.engine.reserve_model(self.start)
        try:
            result=self.answer(messages)
            if result.tool_calls:
                yield ChatGenerationChunk(message=AIMessageChunk(content='',tool_call_chunks=[{'name':c['name'],'args':json.dumps(c['args'],ensure_ascii=False),'id':c['id'],'index':i} for i,c in enumerate(result.tool_calls)]))
            else:
                prompt=str(next((m.content for m in reversed(messages) if m.type=='human'),''))
                for i in range(0,len(result.content),4):
                    await self.engine.check_cancel(self.start['run_id'])
                    yield ChatGenerationChunk(message=AIMessageChunk(content=result.content[i:i+4]));await asyncio.sleep(.05)
                    if 'mock:fail' in prompt and i>=12:raise RunError('MODEL_STREAM_FAILED')
            await self.engine.model_result(call,'SUCCEEDED',{},'')
        except BaseException:
            await self.engine.model_result(call,'FAILED',{},'MODEL_STREAM_FAILED');raise
