"""Authorized user-facing Harness → isolated Python → artifact/cancel acceptance."""
import importlib.util,json,time,urllib.request,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('phase',ROOT/'scripts/accept-phase1.py');phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
d=phase.base;req=d.request
def main():
 token=phase.login('user-a')
 source=phase.upload(token,'compute-input.csv',b'group,value\nA,4\nA,9\n')
 run,state=phase.run(token,'mock:python',[source['id']]);assert state['status']=='SUCCEEDED',state
 files=req('/runs/'+run+'/artifacts',token=token)['items'];result=next(f for f in files if f['name']=='result.csv')
 assert req('/files/'+result['id']+'/content',token=token)['text'].splitlines()==['group,total','A,13']
 print('PASS Harness → governed Python → real offline container → stored CSV',flush=True)
 thread=req('/threads','POST',{'title':'Compute cancellation '+uuid.uuid4().hex[:8]},token,201)['id']
 request=urllib.request.Request(d.BASE+'/threads/'+thread+'/runs',data=json.dumps({'input':'mock:python-cancel','skill_ids':[],'file_ids':[source['id']]}).encode(),method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())})
 with urllib.request.urlopen(request,timeout=20) as response:pending=json.load(response)['run_id']
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  if d.sql("SELECT count(*) FROM runtime.tool_executions WHERE run_id='"+pending+"' AND tool_name='builtin_python' AND status='RUNNING';")=='1':break
  time.sleep(.2)
 else:raise AssertionError('Python tool did not start')
 req('/runs/'+pending+'/cancel','POST',{},token,202)
 deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  state=req('/runs/'+pending,token=token)
  if state['status']=='CANCELLED':break
  time.sleep(.2)
 else:raise AssertionError('Compute run did not cancel')
 assert not req('/runs/'+pending+'/artifacts',token=token)['items']
 print('PASS API cancellation reaches active Python tool and publishes no artifact',flush=True)
 output={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'checks':['harness_compute_artifact','api_compute_cancel'],'run_id':run,'cancelled_run_id':pending,'real_model_calls':0,'real_search_calls':0}
 (ROOT/'docs/evidence/phase1-compute-flow-results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
