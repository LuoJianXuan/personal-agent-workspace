"""Authorized <=8 DeepSeek calls, max 512 output tokens. Requires runtime budget override."""
import importlib.util,json,time,uuid,os
from pathlib import Path
spec=importlib.util.spec_from_file_location('delivery',Path(__file__).with_name('accept-delivery.py'));x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
d=x.d;req=x.req;d.BASE='http://127.0.0.1:5173/api'
d.CMD=[d.DOCKER,'compose','-p','agent-workspace']
env=dict(line.split('=',1) for line in (d.ROOT/'.env').read_text(encoding='utf-8').splitlines() if '=' in line and not line.startswith('#'))
report={'status':'running','mode':'real','provider':'DeepSeek','authorized_calls':8,'max_output_tokens':512,'runs':[],'checks':[]}
path=d.ROOT/'docs/evidence/day6-real-results.json'
def save():path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 a=req('/auth/login','POST',{'username':env['SEED_ADMIN_USERNAME'],'password':env['SEED_ADMIN_PASSWORD']})['access_token']
 m=next(v for v in req('/admin/models',token=a)['items'] if v['name']=='DeepSeek 非思考')
 assert m['max_output_tokens']<=512 and m['protocol_options']=={'thinking':{'type':'disabled'}}
 guard=d.run('exec','-T','runtime','python','-c',"import os;print(os.getenv('REAL_CALL_BUDGET','')+'|'+os.getenv('REAL_MAX_OUTPUT_TOKENS',''))")
 assert guard=='8|512','Runtime must have budget guard before any model request'
 report.update(model_id=m['id'],model_revision=m['revision'],provider_model_name=m['provider_model_name'])
 def run(text,files=None,scene=None):
  r=x.submit(a,m,text,files,scene);report['runs'].append({'run_id':r});save();return r
 prior=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
 if prior and prior.get('runs') and prior['status']=='failed':
  report['runs']=prior['runs'];old=req('/runs/'+prior['runs'][0]['run_id'],token=a)
  assert old['status']=='SUCCEEDED'
  r=req('/threads/'+old['thread_id']+'/runs','POST',{'input':'请现在直接调用 builtin_create_demo_ticket 提交上述工单提案。工具网关会自动暂停并向我展示审批卡，我将在卡片上决定；本条消息仅授权提交提案，不代表批准实际写入。不要仅在正文里询问，不要重复查询订单。','model_id':m['id'],'skill_ids':[]},a,str(uuid.uuid4()),202)['run_id']
  report['runs'].append({'run_id':r});report['checks'].append('Initial real turn queried MCP and asked in text; follow-up explicitly requests the system approval card');save()
 else:
  r=run('合成验收：先查询 DEMO-1001，再直接调用 builtin_create_demo_ticket 提交标题“真实闭环验收”、描述“根据查询结果跟进订单”的提案。工具网关会自动暂停并显示审批卡，我在卡片上决定；不要仅在正文询问。不要重复工具调用。')
 p=x.approval(r,a,timeout=190);assert x.ticket_count(r)==0
 req('/approvals/'+p['approval_id']+'/decision','POST',{'decision':'approve'},a)
 state=x.wait(r,a,timeout=190);assert x.ticket_count(r)==1
 report['runs'][-1]['status']=state['status'];report['checks'].append('real DeepSeek -> real MCP -> persistent approval -> one ticket -> final answer');save()
 f=x.upload(a,'真实验收资料.txt','合成项目：晨光-842。预算为 128 元。')
 r=run('请调用 builtin_read_material 读取本轮附件，然后只回答合成项目名称与预算。',[f['id']]);state=x.wait(r,a,timeout=190);assert '晨光-842' in state['final_text'] and '128' in state['final_text']
 report['runs'][-1]['status']=state['status'];report['checks'].append('real selected-file read and grounded answer');save()
 f=x.upload(a,'真实验收销售.csv','地区,销售额\n东区,10.2\n西区,3\n东区,4.8')
 r=run('请仅解读已有固定统计结果，最多两句话；不要再次调用工具。',[f['id']],dict(dimension='地区',measure='销售额',aggregation='sum',chart_type='bar',unit='元'));state=x.wait(r,a,timeout=190)
 files=req('/runs/'+r+'/artifacts',token=a)['items'];chart=json.loads(x.download(a,next(f for f in files if f['media_type']=='application/json')));assert chart['points'][0]['value']==15
 report['runs'][-1]['status']=state['status'];report['checks'].append('real interpretation of deterministic CSV chart');report['chart_thread']=state['thread_id'];save()
 output=req('/runs/'+r+'/artifacts','POST',token=a);x.download(a,output)
 ids=','.join("'"+v['run_id']+"'" for v in report['runs'])
 records=json.loads(d.sql("SELECT coalesce(json_agg(t),'[]') FROM (SELECT run_id,model_revision,status,usage,error_code FROM runtime.model_calls WHERE run_id IN ("+ids+") ORDER BY created_at) t;"))
 assert len(records)<=8;report.update(status='passed',model_calls=len(records),usage_records=records,timestamp=time.strftime('%Y-%m-%dT%H:%M:%S%z'));save();print('REAL PASS requests='+str(len(records)),flush=True)
if __name__=='__main__':
 try:main()
 except Exception:
  report['status']='failed';save();raise
