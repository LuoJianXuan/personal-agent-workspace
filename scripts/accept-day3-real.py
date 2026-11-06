"""Explicitly authorized small real DeepSeek smoke; API key only in Runtime environment."""
import importlib.util,json,time,uuid,urllib.request,urllib.error
from pathlib import Path
spec=importlib.util.spec_from_file_location('mock_accept',Path(__file__).with_name('accept-day3.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.d.BASE='http://127.0.0.1:5173/api'
env=dict(line.split('=',1) for line in (m.d.ROOT/'.env').read_text(encoding='utf-8').splitlines() if '=' in line and not line.startswith('#'))
req=m.req
report={'mode':'real','provider':'DeepSeek','protocol':'openai_chat_completions','checks':[],'runs':[],'status':'running'}
output=m.d.ROOT/'docs/evidence/day3-real-results.json'
def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 a=req('/auth/login','POST',{'username':env['SEED_ADMIN_USERNAME'],'password':env['SEED_ADMIN_PASSWORD']})['access_token']
 models=req('/admin/models',token=a)['items']
 model=next((x for x in models if x['name']=='DeepSeek 非思考'),None)
 if not model:
  model=req('/admin/models','POST',{'name':'DeepSeek 非思考','provider':'deepseek','protocol':'openai_chat_completions','protocol_options':{'thinking':{'type':'disabled'}},'provider_model_name':'deepseek-flash','base_url':'https://api.deepseek.com','credential_ref':'deepseek_primary','context_limit':64000,'max_output_tokens':512,'capabilities':{'streaming':True,'tool_calling':True},'enabled':True,'is_default':not any(x['is_default'] for x in models),'revision':0},a)
 report['model_id']=model['id'];report['model_revision']=model['revision'];report['provider_model_name']=model['provider_model_name']
 connections=req('/admin/mcp-connections',token=a)['items'];conn=next((x for x in connections if x['name']=='演示订单查询'),None)
 if not conn:conn=req('/admin/mcp-connections','POST',{'name':'演示订单查询','endpoint':'http://demo-mcp:8001/mcp/','credential_ref':'','enabled':True,'revision':0},a)
 cp='/admin/mcp-connections/'+conn['id'];conn=req(cp+'/discover','POST',{'revision':conn['revision']},a);tool=req(cp+'/tools',token=a)['items'][0]
 if not tool['enabled']:req(cp+'/tools/'+tool['namespaced_tool_id'],'PATCH',{'enabled':True,'revision':tool['revision']},a)
 t=req('/threads','POST',{'title':'S03 DeepSeek 真实验收'},a,expect=201)['id'];report['thread_id']=t
 prompts=['请记住本次合成验收标记“青竹-731”。用三点简短说明什么是流式输出，总计约150字；不要调用工具。','我上一轮请你记住的合成验收标记是什么？只返回标记，不调用工具。','请务必调用已提供的订单查询工具查询 DEMO-1001，依据真实工具返回简短说明订单状态，不要猜测。']
 for i,text in enumerate(prompts):
  r=req('/threads/'+t+'/runs','POST',{'input':text,'model_id':model['id'],'skill_ids':[]},a,str(uuid.uuid4()),202);rid=r['run_id'];report['runs'].append({'run_id':rid,'case':['chat_stream','history','tool_loop'][i]});save()
  deadline=time.monotonic()+190;early=False
  while time.monotonic()<deadline:
   state=req('/runs/'+rid,token=a)
   try:events=m.all_events(rid,a)
   except AssertionError:events=[]
   if state['status']=='RUNNING' and sum(e['type']=='message.delta' for e in events)>=2:early=True
   if state['status'] in ['SUCCEEDED','FAILED','INTERRUPTED']:break
   time.sleep(.2)
  report['runs'][-1].update(status=state['status'],error_code=state['error_code'],delta_count=sum(e['type']=='message.delta' for e in events),stream_before_completion=early)
  if state['status']!='SUCCEEDED':report['status']='failed';save();print('REAL FAILED:',state['error_code'],flush=True);return
  if i==1:assert '青竹-731' in state['final_text']
  if i==2:assert any(e['type']=='tool.completed' and 'DEMO-1001' in e['payload']['text'] for e in events)
  report['checks'].append(['chat_stream','history','real_mcp_tool_loop'][i]);save();print('REAL PASS:',report['checks'][-1],flush=True)
 report['status']='passed';save()
if __name__=='__main__':main()
