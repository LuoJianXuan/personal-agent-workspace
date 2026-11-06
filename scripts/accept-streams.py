"""A27 controlled subscription caps and heartbeat. Not a production load test."""
import importlib.util,json,time,uuid,urllib.request,urllib.error,concurrent.futures
from pathlib import Path
spec=importlib.util.spec_from_file_location('delivery',Path(__file__).with_name('accept-delivery.py'));x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
d=x.d;req=x.req

def main():
 a,u,b,m=x.setup();clients=[];streams=[]
 try:
  for i in range(9):
   name='stream-'+uuid.uuid4().hex[:12];password='Test-'+uuid.uuid4().hex
   req('/admin/users','POST',{'username':name,'password':password},a)
   token=req('/auth/login','POST',{'username':name,'password':password})['access_token']
   r=x.submit(token,m);x.approval(r,token);clients.append((token,r))
  def open_stream(pair):
   token,r=pair
   return urllib.request.urlopen(urllib.request.Request(d.BASE+'/runs/'+r+'/stream',headers={'Authorization':'Bearer '+token}),timeout=25)
  with concurrent.futures.ThreadPoolExecutor(8) as pool:streams=list(pool.map(open_stream,[p for p in clients[:8] for _ in range(4)]))
  try:open_stream(clients[8]);raise AssertionError('33rd subscriber was admitted')
  except urllib.error.HTTPError as e:assert e.code==429 and e.headers['Retry-After']=='3'
  before=time.monotonic();req('/admin/models',token=a);latency=time.monotonic()-before;assert latency<3
  # Other subscribers intentionally do not drain their streams.
  ordinary=x.submit(clients[8][0],m,'work while 32 subscribers are open');x.wait(ordinary,clients[8][0])
  heartbeat=False;deadline=time.monotonic()+22
  for line in streams[0]:
   if line.startswith(b': heartbeat'):heartbeat=True;break
   if time.monotonic()>deadline:break
  assert heartbeat
  result={'status':'passed','subscribers':32,'rejected_subscriber':33,'http_status':429,'retry_after':3,'management_latency_seconds':round(latency,3),'checks':['Per-process 32 cap across 8 owners; 33rd from ninth owner rejected','Heartbeat observed on real waiting SSE; 31 non-reading clients did not block ordinary execution or management API'],'real_model_calls':0,'limits':'No OS socket saturation or production throughput claim','timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
  (d.ROOT/'docs/evidence/day6-stream-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print('PASS: A27 global 32 SSE cap, heartbeat, non-reading subscriptions and management responsiveness',flush=True)
 finally:
  for s in streams:s.close()
  for token,r in clients:req('/runs/'+r+'/cancel','POST',token=token,expect=202);x.wait(r,token,'CANCELLED')
if __name__=='__main__':main()
