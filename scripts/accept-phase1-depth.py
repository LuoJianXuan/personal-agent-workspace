"""Authorized deeper acceptance: fixed parsers, native files/context and hard budget."""
import base64,importlib.util,json,time,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('phase',ROOT/'scripts/accept-phase1.py')
phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
d=phase.base;req=d.request;checks=[]
def passed(label):checks.append(label);print('PASS',label,flush=True)
def events(run,token):
 out=[];seq=0
 while True:
  page=req('/runs/'+run+'/events?after_seq='+str(seq),token=token);out+=page['items'];seq=page['next_seq']
  if not page['has_more']:return out
def fixture(kind):
 code='''import base64,io
kind=%r
out=io.BytesIO()
if kind=='pdf':
 from pypdf import PdfWriter
 from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
 writer=PdfWriter();page=writer.add_blank_page(width=300,height=300)
 font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
 page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
 stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 200 Td (Budget 100, deadline two weeks.) Tj ET')
 page[NameObject('/Contents')]=writer._add_object(stream);writer.write(out)
else:
 from openpyxl import Workbook
 book=Workbook();sheet=book.active;sheet.title='数据';sheet.append(['地区','金额']);sheet.append(['东',10]);sheet.append(['东',20]);sheet.append(['西',7]);book.save(out)
print(base64.b64encode(out.getvalue()).decode())
'''
 return base64.b64decode(d.run('exec','-T','runtime','python','-',input=code%kind))
def main():
 session=phase.login('user-a')
 pdf=phase.upload(session,'phase1-text.pdf',fixture('pdf'));doc=phase.wait_doc(session,pdf['id'])
 assert 'Budget 100' in doc['chunks'][0]['text'] and doc['chunks'][0]['page']==1
 passed('Text PDF is parsed by a real bounded on-demand child with physical-page locator')
 excel=phase.upload(session,'phase1-values.xlsx',fixture('xlsx'));phase.wait_doc(session,excel['id'])
 run,state=phase.run(session,'mock:xlsx',[excel['id']]);assert state['status']=='SUCCEEDED',state
 files=req('/runs/'+run+'/artifacts',token=session)['items'];chart=next(f for f in files if f['media_type']=='application/json')
 data=json.loads(req('/files/'+chart['id']+'/content',token=session)['text']);assert data['row_count']==3 and {p['label']:p['value'] for p in data['points']}=={'东':30,'西':7}
 passed('XLSX cached values → governed Decimal aggregation → exact chart/CSV artifacts')
 run,state=phase.run(session,'mock:workspace');assert state['status']=='SUCCEEDED' and '150' in state['final_text'],state
 execution=d.sql("SELECT string_agg(tool_name,',' ORDER BY tool_name) FROM runtime.tool_executions WHERE run_id='"+run+"' AND status='SUCCEEDED';")
 assert execution=='edit_file,read_file,write_file',execution
 assert d.sql("SELECT revision FROM backend.work_files WHERE path='/work/acceptance-"+run+".md';")=='2'
 assert any(e['type']=='task.updated' and e['payload']['tasks'][0]['status']=='completed' for e in events(run,session))
 passed('Native file write/edit/read is scoped, versioned and audited through real Backend')
 text='材料依据与统计口径，保留所有关键事实。'*2200
 large=phase.upload(session,'phase1-large.txt',text.encode())
 run,state=phase.run(session,'mock:offload',[large['id']]);assert state['status']=='SUCCEEDED',state
 assert d.sql("SELECT count(*) FROM backend.work_files WHERE thread_id='"+state['thread_id']+"' AND path LIKE '/large_tool_results/%';")!='0'
 passed('Long actual tool result is offloaded through native filesystem middleware')
 admin=req('/auth/login','POST',{'username':d.ENV['SEED_ADMIN_USERNAME'],'password':d.ENV['SEED_ADMIN_PASSWORD']})['access_token']
 source=next(m for m in req('/admin/models',token=admin)['items'] if m['enabled'])
 model=req('/admin/models','POST',{**d.write('ModelWrite',source),'name':'Context acceptance '+uuid.uuid4().hex[:8],'revision':0,'is_default':False,'context_limit':12000,'max_output_tokens':128},admin)
 thread=req('/threads','POST',{'title':'Phase1 context '+uuid.uuid4().hex[:8]},session,201)['id']
 compacted=[]
 for i in range(10):
  run,state=phase.run(session,'mock:context P1-KEEP '+('context-detail '*280)+str(i),thread_id=thread,model_id=model['id'])
  assert state['status']=='SUCCEEDED',state
  compacted=[e for e in events(run,session) if e['type']=='context.compacted']
  if compacted:break
 assert compacted,'native compaction was not triggered'
 assert int(d.sql("SELECT count(*) FROM runtime.model_calls WHERE run_id='"+run+"';"))>=2
 assert d.sql("SELECT count(*) FROM backend.work_files WHERE thread_id='"+thread+"' AND path LIKE '/conversation_history/%';")!='0'
 passed('Native summary is triggered, original history is offloaded, summary consumes model budget')
 run,state=phase.run(session,'mock:budget');assert state['status']=='FAILED' and state['error_code']=='MODEL_CALL_LIMIT',state
 assert d.sql("SELECT count(*) FROM runtime.model_calls WHERE run_id='"+run+"';")=='12'
 passed('Repeated native tools cannot exceed the hard 12-model-call budget')
 output={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'checks':checks,'real_model_calls':0,'real_search_calls':0}
 (ROOT/'docs/evidence/phase1-depth-results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
