"""Explicitly authorized integration acceptance; Model Mock, real workspace services."""
import base64,importlib.util,io,json,os,time,urllib.request,urllib.error,uuid,zipfile
from pathlib import Path
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('base',ROOT/'scripts/accept-day2.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
assert os.environ.get('WORKSPACE_PHASE1_AUTHORIZED')=='true','Use verify-phase1.ps1 -Authorized'
assert base.TEST_PROJECT in ('agent-workspace-verification','agent-workspace-fresh')
checks=[]
def passed(name):checks.append(name);print('PASS',name,flush=True)
def fixture_docx(text):
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w') as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
  z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+escape(text)+'</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
 return out.getvalue()
def upload(token,name,data):
 boundary='phase1-'+uuid.uuid4().hex
 body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+data+f'\r\n--{boundary}--\r\n'.encode()
 req=urllib.request.Request(base.BASE+'/files',data=body,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'multipart/form-data; boundary='+boundary})
 with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
def wait_doc(token,id):
 before=base.request('/files/'+id+'/parsed',token=token)
 assert before['status']=='not_extracted',before
 assert base.sql("SELECT count(*) FROM backend.document_jobs WHERE file_id='"+id+"';")=='0'
 doc=base.request('/files/'+id+'/extract','POST',{},token)
 assert doc['status']=='ready',doc['error']
 return doc
def run(token,prompt,files=None,network=False,thread_id=None,model_id=None):
 t={'id':thread_id} if thread_id else base.request('/threads','POST',{'title':'Phase1 '+uuid.uuid4().hex[:8]},token,201)
 body={'input':prompt,'skill_ids':[],'file_ids':files or [],'network_enabled':network}
 if model_id:body['model_id']=model_id
 req=urllib.request.Request(base.BASE+'/threads/'+t['id']+'/runs',data=json.dumps(body).encode(),method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())})
 with urllib.request.urlopen(req,timeout=20) as r:submitted=json.load(r)
 id=submitted['run_id']
 for _ in range(180):
  state=base.request('/runs/'+id,token=token)
  if state['status'] in ('SUCCEEDED','FAILED','CANCELLED','INTERRUPTED'):return id,state
  time.sleep(.5)
 raise AssertionError('run did not terminalize')
def login(name):return base.request('/auth/login','POST',{'username':name,'password':base.ENV['SEED_'+('USER_A' if name=='user-a' else 'USER_B')+'_PASSWORD']})['access_token']

def main():
 session=login('user-a');other=login('user-b')
 a=upload(session,'phase1-a.docx',fixture_docx('第一版预算 100 元，期限两周。'))
 b=upload(session,'phase1-b.docx',fixture_docx('第二版预算 150 元，期限三周。'))
 for f in (a,b):
  doc=wait_doc(session,f['id']);assert doc['chunks'] and doc['chunks'][0]['locator'].startswith('段落')
 passed('DOCX upload only saves; explicit on-demand fixed parser creates scoped cache')
 id,state=run(session,'mock:compare',[a['id'],b['id']]);assert state['status']=='SUCCEEDED',state
 sources=base.request('/runs/'+id+'/sources',token=session)['items'];assert len(sources)>=2
 artifacts=base.request('/runs/'+id+'/artifacts',token=session)['items'];assert any(f['name'].endswith('.docx') for f in artifacts)
 md=next(f for f in artifacts if f['name'].endswith('.md'));assert '[source:' in base.request('/files/'+md['id']+'/content',token=session)['text']
 passed('Harness material comparison → real sources → Markdown/DOCX artifacts')
 id2,state=run(session,'mock:report mock:version',[md['id']]);assert state['status']=='SUCCEEDED',state
 versions=base.request('/runs/'+id2+'/artifacts',token=session)['items'];v2=next(f for f in versions if f['name'].endswith('.md'))
 lineage=base.request('/files/'+v2['id']+'/versions',token=session)['items'];assert len(lineage)==2 and lineage[1]['id']==md['id']
 passed('Report v2 preserves v1 and validates source ownership')
 base.request('/files/'+a['id']+'/parsed',token=other,expect=404);base.request('/runs/'+id+'/sources',token=other,expect=404)
 passed('Parsed document and source API deny foreign owner')
 research,state=run(session,'mock:research',network=True);assert state['status']=='SUCCEEDED',state
 src=base.request('/runs/'+research+'/sources',token=session)['items'];assert sum(s['read_status']=='read' for s in src)>=3
 assert sum(s['read_status']=='search_only' for s in src)==3,'Search must succeed before reading discovered URLs'
 seq=0;research_events=[]
 while True:
  page=base.request('/runs/'+research+'/events?after_seq='+str(seq),token=session);research_events+=page['items'];seq=page['next_seq']
  if not page['has_more']:break
 assert not any(e['type']=='tool.failed' for e in research_events),'A later report must not hide a failed search/read'
 assert all('web-fixture:8003' in s.get('url','') for s in src)
 passed('Explicit test upstream: search → three reads → cited report; not real internet evidence')
 denied,state=run(session,'mock:fetch http://127.0.0.1/private',network=True);assert state['status']=='FAILED',state
 passed('Public web tool refuses loopback even in fixture mode')
 base.request('/runs/'+id+'/artifacts?format=docx','POST',{},session)
 passed('Post-run DOCX format export uses stored results without another model call')
 output={'date':time.strftime('%Y-%m-%d'),'checks':checks,'real_model_calls':0,'real_search_calls':0,'browser':'not executed by this script'}
 (ROOT/'docs/evidence/phase1-integration-results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
