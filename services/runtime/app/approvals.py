import asyncio,json,os
from datetime import datetime,timezone,timedelta
from uuid import UUID,uuid5
from psycopg.types.json import Jsonb
from contracts.validate import validate
from .canonical import canonical
from .models import RunError

class FaultPause(Exception):pass
class ApprovalService:
    def __init__(self,engine):self.engine=engine
    async def fault(self,run,name):
        if os.getenv('ENABLE_FAULTS')!='true' or os.getenv('FAULT_'+name.upper())!='true':return
        async with self.engine.pool.connection() as conn:
            row=await (await conn.execute('INSERT INTO runtime.faults(run_id,name) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING name',(run,name))).fetchone()
        if row:raise FaultPause(name)
    async def get(self,id):
        async with self.engine.pool.connection() as c:r=await (await c.execute('SELECT proposal,status FROM runtime.approvals WHERE approval_id=%s',(id,))).fetchone()
        if not r:raise RunError('NOT_FOUND')
        return {**r['proposal'],'status':r['status']}
    async def get_published(self,id):
        async with self.engine.pool.connection() as c:r=await (await c.execute('SELECT published FROM runtime.approvals WHERE approval_id=%s',(id,))).fetchone()
        if not r or not r['published']:raise RunError('NOT_FOUND')
        return await self.get(id)
    async def list(self,run):
        async with self.engine.pool.connection() as c:rows=await (await c.execute('SELECT proposal,status FROM runtime.approvals WHERE run_id=%s AND published ORDER BY approval_id',(run,))).fetchall()
        return {'items':[{**r['proposal'],'status':r['status']} for r in rows]}
    async def prepare(self,start,call,tool):
        args=json.loads(call['function']['arguments']);validate('TicketArgs',args)
        raw,digest=canonical(args);eid=str(uuid5(UUID(start['run_id']),call['id']));aid=str(uuid5(UUID(eid),'approval'))
        ttl=600
        if os.getenv('ENABLE_FAULTS')=='true':ttl=max(2,min(600,int(os.getenv('APPROVAL_TTL_SECONDS','600'))))
        proposal={'approval_id':aid,'execution_id':eid,'run_id':start['run_id'],'tool_call_id':call['id'],'namespaced_tool_id':tool['namespaced_tool_id'],'canonical_args':raw,'args_hash':digest,'capability_revision':tool['revision'],'snapshot_id':start['effective_capabilities']['snapshot_id'],'owner_id':start['context']['user_id'],'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=ttl)).isoformat(),'status':'PENDING'}
        validate('Approval',proposal)
        async with self.engine.pool.connection() as c:
            await c.execute("INSERT INTO runtime.approvals(approval_id,run_id,execution_id,proposal) VALUES(%s,%s,%s,%s) ON CONFLICT(approval_id) DO NOTHING",(aid,start['run_id'],eid,Jsonb(proposal)))
        saved=await self.get(aid)
        if saved['args_hash']!=digest:raise RunError('APPROVAL_CONFLICT')
        return aid
    async def waiting_evidence(self,start):
        from .harness import HarnessDriver
        from langchain_core.messages import AIMessage
        async with HarnessDriver(self.engine,start) as driver:
            state=await driver.graph.aget_state({'configurable':{'thread_id':start['run_id']}})
        pending=[i.value for task in state.tasks for i in task.interrupts if isinstance(i.value,dict)]
        actions=[action for payload in pending for action in payload.get('action_requests',[])]
        if len(actions)!=1 or actions[0]['name']!='builtin_create_demo_ticket':return None
        action=actions[0]
        message=next((m for m in reversed(state.values.get('messages',[])) if isinstance(m,AIMessage) and m.tool_calls),None)
        if message is None:return None
        calls=[c for c in message.tool_calls if c['name']==action['name'] and c['args']==action['args']]
        if len(calls)!=1:return None
        native=calls[0]
        call={'id':native['id'],'function':{'name':native['name'],'arguments':json.dumps(native['args'],ensure_ascii=False)}}
        tool=next((t for t in start['effective_capabilities'].get('builtin_tools',[]) if t['namespaced_tool_id']==native['name']),None)
        if not tool:return None
        aid=await self.prepare(start,call,tool)
        p=await self.get(aid)
        async with self.engine.pool.connection() as c:
            executed=await (await c.execute('SELECT status FROM runtime.tool_executions WHERE execution_id=%s',(p['execution_id'],))).fetchone()
        return None if executed else p
    async def execution_binding(self,start,call):
        if call['function']['name']!='builtin_create_demo_ticket':return None,None
        eid=str(uuid5(UUID(start['run_id']),call['id']));aid=str(uuid5(UUID(eid),'approval'))
        proposal=await self.get(aid)
        async with self.engine.pool.connection() as c:
            row=await (await c.execute('SELECT resume_decision FROM runtime.runs WHERE run_id=%s',(start['run_id'],))).fetchone()
        if not row or not row['resume_decision']:raise RunError('APPROVAL_REQUIRED')
        decision=str(row['resume_decision']);await self.decision(decision,start,proposal)
        return aid,decision
    async def publish_wait(self,start,p):
        run=start['run_id']
        async with self.engine.pool.connection() as c:
            async with c.transaction():
                row=await (await c.execute("UPDATE runtime.runs SET status='WAITING_APPROVAL' WHERE run_id=%s AND status IN ('RUNNING','QUEUED','WAITING_APPROVAL') AND NOT cancel_requested RETURNING run_id",(run,))).fetchone()
                if not row:return
                changed=await (await c.execute('UPDATE runtime.approvals SET published=true WHERE approval_id=%s AND NOT published RETURNING approval_id',(p['approval_id'],))).fetchone()
                if changed:await self.engine.event_on(c,run,'approval.required',p)
    async def decision(self,id,start,p):
        response=await self.engine.backend.get('/internal/approval-decisions/'+id)
        if response.status_code!=200:raise RunError('APPROVAL_DECISION_UNAVAILABLE')
        d=response.json();validate('DecisionRecord',d)
        if d['run_id']!=start['run_id'] or d['owner_id']!=start['context']['user_id'] or d['approval_id']!=p['approval_id']:raise RunError('APPROVAL_CONFLICT')
        for key in ('args_hash','canonical_args','execution_id','snapshot_id','capability_revision','expires_at'):
            if d['proposal'][key]!=p[key]:raise RunError('APPROVAL_CONFLICT')
        if datetime.now(timezone.utc)>=datetime.fromisoformat(p['expires_at']):raise RunError('APPROVAL_EXPIRED')
        await self.engine.authorize(start)
        if d['decision']=='reject':raise RunError('APPROVAL_REJECTED')
        return d
    async def resume(self,run,decision_id):
        async with self.engine.pool.connection() as c:row=await (await c.execute('SELECT * FROM runtime.runs WHERE run_id=%s',(run,))).fetchone()
        if not row:raise RunError('NOT_FOUND')
        if str(row['resume_decision'])==decision_id and row['status'] in ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED'):return await self.engine.get(run)
        if row['status']!='WAITING_APPROVAL':raise RunError('RUN_NOT_RESUMABLE')
        start=row['start_payload'];p=await self.waiting_evidence(start)
        if not p:raise RunError('RUN_NOT_RESUMABLE')
        try:await self.decision(decision_id,start,p)
        except RunError as e:
            if e.code in ('APPROVAL_REJECTED','APPROVAL_EXPIRED','CAPABILITY_CHANGED','RUN_CANCELLED','USER_DISABLED','RUN_NOT_AUTHORIZED'):
                state='CANCELLED' if e.code in ('APPROVAL_REJECTED','RUN_CANCELLED') else 'FAILED'
                async with self.engine.pool.connection() as c:await c.execute('UPDATE runtime.approvals SET status=%s,decision_id=%s WHERE approval_id=%s',('REJECTED' if e.code=='APPROVAL_REJECTED' else 'EXPIRED' if e.code=='APPROVAL_EXPIRED' else 'CANCELLED',decision_id,p['approval_id']))
                await self.engine.finish(run,state,e.code)
                return await self.engine.get(run)
            raise
        async with self.engine.pool.connection() as c:
            async with c.transaction():
                await c.execute('SELECT pg_advisory_xact_lock(310003)')
                current=await (await c.execute('SELECT status,resume_decision,cancel_requested FROM runtime.runs WHERE run_id=%s FOR UPDATE',(run,))).fetchone()
                if current['cancel_requested']:raise RunError('RUN_CANCELLED')
                if current['status']!='WAITING_APPROVAL':return await self.engine.get(run)
                n=await (await c.execute("SELECT count(*) AS n FROM runtime.runs WHERE status='QUEUED'")).fetchone()
                if n['n']>=32:raise RunError('RESOURCE_EXHAUSTED')
                await c.execute("UPDATE runtime.runs SET status='QUEUED',resume_decision=%s,resumed_approval=%s WHERE run_id=%s",(decision_id,p['approval_id'],run))
                await c.execute("UPDATE runtime.approvals SET status='APPROVED',decision_id=%s WHERE approval_id=%s",(decision_id,p['approval_id']))
                await self.engine.event_on(c,run,'approval.resolved',{'status':'APPROVED','object_id':p['approval_id']})
        return await self.engine.get(run)
    async def sweep(self):
        while True:
            try:
                async with self.engine.pool.connection() as c:rows=await (await c.execute("SELECT start_payload,resume_decision,resumed_approval FROM runtime.runs WHERE status='WAITING_APPROVAL'")).fetchall()
                for row in rows:
                    start=row['start_payload'];p=await self.waiting_evidence(start)
                    if not p:await self.engine.finish(start['run_id'],'INTERRUPTED','WAIT_CHECKPOINT_MISSING');continue
                    if row['resume_decision'] and str(row['resumed_approval'])==p['approval_id'] and p['status']=='APPROVED':
                        await self.resume(start['run_id'],str(row['resume_decision']));continue
                    if datetime.now(timezone.utc)>=datetime.fromisoformat(p['expires_at']):
                        async with self.engine.pool.connection() as c:await c.execute("UPDATE runtime.approvals SET status='EXPIRED' WHERE approval_id=%s AND status='PENDING'",(p['approval_id'],))
                        await self.engine.finish(start['run_id'],'FAILED','APPROVAL_EXPIRED');continue
                    try:await self.engine.authorize(start)
                    except RunError as e:
                        if e.code!='CAPABILITY_CHECK_UNAVAILABLE':await self.engine.finish(start['run_id'],'CANCELLED' if e.code=='RUN_CANCELLED' else 'FAILED',e.code)
            except asyncio.CancelledError:raise
            except Exception:pass
            await asyncio.sleep(1)
