"""S04-S07 isolated integration acceptance. Mock model; real services and storage."""
import importlib.util,json,time,uuid,urllib.request,urllib.error,concurrent.futures,hashlib,os
from pathlib import Path
spec=importlib.util.spec_from_file_location('d3',Path(__file__).with_name('accept-day3.py'));d3=importlib.util.module_from_spec(spec);spec.loader.exec_module(d3)
d=d3.d;req=d3.req;wait=d3.wait;events=d3.all_events
results=[]
def passed(s):results.append(s);print('PASS:',s,flush=True)
def setup():
 a=d.login('ADMIN')['access_token']
 for user in req('/admin/users',token=a)['items']:
  if not user['enabled']:req('/admin/users/'+user['id'],'PATCH',{'enabled':True,'revision':user['revision']},a)
 u=d.login('USER_A')['access_token'];b=d.login('USER_B')['access_token']
 model=json.loads((d.ROOT/'schemas/examples/model-write.json').read_text());model.update(name='Delivery '+d.SUFFIX,base_url='https://api.deepseek.com',credential_ref='deepseek_primary',provider_model_name='mock-only',is_default=True,enabled=True,context_limit=64000,max_output_tokens=512,revision=0)
 m=req('/admin/models','POST',model,a)
 return a,u,b,m

def submit(u,m,text='mock:ticket',files=None,scene=None):
 t=req('/threads','POST',{'title':'Delivery '+d.SUFFIX},u,expect=201)
 body={'input':text,'model_id':m['id'],'skill_ids':[],'file_ids':files or []}
 if scene:body['scenario']=scene
 return req('/threads/'+t['id']+'/runs','POST',body,u,str(uuid.uuid4()),202)['run_id']
def approval(r,u,timeout=30):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  rstate=req('/runs/'+r,token=u)
  if rstate.get('runtime_unavailable'):time.sleep(.3);continue
  if rstate['status']=='WAITING_APPROVAL':
   items=req('/runs/'+r+'/approvals',token=u)['items'];assert items;return items[-1]
  assert rstate['status'] not in ['FAILED','CANCELLED','INTERRUPTED','SUCCEEDED'],rstate
  time.sleep(.25)
 raise AssertionError('Approval timeout '+r)
def ticket_count(r):return int(d.sql("SELECT count(*) FROM backend.demo_tickets WHERE run_id='"+r+"';"))
def upload(u,name,text,expect=201):
 boundary='workspace'+uuid.uuid4().hex
 content=text.encode() if isinstance(text,str) else text
 body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
 request=urllib.request.Request(d.BASE+'/files',data=body,headers={'Authorization':'Bearer '+u,'Content-Type':'multipart/form-data; boundary='+boundary})
 try:
  with urllib.request.urlopen(request,timeout=25) as response:status,raw=response.status,response.read()
 except urllib.error.HTTPError as e:status,raw=e.code,e.read()
 assert status==expect,(status,raw[:200]);return json.loads(raw)
def download(u,f):
 with urllib.request.urlopen(urllib.request.Request(d.BASE+'/files/'+f['id']+'/download',headers={'Authorization':'Bearer '+u})) as r:raw=r.read()
 assert hashlib.sha256(raw).hexdigest()==f['sha256'];return raw

def main():
 a,u,b,m=setup();r=submit(u,m);p=approval(r,u)
 assert ticket_count(r)==0
 req('/approvals/'+p['approval_id']+'/decision','POST',{'decision':'approve'},b,expect=404)
 with concurrent.futures.ThreadPoolExecutor(4) as pool:
  decisions=list(pool.map(lambda _:req('/approvals/'+p['approval_id']+'/decision','POST',{'decision':'approve'},u),range(4)))
 assert len({x['decision_id'] for x in decisions})==1
 wait(r,u);assert ticket_count(r)==1
 req('/approvals/'+p['approval_id']+'/decision','POST',{'decision':'reject'},u,expect=409)
 passed('A12/A20: full bound approval, owner isolation, concurrent same decision, exactly one ticket')
 r2=submit(u,m);p2=approval(r2,u);d.run('restart','runtime');p3=approval(r2,u);assert p3==p2
 req('/approvals/'+p2['approval_id']+'/decision','POST',{'decision':'approve'},u);wait(r2,u);assert ticket_count(r2)==1
 passed('A13: durable LangGraph interrupt survives Runtime restart with same approval and one write')
 r3=submit(u,m);p=approval(r3,u);req('/approvals/'+p['approval_id']+'/decision','POST',{'decision':'reject'},u);wait(r3,u,'CANCELLED');assert ticket_count(r3)==0
 r4=submit(u,m);approval(r4,u);req('/runs/'+r4+'/cancel','POST',token=u,expect=202);wait(r4,u,'CANCELLED');assert ticket_count(r4)==0
 r5=submit(u,m,'mock:long');time.sleep(.6);req('/runs/'+r5+'/cancel','POST',token=u,expect=202);wait(r5,u,'CANCELLED')
 passed('A11/A16: rejected approval and cancellation during wait/stream terminate without writes')
 f=upload(u,'验收资料.txt','项目代号：晨光。预算 123。');req('/files/'+f['id'],token=b,expect=404);req('/files/'+f['id']+'/content',token=b,expect=404);download(u,f)
 rr=submit(u,m,'mock:read '+f['id'],[f['id']]);rrs=wait(rr,u);assert '晨光' in rrs['final_text']
 passed('A19/A20: authorized material uses real storage/read tool; cross-owner access denied and hash matches download')
 csvfile=upload(u,'销售.csv','区域,金额\n华东,10.2\n华北,3\n华东,4.8\n')
 scene={'dimension':'区域','measure':'金额','aggregation':'sum','chart_type':'bar','unit':'元'}
 rc=submit(u,m,'分析销售',[csvfile['id']],scene);wait(rc,u)
 artifacts=req('/runs/'+rc+'/artifacts',token=u)['items'];assert len(artifacts)==2
 chart=json.loads(download(u,next(x for x in artifacts if x['media_type']=='application/json')))
 assert chart['points']==[{'label':'华东','value':15.0},{'label':'华北','value':3.0}]
 calls=d.sql("SELECT count(*) FROM runtime.model_calls WHERE run_id='"+rc+"';")
 report=req('/runs/'+rc+'/artifacts','POST',token=u);again=req('/runs/'+rc+'/artifacts','POST',token=u);assert report['id']==again['id'];assert '运行报告' in download(u,report).decode()
 assert d.sql("SELECT count(*) FROM runtime.model_calls WHERE run_id='"+rc+"';")==calls
 assert len([e for e in events(rc,u) if e['type']=='artifact.ready'])==3
 passed('A21/A22: fixed Decimal totals, source-bound chart/CSV, real downloads, idempotent report without model calls')
 upload(u,'bad.exe','bad',400);upload(u,'bad.txt',b'\xff',400);upload(u,'too.txt','x'*50001,400);upload(u,'bad.csv','a,a\n1,2',400)
 req('/threads/'+req('/threads','POST',{'title':'invalid'},u,expect=201)['id']+'/runs','POST',{'input':'x','file_ids':[f['id']]*4},u,str(uuid.uuid4()),400)
 passed('File extension, encoding, text limit, CSV headers and maximum references enforced')
 report={'status':'passed','checks':results,'mode':'mock','real_model_calls':0,'approval_run':r2,'chart_run':rc,'file_id':csvfile['id'],'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
 (d.ROOT/'docs/evidence/day4-5-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
