import asyncio,json,sys
from uuid import uuid5,UUID
from jsonschema import Draft202012Validator
from .access import target,run_worker
from .models import RunError,safe_text
from .canonical import canonical
from .approvals import FaultPause

class ToolGatewayService:
    def __init__(self,engine,start):self.engine=engine;self.start=start
    def find(self,call):return next((t for t in self.start['effective_capabilities']['tools']+self.start['effective_capabilities'].get('builtin_tools',[]) if t['namespaced_tool_id']==call['function']['name']),None)
    async def filesystem(self,request,handler):
        from langchain_core.messages import ToolMessage
        native=request.tool_call;run=self.start['run_id'];eid=str(uuid5(UUID(run),native['id']))
        await self.engine.authorize(self.start)
        raw,digest=canonical(native['args'])
        async with self.engine.pool.connection() as c:
            old=await (await c.execute('SELECT status,result,request_hash FROM runtime.tool_executions WHERE execution_id=%s',(eid,))).fetchone()
            if old:
                if old['request_hash']!=digest:raise RunError('TOOL_ARGUMENT_CONFLICT')
                if old['status']=='SUCCEEDED':return ToolMessage(content=old['result'],tool_call_id=native['id'])
                raise RunError('OUTCOME_UNKNOWN')
            await c.execute("INSERT INTO runtime.tool_executions(execution_id,run_id,status,request_hash,tool_name) VALUES(%s,%s,'RUNNING',%s,%s)",(eid,run,digest,native['name']))
        payload={'execution_id':eid,'tool_call_id':native['id'],'status':'RUNNING','text':native['name'],'file_refs':[]}
        await self.engine.event(run,'tool.started',payload)
        try:
            result=await handler(request);text=safe_text(str(getattr(result,'content','文件操作已完成')))
            failed=getattr(result,'status','success')=='error';status='FAILED' if failed else 'SUCCEEDED'
            async with self.engine.pool.connection() as c:await c.execute("UPDATE runtime.tool_executions SET status=%s,result=%s WHERE execution_id=%s",(status,text,eid))
            await self.engine.event(run,'tool.failed' if failed else 'tool.completed',{**payload,'status':status,'text':text[:12000]})
            return result
        except BaseException:
            async with self.engine.pool.connection() as c:await c.execute("UPDATE runtime.tool_executions SET status='UNKNOWN' WHERE execution_id=%s",(eid,))
            await self.engine.event(run,'tool.failed',{**payload,'status':'UNKNOWN','text':'FILE_EXECUTION_INTERRUPTED'});raise
    async def execute(self,call,decision_id=None,approval_id=None):
        snap=self.start['effective_capabilities'];run=self.start['run_id'];name=call['function']['name']
        eid=str(uuid5(UUID(run),call['id']));tool=self.find(call)
        async def record(kind,status,text,files=None):
            payload={'execution_id':eid,'tool_call_id':call['id'],'status':status,'text':safe_text(text),'file_refs':files or []}
            await self.engine.event(run,kind,payload)
        await record('tool.requested','REQUESTED',name)
        try:
            await self.engine.authorize(self.start)
            if not tool:raise RunError('TOOL_DENIED')
            args=json.loads(call['function']['arguments']);Draft202012Validator(tool['input_schema']).validate(args)
            raw,hash=canonical(args)
            if name=='builtin_create_demo_ticket':
                if not approval_id or not decision_id:raise RunError('APPROVAL_REQUIRED')
                proposal=await self.engine.approvals.get(approval_id)
                if proposal['execution_id']!=eid or proposal['args_hash']!=hash:raise RunError('APPROVAL_CONFLICT')
                await self.engine.approvals.decision(decision_id,self.start,proposal)
            async with self.engine.pool.connection() as conn:
                old=await (await conn.execute('SELECT status,result,request_hash FROM runtime.tool_executions WHERE execution_id=%s',(eid,))).fetchone()
                if old:
                    if old['request_hash']!=hash:raise RunError('TOOL_ARGUMENT_CONFLICT')
                    if old['status']=='SUCCEEDED':return {'role':'tool','tool_call_id':call['id'],'content':old['result']}
                    raise RunError('OUTCOME_UNKNOWN')
                await conn.execute("INSERT INTO runtime.tool_executions(execution_id,run_id,status,request_hash,tool_name,decision_id) VALUES(%s,%s,'RUNNING',%s,%s,%s)",(eid,run,hash,name,decision_id))
            await record('tool.started','RUNNING',name)
            if name=='builtin_create_demo_ticket':
                try:
                    response=await self.engine.backend.post('/internal/demo-tickets',json={'run_id':run,'execution_id':eid,'decision_id':decision_id,'canonical_args':raw,'args_hash':hash})
                    if 400<=response.status_code<500:raise RunError(response.json().get('code','TOOL_DENIED'))
                    if response.status_code!=200:raise RuntimeError('uncertain response')
                    result=response.json()
                except RunError:raise
                except Exception:
                    try:
                        check=await self.engine.backend.get('/internal/demo-tickets/by-execution/'+eid)
                        if check.status_code!=200:raise RunError('OUTCOME_UNKNOWN')
                        result=check.json()
                    except Exception:raise RunError('OUTCOME_UNKNOWN') from None
                await self.engine.approvals.fault(run,'after_ticket_commit')
                text=json.dumps(result,ensure_ascii=False)
            elif name in ('builtin_read_material','builtin_csv_summary','builtin_publish_report','builtin_python'):
                from .materials import MaterialTools
                text=await MaterialTools(self.engine,self.start).execute(name,args,eid)
            elif name in ('builtin_web_search','builtin_fetch_page'):
                from .research import ResearchTools
                text=await ResearchTools(self.engine,self.start).execute(name,args,eid)
            else:
                connection=next(c for c in snap['mcp_connections'] if c['id']==tool['connection_id'])
                item=target('mcp',connection['endpoint'],connection['credential_ref'])
                if tool['remote_name'] not in item.get('read_only_tools',[]):raise RunError('TOOL_DENIED')
                result=await run_worker({'endpoint':connection['endpoint'],'credential_ref':connection['credential_ref'],'name':tool['remote_name'],'arguments':args},command=[sys.executable,'-m','app.tool_worker'],deadline=20)
                text=result['text']
            text=safe_text(text)
            async with self.engine.pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute("UPDATE runtime.tool_executions SET status='SUCCEEDED',result=%s WHERE execution_id=%s",(text,eid))
                    await self.engine.event_on(conn,run,'tool.completed',{'execution_id':eid,'tool_call_id':call['id'],'status':'SUCCEEDED','text':text,'file_refs':[]})
            return {'role':'tool','tool_call_id':call['id'],'content':text}
        except asyncio.CancelledError:
            async with self.engine.pool.connection() as conn:
                await conn.execute("UPDATE runtime.tool_executions SET status='UNKNOWN' WHERE execution_id=%s AND status='RUNNING'",(eid,))
            await record('tool.failed','UNKNOWN','TOOL_EXECUTION_INTERRUPTED')
            raise
        except FaultPause:raise
        except Exception as e:
            code=e.code if isinstance(e,RunError) else ('TOOL_TIMEOUT' if isinstance(e,TimeoutError) else 'TOOL_DENIED_OR_UNAVAILABLE')
            status='UNKNOWN' if code=='OUTCOME_UNKNOWN' else 'FAILED'
            async with self.engine.pool.connection() as conn:
                await conn.execute("UPDATE runtime.tool_executions SET status=%s WHERE execution_id=%s AND status='RUNNING'",(status,eid))
            await record('tool.failed',status,code)
            if code in ('SOURCE_UNAVAILABLE','SEARCH_EMPTY','PARSE_NOT_READY','PARSE_UNSUPPORTED','CSV_NON_NUMERIC','CSV_COLUMN_NOT_FOUND','CITATION_INVALID','COMPUTE_TIMEOUT'):
                return {'role':'tool','tool_call_id':call['id'],'content':json.dumps({'error':code,'completed':False},ensure_ascii=False)}
            raise RunError(code) from None
