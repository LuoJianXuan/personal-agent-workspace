"""Pipe into a Mock verification Runtime one-off with its normal service stopped."""
import asyncio,copy,json,os
from uuid import uuid4
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from app.migrate import main as migrate

assert os.environ.get('MODEL_MODE')=='mock' and os.environ.get('WORKSPACE_PHASE1_AUTHORIZED')=='true'
async def main():
 run=str(uuid4())
 async with await AsyncConnection.connect(os.environ['RUNTIME_DATABASE_URL'],autocommit=True,row_factory=dict_row) as conn:
  row=await (await conn.execute("SELECT count(*) AS n FROM runtime.runs WHERE status IN ('QUEUED','RUNNING','WAITING_APPROVAL')")).fetchone()
  assert row['n']==0,'Migration acceptance requires a drained verification environment'
  saved=await (await conn.execute("SELECT start_payload FROM runtime.runs WHERE status='SUCCEEDED' AND mode='mock' ORDER BY created_at DESC LIMIT 1")).fetchone()
  assert saved,'Run ordinary Mock acceptance first'
  before=await (await conn.execute('SELECT count(*) AS n FROM runtime_harness_v2.checkpoints')).fetchone()
  payload=copy.deepcopy(saved['start_payload']);payload['run_id']=run
  try:
   await conn.execute("INSERT INTO runtime.runs(run_id,thread_id,request_hash,start_payload,status,mode,engine_version) VALUES(%s,%s,'migration-fixture',%s,'QUEUED','mock','legacy')",(run,payload['thread_id'],Jsonb(payload)))
   try:await migrate();raise AssertionError('Migration admitted a legacy active run')
   except RuntimeError as error:assert 'MIGRATION_PENDING_RUNS' in str(error)
  finally:await conn.execute('DELETE FROM runtime.runs WHERE run_id=%s',(run,))
  await migrate()
  after=await (await conn.execute('SELECT count(*) AS n FROM runtime_harness_v2.checkpoints')).fetchone()
  version=await (await conn.execute('SELECT max(version) AS v FROM runtime.schema_migrations')).fetchone()
  assert before['n']==after['n'] and version['v']==6
  print(json.dumps({'checks':['legacy active run rejects migration','drained v6 migration is repeatable','existing new checkpoint rows are preserved'],'checkpoint_rows_preserved':after['n'],'real_model_calls':0,'real_search_calls':0}))
asyncio.run(asyncio.wait_for(main(),90))
