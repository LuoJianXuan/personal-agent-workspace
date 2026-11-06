"""Cross-check browser-created data with authoritative APIs in the Mock stack."""
import importlib.util,json,time,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('delivery',Path(__file__).with_name('accept-delivery.py'));x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
d=x.d
assert d.TEST_PROJECT=='agent-workspace-verification'
u=d.login('USER_A')['access_token']
case=json.loads(Path(sys.argv[1] if len(sys.argv)>1 else d.ROOT/'docs/evidence/regression-2026-11-04/ui-data-results.json').read_text(encoding='utf-8'))
checks=[]
history=x.req('/threads/'+case['history_thread']+'/messages',token=u)['items']
assert len(history)==6 and sum(m['role']=='assistant' for m in history)==3
checks.append('Browser first-send/multi-turn: three turns, exactly three persisted assistant replies')
assert x.ticket_count(case['approval_run'])==1
checks.append('Browser approval: exactly one committed synthetic ticket')
file=x.req('/files/'+case['file_id'],token=u)
run=case['chart_run'];assert x.req('/runs/'+run,token=u)['status']=='SUCCEEDED'
artifacts=x.req('/runs/'+run+'/artifacts',token=u)['items']
chart=json.loads(x.download(u,next(f for f in artifacts if f['media_type']=='application/json')))
assert chart['file_id']==file['id'] and chart['row_count']==3
assert chart['points']==[{'label':'东区','value':15.0},{'label':'西区','value':3.0}]
checks.append('Browser CSV upload/analysis: authoritative chart tied to uploaded file, east 15 and west 3')
output={'status':'passed','checks':checks,'chart_run':run,'file_id':file['id'],'approval_run':case['approval_run'],'history_thread':case['history_thread'],'real_model_calls':0,'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
(d.ROOT/'docs/evidence/regression-2026-11-04/ui-data-results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(output,ensure_ascii=False))
