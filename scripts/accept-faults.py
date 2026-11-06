"""Default-off failure windows, isolated project only. No real model calls."""
import importlib.util,json,time,os,concurrent.futures
from pathlib import Path
spec=importlib.util.spec_from_file_location('delivery',Path(__file__).with_name('accept-delivery.py'));x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
d=x.d;req=x.req;wait=x.wait
FLAGS=['FAULT_FILE_ROOT','FAULT_PAUSE_RESUME_DELIVERY','FAULT_TICKET_RESPONSE_LOST','FAULT_TICKET_QUERY_UNAVAILABLE','FAULT_ARTIFACT_METADATA','FAULT_AFTER_WAIT_CHECKPOINT','FAULT_AFTER_TICKET_COMMIT','APPROVAL_TTL_SECONDS']
d.CMD+=['-f','tests/compose/fault-injection.yaml']
results=[]
def passed(s):results.append(s);print('PASS:',s,flush=True)
def config(**flags):
 for f in FLAGS:os.environ[f]=str(flags.get(f,'600' if f=='APPROVAL_TTL_SECONDS' else '/data/files' if f=='FAULT_FILE_ROOT' else 'false'))
 d.run('up','-d','--wait','backend','runtime')
def recorded(r,name):
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  if d.sql("SELECT count(*) FROM runtime.faults WHERE run_id='"+r+"' AND name='"+name+"';")=='1':return
  time.sleep(.3)
 raise AssertionError('fault not reached')
def decide(r,u,choice='approve'):
 p=x.approval(r,u);req('/approvals/'+p['approval_id']+'/decision','POST',{'decision':choice},u);return p

def main():
 config();a,u,b,m=x.setup()
 try:
  config(APPROVAL_TTL_SECONDS='2');r=x.submit(u,m);x.approval(r,u);wait(r,u,'FAILED');assert x.ticket_count(r)==0
  passed('A11: approval expiry releases run and produces zero tickets')
  config(FAULT_AFTER_WAIT_CHECKPOINT='true');r=x.submit(u,m);recorded(r,'after_wait_checkpoint');assert req('/runs/'+r,token=u)['status']=='RUNNING'
  assert not req('/runs/'+r+'/approvals',token=u)['items']
  d.run('restart','runtime');p=x.approval(r,u);decide(r,u);wait(r,u);assert x.ticket_count(r)==1
  passed('A14: saved interrupt before WAITING publication repaired after restart, same execution succeeds once')
  config(FAULT_PAUSE_RESUME_DELIVERY='true');r=x.submit(u,m);p=x.approval(r,u)
  req('/approvals/'+p['approval_id']+'/decision','POST',{'decision':'approve'},u)
  assert x.ticket_count(r)==0
  d.run('restart','backend','runtime');assert x.approval(r,u)['approval_id']==p['approval_id']
  config();state=wait(r,u,expected='SUCCEEDED')
  assert x.ticket_count(r)==1
  passed('A13: persisted decision/command survives backend/runtime restart and produces one ticket')
  config(FAULT_TICKET_RESPONSE_LOST='true');r=x.submit(u,m);decide(r,u);wait(r,u);assert x.ticket_count(r)==1
  passed('A15: committed ticket with lost response is queried by original execution, not written again')
  config(FAULT_TICKET_RESPONSE_LOST='true',FAULT_TICKET_QUERY_UNAVAILABLE='true');r=x.submit(u,m);decide(r,u);state=wait(r,u,'FAILED');assert state['error_code']=='OUTCOME_UNKNOWN' and x.ticket_count(r)==1
  assert any(e['type']=='tool.failed' and e['payload']['status']=='UNKNOWN' for e in x.events(r,u))
  passed('A15: query unavailable leaves explicit UNKNOWN and one ticket, no blind retry')
  config(FAULT_AFTER_TICKET_COMMIT='true');r=x.submit(u,m);decide(r,u);recorded(r,'after_ticket_commit');assert x.ticket_count(r)==1
  req('/runs/'+r+'/cancel','POST',token=u,expect=202);d.run('restart','runtime');wait(r,u,'CANCELLED');assert x.ticket_count(r)==1
  assert any(e['type']=='tool.completed' for e in x.events(r,u))
  passed('A16: cancel after committed write preserves/reconciles actual ticket, does not claim rollback')
  config();r=x.submit(u,m);x.approval(r,u);changed=d.write('ModelWrite',m,enabled=False,is_default=False);m=req('/admin/models/'+m['id'],'PATCH',changed,a);wait(r,u,'FAILED');assert x.ticket_count(r)==0
  m=req('/admin/models/'+m['id'],'PATCH',d.write('ModelWrite',m,enabled=True,is_default=True),a)
  passed('A17: disabling model during wait revokes approval execution and releases run')
  # Five waits do not retain the four workers; a sixth ordinary run still finishes.
  waits=[x.submit(u,m) for _ in range(5)]
  for r in waits:x.approval(r,u)
  wait(x.submit(u,m,'ordinary while waiting'),u)
  for r in waits:req('/runs/'+r+'/cancel','POST',token=u,expect=202);wait(r,u,'CANCELLED')
  passed('A27: five durable approvals release all worker slots, ordinary work continues')
  r=x.submit(u,m,'report fault');wait(r,u);config(FAULT_ARTIFACT_METADATA='true');req('/runs/'+r+'/artifacts','POST',token=u,expect=503);assert not req('/runs/'+r+'/artifacts',token=u)['items']
  config(FAULT_FILE_ROOT='/proc/agent-workspace-storage-fault');req('/runs/'+r+'/artifacts','POST',token=u,expect=503);assert not req('/runs/'+r+'/artifacts',token=u)['items']
  config();report=req('/runs/'+r+'/artifacts','POST',token=u);x.download(u,report)
  passed('A21: metadata and physical storage failure expose no READY artifact; explicit retry creates downloadable report')
  f=x.upload(u,'persistent.txt','persisted');d.run('restart','backend','runtime');assert x.download(u,f)==b'persisted'
  passed('A26: file and run history survive service restart')
 finally:config()
 (d.ROOT/'docs/evidence/day6-fault-results.json').write_text(json.dumps({'status':'passed','checks':results,'real_model_calls':0,'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
