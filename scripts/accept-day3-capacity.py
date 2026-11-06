"""Run with verification Runtime stopped: exercises the real admission store without model calls."""
import asyncio,json,os,copy
from uuid import uuid4
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from app.engine import Engine
from app.models import RunError
async def main():
 payload=json.loads(input());ids=[];resume=payload.pop('_capacity_resume',None)
 pool=AsyncConnectionPool(os.environ['RUNTIME_DATABASE_URL'],min_size=1,max_size=4,timeout=3,open=False,kwargs={'autocommit':True,'row_factory':dict_row,'options':'-c search_path=runtime -c statement_timeout=3000'});await pool.open(wait=True,timeout=10)
 checkpoints=AsyncConnectionPool(os.environ['RUNTIME_DATABASE_URL'],min_size=1,max_size=4,timeout=3,open=False,kwargs={'autocommit':True,'row_factory':dict_row,'options':'-c search_path=runtime_harness_v2 -c statement_timeout=3000'});await checkpoints.open(wait=True,timeout=10);engine=Engine(pool,checkpoints)
 try:
  for _ in range(32):
   p=copy.deepcopy(payload);p['run_id']=str(uuid4());ids.append(p['run_id']);await engine.accept(p)
   if len(ids)==1:first=p
  assert (await engine.accept(first))['run_id']==first['run_id']
  bad=copy.deepcopy(first);bad['input']='changed'
  try:await engine.accept(bad);raise AssertionError('conflicting replay admitted')
  except RunError as e:assert e.code=='IDEMPOTENCY_CONFLICT'
  real=copy.deepcopy(first);real['run_id']=str(uuid4());real['mode']='real'
  try:await engine.accept(real);raise AssertionError('mock-only Runtime accepted real mode')
  except RunError as e:assert e.code=='REAL_MODEL_DISABLED'
  new=copy.deepcopy(first);new['run_id']=str(uuid4())
  try:await engine.accept(new);raise AssertionError('over-capacity admitted')
  except RunError as e:assert e.code=='RESOURCE_EXHAUSTED'
  async with pool.connection() as c:
   row=await (await c.execute('SELECT count(*) AS n FROM runtime.runs WHERE run_id=%s',(new['run_id'],))).fetchone();assert row['n']==0
  if resume:
   try:await engine.approvals.resume(resume['run_id'],resume['decision_id']);raise AssertionError('full queue resumed approval')
   except RunError as e:assert e.code=='RESOURCE_EXHAUSTED',e.code
   assert (await engine.get(resume['run_id']))['status']=='WAITING_APPROVAL'
   assert await engine.approvals.waiting_evidence(payload) is not None
  print('PASS: 32 queued admission limit; existing replay before capacity; conflicting replay; rejected run not inserted')
 finally:
  async with pool.connection() as c:await c.execute('DELETE FROM runtime.runs WHERE run_id=ANY(%s::uuid[])',(ids,))
  await engine.close();await checkpoints.close();await pool.close()
asyncio.run(asyncio.wait_for(main(),90))
