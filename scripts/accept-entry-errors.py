"""Keep safe capability errors actionable at the user submission boundary."""
import importlib.util,json,time,urllib.request,urllib.error,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('phase',ROOT/'scripts/accept-phase1.py');phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
d=phase.base;req=d.request
def main():
 u=phase.login('user-a');b=phase.login('user-b');a=d.login('ADMIN')['access_token']
 personal=[s for s in req('/catalog/skills',token=u)['items'] if s['enabled'] and s['personal_enabled']]
 for i in range(max(0,4-len(personal))):
  skill=req('/admin/skills','POST',{'name':'Overflow '+uuid.uuid4().hex[:8],'description':'Synthetic entry boundary','category':'验收','content':'合成验收，不含秘密。','enabled':True,'revision':0},a)
  req('/me/skills/'+skill['id']+'/enablement','PUT',{'enabled':True},u)
 thread=req('/threads','POST',{'title':'Entry errors '+uuid.uuid4().hex[:8]},u,201)['id']
 def rejected(body,status,code):
  request=urllib.request.Request(d.BASE+'/threads/'+thread+'/runs',data=json.dumps(body).encode(),method='POST',headers={'Authorization':'Bearer '+u,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())})
  try:urllib.request.urlopen(request,timeout=20);raise AssertionError('Invalid submission accepted')
  except urllib.error.HTTPError as error:
   data=json.load(error);assert error.code==status and data['code']==code,(error.code,data['code'])
   return data
 error=rejected({'input':'overflow'},400,'INVALID_ARGUMENT');assert '3' in error['message'] and '技能' in error['message']
 rejected({'input':'unknown model','skill_ids':[],'model_id':str(uuid.uuid4())},409,'MODEL_UNAVAILABLE')
 rejected({'input':'unknown skill','skill_ids':[str(uuid.uuid4())]},404,'NOT_FOUND')
 file=phase.upload(b,'foreign-entry.txt',b'synthetic owner boundary')
 rejected({'input':'foreign file','skill_ids':[],'file_ids':[file['id']]},404,'NOT_FOUND')
 assert d.sql("SELECT count(*) FROM backend.run_submissions WHERE thread_id='"+thread+"';")=='0'
 run,state=phase.run(u,'mock:context entry succeeds with explicit empty skills',thread_id=thread);assert state['status']=='SUCCEEDED',state
 result={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'checks':['skill_overflow_actionable_400','unknown_model_409','unknown_skill_404','foreign_file_404','invalid_submissions_create_no_run','explicit_empty_skills_succeed'],'real_model_calls':0,'real_search_calls':0}
 (ROOT/'docs/evidence/phase1-entry-error-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('PASS Entry boundary preserves safe specific errors; explicit empty skills succeed',flush=True)
if __name__=='__main__':main()
