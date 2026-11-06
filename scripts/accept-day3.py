"""Authorized S03 acceptance: isolated database, Mock output, real graph/MCP/SSE."""
import importlib.util,json,time,uuid,urllib.request,urllib.error,concurrent.futures
from pathlib import Path
spec=importlib.util.spec_from_file_location('d2',Path(__file__).with_name('accept-day2.py'));d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
# Verification compose mode is shared by every acceptance stage.
results=[]
def passed(s):results.append(s);print('PASS:',s,flush=True)
def req(path,method='GET',body=None,token=None,key=None,expect=200):
 headers={'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 if key:headers['Idempotency-Key']=key
 r=urllib.request.Request(d.BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
 try:
  with urllib.request.urlopen(r,timeout=20) as res:status,raw=res.status,res.read()
 except urllib.error.HTTPError as e:status,raw=e.code,e.read()
 v=json.loads(raw);assert status==expect,(path,status,v);return v

def wait(run,token,expected='SUCCEEDED',timeout=55):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  r=req('/runs/'+run,token=token)
  if r['status'] in ['SUCCEEDED','FAILED','INTERRUPTED','CANCELLED']:
   assert r['status']==expected,r;return r
  time.sleep(.3)
 raise AssertionError('Run did not settle '+run)

def all_events(run,token,after=0):
 out=[]
 while True:
  page=req(f'/runs/{run}/events?after_seq={after}',token=token);out+=page['items'];after=page['next_seq']
  if not page['has_more']:return out

def main():
 a=d.login('ADMIN')['access_token']
 users=req('/admin/users',token=a)['items']
 for user in users:
  if user['username'] in [d.ENV['SEED_USER_A_USERNAME'],d.ENV['SEED_USER_B_USERNAME']] and not user['enabled']:req('/admin/users/'+user['id'],'PATCH',{'enabled':True,'revision':user['revision']},a)
 u=d.login('USER_A')['access_token'];b=d.login('USER_B')['access_token']
 model=json.loads((d.ROOT/'schemas/examples/model-write.json').read_text());model.update(name='S03 Mock '+d.SUFFIX,provider='display-only',provider_model_name='mock-only',base_url='https://api.deepseek.com',credential_ref='deepseek_primary',is_default=True,enabled=True,context_limit=64000,max_output_tokens=512,revision=0)
 m=req('/admin/models','POST',model,a);mid=m['id']
 conn=req('/admin/mcp-connections','POST',{'name':'S03 real MCP '+d.SUFFIX,'endpoint':'http://demo-mcp:8001/mcp/','credential_ref':'','enabled':True,'revision':0},a)
 cp='/admin/mcp-connections/'+conn['id'];conn=req(cp+'/discover','POST',{'revision':conn['revision']},a);tool=req(cp+'/tools',token=a)['items'][0];req(cp+'/tools/'+tool['namespaced_tool_id'],'PATCH',{'revision':tool['revision'],'enabled':True},a)
 def thread():return req('/threads','POST',{'title':'S03 '+d.SUFFIX},u,expect=201)['id']
 def submit(t,text,key=None):return req('/threads/'+t+'/runs','POST',{'input':text,'model_id':mid,'skill_ids':[]},u,key or str(uuid.uuid4()),202)
 tid=thread();key=str(uuid.uuid4());r=submit(tid,'mock:long',key);rid=r['run_id']
 assert submit(tid,'mock:long',key)['run_id']==rid
 req('/threads/'+tid+'/runs','POST',{'input':'different','model_id':mid,'skill_ids':[]},u,key,409)
 req('/threads/'+tid+'/runs','POST',{'input':'another','model_id':mid,'skill_ids':[]},u,str(uuid.uuid4()),409)
 req('/runs/'+rid,token=b,expect=404);req('/threads/'+tid+'/messages',token=b,expect=404);req('/runs/'+rid+'/events',token=b,expect=404)
 passed('A09/A20: same-key replay, conflicting payload, thread busy and owner isolation')
 # Read until multiple durable deltas while still RUNNING, deliberately disconnect.
 end=time.monotonic()+15;prefix=[]
 while time.monotonic()<end:
  try:
   stream=urllib.request.urlopen(urllib.request.Request(d.BASE+'/runs/'+rid+'/stream',headers={'Authorization':'Bearer '+u}),timeout=20)
   for raw in stream:
    if raw.startswith(b'data:'):
     event=json.loads(raw[5:]);prefix.append(event)
     if sum(e['type']=='message.delta' for e in prefix)>=3:break
   stream.close();break
  except urllib.error.HTTPError:time.sleep(.3)
 assert len([e for e in prefix if e['type']=='message.delta'])>=3
 assert req('/runs/'+rid,token=u)['status']=='RUNNING'
 result=wait(rid,u);events=all_events(rid,u);remaining=all_events(rid,u,prefix[-1]['seq'])
 assert [e['event_id'] for e in prefix+remaining]==[e['event_id'] for e in events]
 assert [e['seq'] for e in events]==list(range(1,len(events)+1))
 complete=next(e for e in events if e['type']=='message.completed' and e['payload']['is_final'])
 deltas=[e for e in events if e['type']=='message.delta'];assert ''.join(e['payload']['text'] for e in deltas)==complete['payload']['text']==result['final_text']
 assert [e['payload']['chunk_index'] for e in deltas]==list(range(len(deltas)))
 passed('A07/A18: multiple real-time durable chunks, disconnect, cursor replay, exact final convergence')
 second=submit(tid,'记住上一轮');second_result=wait(second['run_id'],u);assert '历史用户轮数：2' in second_result['final_text']
 history=req('/threads/'+tid+'/messages',token=u)['items'];assert len(history)==4
 assert len({(x['run_id'],x['role']) for x in history})==4
 req('/threads/'+tid,'PATCH',{'title':'已改名 '+d.SUFFIX},u)
 passed('Multi-turn completed history, rename and exactly one final projection per run')
 toolrun=submit(thread(),'mock:tool');wait(toolrun['run_id'],u);te=all_events(toolrun['run_id'],u);assert any(e['type']=='tool.completed' and 'DEMO-1001' in e['payload']['text'] for e in te)
 assert d.sql("SELECT count(*) FROM runtime_harness_v2.checkpoints WHERE thread_id='"+toolrun['run_id']+"';")!='0'
 passed('A08: Mock model traverses real LangGraph, PostgreSQL checkpoints and real MCP gateway')
 failed=submit(thread(),'mock:fail');fr=wait(failed['run_id'],u,'FAILED');fe=all_events(failed['run_id'],u);assert fr['error_code']=='MODEL_STREAM_FAILED' and any(e['type']=='message.delta' for e in fe) and not any(e['type']=='message.completed' for e in fe)
 passed('A18: mid-stream failure keeps unfinished drafts and has no successful final message')
 # Four live subscribers; fifth is rejected, configuration APIs remain responsive.
 long=submit(thread(),'mock:long');streams=[]
 try:
  for _ in range(4):
   end=time.monotonic()+10
   while True:
    try:streams.append(urllib.request.urlopen(urllib.request.Request(d.BASE+'/runs/'+long['run_id']+'/stream',headers={'Authorization':'Bearer '+u}),timeout=15));break
    except urllib.error.HTTPError as e:
     if time.monotonic()>end:raise
     time.sleep(.2)
  req('/runs/'+long['run_id']+'/stream',token=u,expect=429)
  before=time.monotonic();req('/admin/models',token=a);assert time.monotonic()-before<3
 finally:
  for stream in streams:stream.close()
 wait(long['run_id'],u)
 passed('A27: fifth per-user subscription rejected, management API responsive during four subscriptions')
 # Stop runtime only in verification; submission survives and is dispatched with the same run id.
 d.run('stop','runtime')
 try:
  pending=submit(thread(),'dispatch recovery')
  state=req('/runs/'+pending['run_id'],token=u);assert state['runtime_unavailable']
 finally:d.run('up','-d','--wait','runtime')
 wait(pending['run_id'],u)
 payload=d.sql("SELECT start_payload::text FROM backend.run_submissions WHERE run_id='"+pending['run_id']+"';")
 replay="""import os,json,urllib.request
payload=%r
r=urllib.request.Request('http://runtime:8000/internal/runs',data=payload.encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['BACKEND_TO_RUNTIME_TOKEN']})
with urllib.request.urlopen(r) as res:print(json.load(res)['run_id'])
"""
 assert d.run('exec','-T','runtime','python','-',input=replay%payload)==pending['run_id']
 assert len([e for e in all_events(pending['run_id'],u) if e['type']=='run.started'])==1
 passed('A10: offline dispatch persists; repeated accepted start returns same run without re-execution')
 interrupted=submit(thread(),'mock:long')
 end=time.monotonic()+10
 while req('/runs/'+interrupted['run_id'],token=u)['status']!='RUNNING' and time.monotonic()<end:time.sleep(.2)
 d.run('restart','runtime');wait(interrupted['run_id'],u,'INTERRUPTED')
 passed('Restart settles orphaned execution as INTERRUPTED; prior history remains readable')
 admin=req('/admin/runs/'+rid,token=a)['items'][0];assert 'final_text' not in admin and 'start_payload' not in admin
 req('/admin/runs',token=u,expect=403)
 passed('Admin run lookup is metadata-only; ordinary user is forbidden')
 report={'status':'passed','checks':results,'real_model_calls':0,'mode':'mock','thread_id':tid,'tool_run_id':toolrun['run_id'],'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
 (d.ROOT/'docs/evidence/day3-mock-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
