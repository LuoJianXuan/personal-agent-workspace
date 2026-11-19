"""Internal tool governance components. No deployment or second Agent loop."""
import asyncio,json,os,sys
from dataclasses import dataclass
from jsonschema import Draft202012Validator
from .access import target,run_worker,tool_access
from .models import RunError,safe_text
from .canonical import canonical
from .personal_mcp import material

@dataclass(frozen=True)
class ToolExecutionResult:
    text:str
    files:tuple=()
    def __post_init__(self):
        if len(self.text)>128*1024:raise RunError('TOOL_OUTPUT_LIMIT')

class ToolRegistry:
    def __init__(self,start):
        snapshot=start['effective_capabilities']
        self.tools={t['namespaced_tool_id']:t for t in snapshot['tools']+snapshot.get('builtin_tools',[])}
    def resolve(self,name):
        tool=self.tools.get(name)
        if not tool:raise RunError('TOOL_DENIED')
        return tool

class PolicyEngine:
    def __init__(self,engine,start):self.engine=engine;self.start=start
    async def admit(self,tool,args,eid,approval_id=None,decision_id=None):
        await self.engine.authorize(self.start)
        Draft202012Validator(tool['input_schema']).validate(args)
        raw,digest=canonical(args)
        authorized={f['id'] for f in self.start['file_refs']}
        refs=[args[k] for k in ('file_id','parent_file_id') if args.get(k)]
        refs+=args.get('file_ids',[])
        if any(f not in authorized for f in refs):raise RunError('FILE_NOT_AUTHORIZED')
        name=tool['namespaced_tool_id']
        if name in ('builtin_web_search','builtin_fetch_page') and not self.start['effective_capabilities'].get('network_enabled'):
            raise RunError('NETWORK_DISABLED')
        if name=='builtin_python' and not self.engine.compute_enabled():raise RunError('COMPUTE_NOT_CONFIGURED')
        if name=='builtin_create_demo_ticket' or tool.get('requires_approval'):
            if not approval_id or not decision_id:raise RunError('APPROVAL_REQUIRED')
            proposal=await self.engine.approvals.get(approval_id)
            if proposal['execution_id']!=eid or proposal['args_hash']!=digest:raise RunError('APPROVAL_CONFLICT')
            await self.engine.approvals.decision(decision_id,self.start,proposal)
        return raw,digest

    async def reserve(self,tool,eid):
        name=tool['namespaced_tool_id']
        if name in ('builtin_web_search','builtin_fetch_page'):
            from .research import ResearchTools,fixture_active
            if name=='builtin_web_search' and not os.getenv('TAVILY_API_KEY') and not fixture_active(self.start):
                raise RunError('SEARCH_NOT_CONFIGURED')
            await ResearchTools(self.engine,self.start).budget('search' if name=='builtin_web_search' else 'fetch',eid)

class ExecutionLifecycle:
    def __init__(self,engine,start):self.engine=engine;self.run=start['run_id']
    async def begin(self,eid,name,digest,decision_id=None,connection_id=None,max_calls_per_minute=0):
        async with self.engine.pool.connection() as c:
            async with c.transaction():
                await c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(self.run,))
                if connection_id:
                    await c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,1))',(connection_id,))
                old=await (await c.execute('SELECT status,result,request_hash FROM runtime.tool_executions WHERE execution_id=%s',(eid,))).fetchone()
                if old:
                    if old['request_hash']!=digest:raise RunError('TOOL_ARGUMENT_CONFLICT')
                    if old['status']=='SUCCEEDED':return old['result']
                    raise RunError('OUTCOME_UNKNOWN')
                n=await (await c.execute('SELECT count(*) AS n FROM runtime.tool_executions WHERE run_id=%s',(self.run,))).fetchone()
                if n['n']>=20:raise RunError('TOOL_CALL_LIMIT')
                if connection_id and max_calls_per_minute:
                    recent=await (await c.execute("SELECT count(*) AS n FROM runtime.tool_executions WHERE connection_id=%s AND created_at>now()-interval '1 minute'",(connection_id,))).fetchone()
                    if recent['n']>=max_calls_per_minute:raise RunError('MCP_RATE_LIMIT')
                await c.execute("INSERT INTO runtime.tool_executions(execution_id,run_id,status,request_hash,tool_name,decision_id,connection_id) VALUES(%s,%s,'RUNNING',%s,%s,%s,%s)",(eid,self.run,digest,name,decision_id,connection_id))
        return None
    async def finish(self,eid,call_id,status,text):
        async with self.engine.pool.connection() as c:
            async with c.transaction():
                await c.execute("UPDATE runtime.tool_executions SET status=%s,result=%s WHERE execution_id=%s AND status='RUNNING'",(status,text,eid))
                await self.engine.event_on(c,self.run,'tool.completed' if status=='SUCCEEDED' else 'tool.failed',{'execution_id':eid,'tool_call_id':call_id,'status':status,'text':safe_text(text),'file_refs':[]})

class TicketExecutor:
    async def execute(self,engine,start,tool,args,eid,raw,decision):
        try:
            r=await engine.backend.post('/internal/demo-tickets',json={'run_id':start['run_id'],'execution_id':eid,'decision_id':decision,'canonical_args':raw,'args_hash':canonical(args)[1]})
            if 400<=r.status_code<500:raise RunError(r.json().get('code','TOOL_DENIED'))
            if r.status_code!=200:raise RuntimeError()
            result=r.json()
        except RunError:raise
        except Exception:
            try:
                r=await engine.backend.get('/internal/demo-tickets/by-execution/'+eid)
                if r.status_code!=200:raise RunError('OUTCOME_UNKNOWN')
                result=r.json()
            except Exception:raise RunError('OUTCOME_UNKNOWN') from None
        await engine.approvals.fault(start['run_id'],'after_ticket_commit')
        return ToolExecutionResult(json.dumps(result,ensure_ascii=False))

class BuiltinExecutor:
    async def execute(self,engine,start,tool,args,eid,raw,decision):
        name=tool['namespaced_tool_id']
        if name in ('builtin_web_search','builtin_fetch_page'):
            from .research import ResearchTools
            text=await ResearchTools(engine,start).execute(name,args,eid)
        else:
            from .materials import MaterialTools
            text=await MaterialTools(engine,start).execute(name,args,eid)
        return ToolExecutionResult(text)

class McpExecutor:
    async def execute(self,engine,start,tool,args,eid,raw,decision):
        connection=next((c for c in start['effective_capabilities']['mcp_connections'] if c['id']==tool.get('connection_id')),None)
        if not connection:raise RunError('TOOL_DENIED')
        private = bool(connection.get("connector_id"))
        item=target('mcp',connection['endpoint'],connection['credential_ref'],personal=private)
        mode,requires_approval=tool_access(item,tool['remote_name'],personal=private)
        if mode=='blocked' or mode!=tool.get('access_mode') or requires_approval!=bool(tool.get('requires_approval')):raise RunError('TOOL_DENIED')
        payload = {'endpoint':connection['endpoint'],'credential_ref':connection['credential_ref'],'name':tool['remote_name'],'arguments':args,'access_mode':mode,'requires_approval':requires_approval}
        binding = {"run_id": start["run_id"], "execution_id": eid, "tool_id": tool["namespaced_tool_id"], "args_hash": canonical(args)[1]}
        if private:
            if decision:
                binding["decision_id"] = decision
            secret = await material(engine, "execution", binding)
            if any(secret[key] != payload[key] for key in ("endpoint", "credential_ref")):
                raise RunError("TOOL_DENIED")
            payload["token"] = secret["token"]
        try:
            result = await run_worker(payload, command=[sys.executable, '-m', 'app.tool_worker'], deadline=20, private=private)
        except (TimeoutError, ValueError, OSError):
            if private and requires_approval:
                raise RunError("OUTCOME_UNKNOWN") from None
            raise
        code = result.get("error")
        if code == "CONNECTION_AUTH_REQUIRED":
            try:
                await material(engine, "execution", {**binding, "auth_failed": True})
            except RunError:
                pass
            raise RunError(code)
        if code:
            raise RunError(code if code in ("MCP_UNAVAILABLE", "OUTCOME_UNKNOWN") else "MCP_UNAVAILABLE")
        return ToolExecutionResult(result['text'])

class ExecutionRouter:
    def __init__(self):
        self.ticket=TicketExecutor();self.builtin=BuiltinExecutor();self.mcp=McpExecutor()
    async def dispatch(self,engine,start,tool,args,eid,raw,decision):
        name=tool['namespaced_tool_id']
        executor=self.ticket if name=='builtin_create_demo_ticket' else self.builtin if name.startswith('builtin_') else self.mcp
        return await executor.execute(engine,start,tool,args,eid,raw,decision)
