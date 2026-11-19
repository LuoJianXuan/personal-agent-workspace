"""Agent-facing façade for governed tools; executors remain internal modules."""
import asyncio,json
from uuid import uuid5,UUID
from .models import RunError,safe_text
from .canonical import canonical
from .approvals import FaultPause
from .tool_execution import ToolRegistry,PolicyEngine,ExecutionLifecycle,ExecutionRouter

class ToolGatewayService:
    def __init__(self,engine,start):
        self.engine=engine;self.start=start
        self.registry=ToolRegistry(start);self.policy=PolicyEngine(engine,start)
        self.lifecycle=ExecutionLifecycle(engine,start);self.router=ExecutionRouter()
    def find(self,call):
        return self.registry.tools.get(call['function']['name'])
    async def record(self,call,eid,kind,status,text):
        await self.engine.event(self.start['run_id'],kind,{'execution_id':eid,'tool_call_id':call['id'],'status':status,'text':safe_text(text),'file_refs':[]})
    async def filesystem(self,request,handler):
        from langchain_core.messages import ToolMessage
        native=request.tool_call;eid=str(uuid5(UUID(self.start['run_id']),native['id']))
        await self.record(native,eid,'tool.requested','REQUESTED',native['name'])
        await self.engine.authorize(self.start)
        _,digest=canonical(native['args'])
        old=await self.lifecycle.begin(eid,native['name'],digest)
        if old is not None:return ToolMessage(content=old,tool_call_id=native['id'])
        await self.record(native,eid,'tool.started','RUNNING',native['name'])
        try:
            result=await handler(request)
            status='FAILED' if getattr(result,'status','success')=='error' else 'SUCCEEDED'
            await self.lifecycle.finish(eid,native['id'],status,safe_text(str(getattr(result,'content','文件操作已完成'))))
            return result
        except BaseException:
            await self.lifecycle.finish(eid,native['id'],'UNKNOWN','FILE_EXECUTION_INTERRUPTED')
            raise
    async def execute(self,call,decision_id=None,approval_id=None):
        name=call['function']['name'];eid=str(uuid5(UUID(self.start['run_id']),call['id']))
        owned=False
        spec = self.find(call)
        label = spec.get('display_name', name) if spec else name
        await self.record(call,eid,'tool.requested','REQUESTED',label)
        try:
            tool=self.registry.resolve(name);args=json.loads(call['function']['arguments'])
            raw,digest=await self.policy.admit(tool,args,eid,approval_id,decision_id)
            connection=next((c for c in self.start['effective_capabilities'].get('mcp_connections',[]) if c['id']==tool.get('connection_id')),None)
            old=await self.lifecycle.begin(eid,name,digest,decision_id,tool.get('connection_id'),connection.get('max_calls_per_minute',0) if connection else 0)
            if old is not None:return {'role':'tool','tool_call_id':call['id'],'content':old}
            owned=True
            await self.policy.reserve(tool,eid)
            await self.record(call,eid,'tool.started','RUNNING',label)
            result=await self.router.dispatch(self.engine,self.start,tool,args,eid,raw,decision_id)
            text=safe_text(result.text)
            await self.lifecycle.finish(eid,call['id'],'SUCCEEDED',text)
            return {'role':'tool','tool_call_id':call['id'],'content':text}
        except asyncio.CancelledError:
            if owned:await self.lifecycle.finish(eid,call['id'],'UNKNOWN','TOOL_EXECUTION_INTERRUPTED')
            raise
        except FaultPause:raise
        except Exception as e:
            code=e.code if isinstance(e,RunError) else ('TOOL_TIMEOUT' if isinstance(e,TimeoutError) else 'TOOL_DENIED_OR_UNAVAILABLE')
            status='UNKNOWN' if code=='OUTCOME_UNKNOWN' else 'CANCELLED' if code in ('COMPUTE_CANCELLED','RUN_CANCELLED') else 'FAILED'
            if owned:await self.lifecycle.finish(eid,call['id'],status,code)
            else:await self.record(call,eid,'tool.failed',status,code)
            if code in ('SOURCE_UNAVAILABLE','SEARCH_EMPTY','PARSE_NOT_READY','PARSE_UNSUPPORTED','CSV_NON_NUMERIC','CSV_COLUMN_NOT_FOUND','CITATION_INVALID','COMPUTE_TIMEOUT'):
                return {'role':'tool','tool_call_id':call['id'],'content':json.dumps({'error':code,'completed':False},ensure_ascii=False)}
            if status=='CANCELLED':raise asyncio.CancelledError()
            raise RunError(code) from None
