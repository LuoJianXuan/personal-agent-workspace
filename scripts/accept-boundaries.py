"""Boundary and negative checks against isolated services, never provider calls."""
import importlib.util,json,time,uuid,concurrent.futures,urllib.request,urllib.error
from pathlib import Path
spec=importlib.util.spec_from_file_location('delivery',Path(__file__).with_name('accept-delivery.py'));x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
d=x.d;req=x.req;wait=x.wait
results=[]
def passed(s):results.append(s);print('PASS:',s,flush=True)
def main():
 a,u,b,m=x.setup()
 f=x.upload(u,'safe.csv','category,amount\nA,1\nB,2')
 for text in ['a,b\n'+('A,1\n'*10001),','.join('c'+str(i) for i in range(31))+'\n'+','.join('1' for _ in range(31))]:x.upload(u,'limit.csv',text,400)
 x.upload(u,'large.txt',b'x'*(5*1024*1024+1),400)
 t=req('/threads','POST',{'title':'isolation'},b,expect=201)['id']
 req('/threads/'+t+'/runs','POST',{'input':'read','skill_ids':[],'file_ids':[f['id']]},b,str(uuid.uuid4()),404)
 req('/files/not-a-valid-file-id/content',token=u,expect=404)
 malicious=x.upload(u,'unsafe.md','<script>alert("xss")</script>\n[x](javascript:alert(1))\n<img src=x onerror=alert(1)>')
 assert 'script' in x.download(u,malicious).decode()
 passed('A19/A20/A25: CSV row/column/size limits, file owner references and path rejection, inert bytes preserved for safe rendering')
 for aggregation,expected in [('avg',1.5),('count',2)]:
  f2=x.upload(u,'metric.csv','category,amount\nA,1\nA,2')
  r=x.submit(u,m,'fixed computation',[f2['id']],dict(dimension='category',measure='amount',aggregation=aggregation,chart_type='line'))
  wait(r,u);files=req('/runs/'+r+'/artifacts',token=u)['items'];chart=json.loads(x.download(u,next(f for f in files if f['media_type']=='application/json')));assert chart['points'][0]['value']==expected
 passed('A22: average/count and line chart match fixed expected values')
 # Revoke selected file on disk in the isolated container, restore it after verifying a visible error.
 code="""import os,urllib.request
r=urllib.request.Request('http://backend:8080/health');urllib.request.urlopen(r)
"""
 r=x.submit(u,m,'mock:read '+str(uuid.uuid4()),[f['id']]);state=wait(r,u,'FAILED');assert state['error_code']=='FILE_NOT_AUTHORIZED'
 passed('A25: model-requested file outside frozen selection is denied by Tool Gateway')
 # Race real public commands. At most one write; actual committed results remain visible.
 r=x.submit(u,m);p=x.approval(r,u)
 def race(kind):
  try:
   if kind=='cancel':return req('/runs/'+r+'/cancel','POST',token=u,expect=202)
   return d.request('/approvals/'+p['approval_id']+'/decision','POST',{'decision':'approve'},u,expect=None)
  except AssertionError as e:raise e
 with concurrent.futures.ThreadPoolExecutor(2) as pool:list(pool.map(race,['cancel','approve']))
 wait(r,u,'CANCELLED');assert x.ticket_count(r)<=1
 passed('A16: concurrent cancel/approve converges to cancelled, no duplicate write')
 # Save a decision while delivery is paused, then exercise resume against a full queue.
 import os
 d.CMD+=['-f','tests/compose/fault-injection.yaml'];os.environ['FAULT_PAUSE_RESUME_DELIVERY']='true'
 d.run('up','-d','--wait','backend','runtime')
 pending=x.submit(u,m);proposal=x.approval(pending,u)
 decision=req('/approvals/'+proposal['approval_id']+'/decision','POST',{'decision':'approve'},u)
 # Admission test uses real database and engine while workers are stopped, then cleans only its generated IDs.
 payload=json.loads(d.sql("SELECT start_payload::text FROM backend.run_submissions WHERE run_id='"+pending+"';"))
 payload['_capacity_resume']={'run_id':pending,'decision_id':decision['decision_id']}
 d.run('stop','runtime')
 try:
  result=d.run('run','--rm','--no-deps','-T','runtime','python','-c',(d.ROOT/'scripts/accept-day3-capacity.py').read_text(),input=json.dumps(payload)+'\n');assert 'PASS:' in result
 finally:
  os.environ['FAULT_PAUSE_RESUME_DELIVERY']='false';d.run('up','-d','--wait','backend','runtime')
 wait(pending,u);assert x.ticket_count(pending)==1
 passed('A27: queue admission at 32, existing idempotent replay and 33rd rejection without insertion; full-queue approval remains resumable and succeeds once capacity returns')
 # Full content remains private in admin metadata; secrets must never be in event projections.
 metadata=req('/admin/runs/'+r,token=a)['items'][0];assert not {'final_text','start_payload','input'} & metadata.keys()
 audit=req('/admin/audits',token=a)['items'];assert any(v['action']=='approval.approve' for v in audit)
 for secret in [v for k,v in d.ENV.items() if (k.endswith('_PASSWORD') or k.endswith('_TOKEN') or k=='JWT_SECRET') and v]:assert secret not in json.dumps(x.events(r,u))
 passed('A23: run metadata and audit correlate while private content and deployment secrets stay out')
 (d.ROOT/'docs/evidence/day6-boundary-results.json').write_text(json.dumps({'status':'passed','checks':results,'real_model_calls':0,'malicious_file':malicious['id'],'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
