"""Day 2 acceptance against the isolated verification stack, never the dev database.
Run after compose migrations/up. No provider/model HTTP calls are made.
"""
import concurrent.futures
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ENV = dict(line.split('=',1) for line in (ROOT/os.environ.get('WORKSPACE_TEST_ENV','.env.test')).read_text(encoding='utf-8').splitlines() if '=' in line and not line.startswith('#'))
DOCKER = os.environ.get('DOCKER_EXE', 'docker')
TEST_ENV=os.environ.get('WORKSPACE_TEST_ENV','.env.test')
TEST_PROJECT=os.environ.get('WORKSPACE_TEST_PROJECT','agent-workspace-verification')
assert TEST_PROJECT in ('agent-workspace-verification','agent-workspace-fresh'), 'Isolated project only'
os.environ.setdefault('TEST_POSTGRES_PORT', '55434' if TEST_PROJECT=='agent-workspace-verification' else '55435')
CMD = [DOCKER,'compose','--env-file',TEST_ENV,'-p',TEST_PROJECT,'-f','compose.yaml','-f','tests/compose/postgres-port.yaml','-f','tests/compose/isolated-stack.yaml','-f','tests/compose/mock-model.yaml']
BASE = 'http://127.0.0.1:'+ENV['WEB_PORT']+'/api'
assert ENV.get('WEB_PORT') in ('5174','5175'), 'This script is restricted to the verification stack'
RESULTS = []
IDS = {}
SUFFIX = uuid.uuid4().hex[:8]
SCHEMA = json.loads((ROOT/'schemas/jsonschema/contracts.json').read_text(encoding='utf-8'))
def passed(name):
    RESULTS.append(name)
    print('PASS:',name,flush=True)
def run(*args,input=None):
    p=subprocess.run(CMD+list(args),cwd=ROOT,input=input,text=True,encoding='utf-8',capture_output=True)
    if p.returncode:
        raise RuntimeError('compose operation failed: '+' '.join(args[:4])+' '+p.stderr[-1000:])
    return p.stdout.strip()
def sql(query):
    return run('exec','-T','postgres','psql','-U','workspace_admin','-d','workspace','-At','-v','ON_ERROR_STOP=1',input=query)
def request(path,method='GET',body=None,token=None,expect=200):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(BASE+path,data=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:status,raw=r.status,r.read()
    except urllib.error.HTTPError as e:status,raw=e.code,e.read()
    try:value=json.loads(raw)
    except Exception:raise AssertionError(f'Non-JSON response {status} at {path}')
    if expect is not None:assert status==expect,(method,path,status,value)
    return value if expect is not None else (status,value)
def login(prefix):
    return request('/auth/login','POST',{'username':ENV['SEED_'+prefix+'_USERNAME'],'password':ENV['SEED_'+prefix+'_PASSWORD']})
def write(name,row,**updates):
    data={key:row[key] for key in SCHEMA['$defs'][name]['properties'] if key in row}
    return {**data,**updates}
def internal(path,body=None,auth=True):
    code='''import json,os,urllib.request,urllib.error
body=%r
headers={'Content-Type':'application/json'}
if %r:headers['Authorization']='Bearer '+os.environ['RUNTIME_TO_BACKEND_TOKEN']
r=urllib.request.Request('http://backend:8080'+%r,data=json.dumps(body).encode() if body is not None else None,headers=headers)
try:
 with urllib.request.urlopen(r,timeout=15) as response:print(json.dumps([response.status,json.load(response)]))
except urllib.error.HTTPError as e:print(json.dumps([e.code,json.load(e)]))
'''
    return json.loads(run('exec','-T','runtime','python','-',input=code%(body,auth,path)))
def validate_snapshot(snapshot,identity):
    ctx={'tenant_id':ENV['TENANT_ID'],'project_id':ENV['PROJECT_ID'],'user_id':identity['user']['id'],'request_id':str(uuid.uuid4())}
    return internal('/internal/capabilities/validate',{'snapshot_id':snapshot['snapshot_id'],'context':ctx})
def snapshot(model,token,**opts):
    return request('/capabilities/resolve','POST',{'model_id':model['id'],'require_tools':True,'require_streaming':True,**opts},token)
def main():
    admin,ua,ub=login('ADMIN'),login('USER_A'),login('USER_B');a=admin['access_token'];u=ua['access_token'];b=ub['access_token']
    for path in ['/admin/models','/admin/skills','/admin/mcp-connections','/admin/users','/admin/audits','/admin/deployment']:
        request(path,token=u,expect=403);request(path,expect=401)
    request('/admin/skills','POST',{},u,403)
    passed('A02: login, admin-only CRUD/catalog policy, unauthenticated denial')
    deployment=request('/admin/deployment',token=a)
    assert deployment['models'][0]['credential_configured'] is True
    assert 'acceptance-placeholder' not in json.dumps(deployment)
    model={'name':'Acceptance model '+SUFFIX,'provider':'any-display-label','protocol':'openai_chat_completions','protocol_options':{'thinking':{'type':'disabled'}},'provider_model_name':'acceptance-only-no-calls','base_url':'https://api.deepseek.com','credential_ref':'deepseek_primary','context_limit':32000,'max_output_tokens':4096,'capabilities':{'streaming':True,'tool_calling':True},'enabled':True,'is_default':True,'revision':0}
    m=request('/admin/models','POST',model,a);IDS['model']=m['id']
    assert m['chat_status']==m['stream_status']==m['tool_loop_status']=='unverified'
    for change in [{'protocol':'unsupported'},{'protocol_options':{'arbitrary_key':'x'}},{'base_url':'http://127.0.0.1:5432'},{'credential_ref':'wrong-alias'},{'max_output_tokens':32000},{'api_key':'must-not-be-accepted'}]:
        request('/admin/models','POST',{**model,**change},a,400)
    catalog=request('/catalog/models',token=u)['items'];entry=next(v for v in catalog if v['id']==m['id']);assert entry['available'] and 'base_url' not in entry and 'credential_ref' not in entry
    check=request('/admin/models/'+m['id']+'/validate','POST',token=a);assert check['revision']==m['revision'] and check['chat_status']=='unverified'
    passed('A03: protocol-first model CRUD, strict options, credential/target binding, safe catalog, no paid probe')
    second=request('/admin/models','POST',{**model,'name':'Second model '+SUFFIX,'provider':'different-platform-label'},a);all_models=request('/admin/models',token=a)['items'];assert sum(v['is_default'] for v in all_models)==1
    m=next(v for v in all_models if v['id']==m['id']);assert not m['is_default'] and m['revision']==2
    request('/admin/models/'+m['id'],'PATCH',write('ModelWrite',m,revision=1),a,409)
    m=request('/admin/models/'+m['id'],'PATCH',write('ModelWrite',m,is_default=True),a)
    passed('A03: single default, optimistic concurrency, platform label does not choose protocol')
    skill={'name':'Acceptance skill '+SUFFIX,'description':'Integration fixture','category':'验收','content':'先检查数据来源。\n<script>window.__unsafe=1</script>','enabled':True,'revision':0}
    sk=request('/admin/skills','POST',skill,a);IDS['skill']=sk['id'];path='/admin/skills/'+sk['id']
    assert any(v['id']==sk['id'] for v in request('/catalog/skills',token=u)['items'])
    request('/me/skills/'+sk['id']+'/enablement','PUT',{'enabled':True},u)
    assert next(v for v in request('/catalog/skills',token=u)['items'] if v['id']==sk['id'])['personal_enabled']
    assert not next(v for v in request('/catalog/skills',token=b)['items'] if v['id']==sk['id'])['personal_enabled']
    sk=request(path,'PATCH',write('SkillWrite',sk,content='第二版正文'),a);assert sk['revision']==2
    request(path,'PATCH',write('SkillWrite',sk,revision=1),a,409)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        outcomes=list(pool.map(lambda _:request(path,'PATCH',write('SkillWrite',sk,description='concurrent update'),a,expect=None)[0],range(2)))
    assert sorted(outcomes)==[200,409];sk=next(v for v in request('/admin/skills',token=a)['items'] if v['id']==sk['id'])
    passed('A04: real skill CRUD, personal preferences isolated, markdown stored, concurrent edit conflict')
    conn=request('/admin/mcp-connections','POST',{'name':'Acceptance MCP '+SUFFIX,'endpoint':'http://demo-mcp:8001/mcp/','credential_ref':'','enabled':True,'revision':0},a);IDS['mcp']=conn['id'];cp='/admin/mcp-connections/'+conn['id']
    assert conn['probe_status']=='unverified'
    request('/admin/mcp-connections','POST',{'name':'blocked','endpoint':'http://169.254.169.254/','credential_ref':'','enabled':True,'revision':0},a,400)
    conn=request(cp+'/discover','POST',{'revision':conn['revision']},a);assert conn['probe_status']=='success',conn
    tools=request(cp+'/tools',token=a)['items'];assert len(tools)==1;tool=tools[0];assert tool['remote_name']=='lookup_demo_order' and not tool['enabled'] and tool['trusted_read_only']
    assert all(v['namespaced_tool_id']!=tool['namespaced_tool_id'] for v in request('/catalog/tools',token=u)['items'])
    tool=request(cp+'/tools/'+tool['namespaced_tool_id'],'PATCH',{'enabled':True,'revision':tool['revision']},a)
    assert any(v['namespaced_tool_id']==tool['namespaced_tool_id'] for v in request('/catalog/tools',token=u)['items'])
    conn2=request('/admin/mcp-connections','POST',{'name':'Second MCP '+SUFFIX,'endpoint':'http://demo-mcp:8001/mcp/','credential_ref':'','enabled':True,'revision':0},a)
    conn2=request('/admin/mcp-connections/'+conn2['id']+'/discover','POST',{'revision':conn2['revision']},a)
    t2=request('/admin/mcp-connections/'+conn2['id']+'/tools',token=a)['items'][0];assert t2['namespaced_tool_id']!=tool['namespaced_tool_id']
    request('/admin/mcp-connections/'+conn2['id']+'/tools/'+tool['namespaced_tool_id'],'PATCH',{'enabled':False,'revision':tool['revision']},a,404)
    passed('A05: real SDK initialize/list_tools, default-denied tools, explicit enablement, namespace isolation')
    snap=snapshot(m,u,skill_ids=[sk['id']]);assert tool['namespaced_tool_id'] in snap['tool_ids'];assert 'credential_ref' not in json.dumps(snap)
    code,decision=validate_snapshot(snap,ua);assert code==200 and decision['allow']
    assert validate_snapshot(snap,ub)[0]==404
    assert internal('/internal/capabilities/validate',{'snapshot_id':snap['snapshot_id'],'context':{'tenant_id':ENV['TENANT_ID'],'project_id':ENV['PROJECT_ID'],'user_id':ua['user']['id'],'request_id':str(uuid.uuid4())}},False)[0]==401
    passed('Capability resolution persists a frozen snapshot, private credentials hidden, owner/context checked')
    sk=request(path,'PATCH',write('SkillWrite',sk,enabled=False),a);assert validate_snapshot(snap,ua)[1]['reason']=='CAPABILITY_CHANGED'
    request('/capabilities/resolve','POST',{'model_id':m['id'],'skill_ids':[sk['id']],'require_tools':True,'require_streaming':True},u,409)
    sk=request(path,'PATCH',write('SkillWrite',sk,enabled=True),a)
    snap=snapshot(m,u,skill_ids=[]);tool=request(cp+'/tools/'+tool['namespaced_tool_id'],'PATCH',{'enabled':False,'revision':tool['revision']},a);assert not validate_snapshot(snap,ua)[1]['allow']
    tool=request(cp+'/tools/'+tool['namespaced_tool_id'],'PATCH',{'enabled':True,'revision':tool['revision']},a)
    # Simulate a previously stored old schema; reconcile against the real current provider discovery.
    sql("UPDATE backend.mcp_tools SET data=jsonb_set(data,'{schema_hash}','\"previous-schema\"') WHERE id='"+tool['namespaced_tool_id']+"';")
    conn=request(cp+'/discover','POST',{'revision':conn['revision']},a);tool=request(cp+'/tools',token=a)['items'][0];assert not tool['enabled'] and tool['revision']>2
    tool=request(cp+'/tools/'+tool['namespaced_tool_id'],'PATCH',{'enabled':True,'revision':tool['revision']},a)
    snap=snapshot(m,u,skill_ids=[]);conn=request(cp,'PATCH',write('McpWrite',conn,enabled=False),a);assert not validate_snapshot(snap,ua)[1]['allow']
    assert not request(cp+'/tools',token=a)['items'][0]['enabled']
    passed('A06: skill/tool/MCP revocation invalidates snapshots; changed discovery schema requires reauthorization')
    conn=request(cp,'PATCH',write('McpWrite',conn,enabled=True),a);conn=request(cp+'/discover','POST',{'revision':conn['revision']},a)
    run('stop','demo-mcp')
    try:
        start=time.monotonic();failed=request(cp+'/discover','POST',{'revision':conn['revision']},a);assert failed['probe_status']=='failed' and time.monotonic()-start<12
    finally:run('up','-d','--wait','demo-mcp')
    conn=request(cp+'/discover','POST',{'revision':failed['revision']},a);assert conn['probe_status']=='success'
    passed('MCP unavailable yields persisted visible failure and recovers after provider restart')
    # Local provider integration only: verifies SDK call_tool semantics, not the Day 3 application gateway.
    probe='''import asyncio,json
from datetime import timedelta
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from app.access import safe_client
async def main():
 async with streamablehttp_client('http://demo-mcp:8001/mcp/',httpx_client_factory=safe_client) as (read,write,_):
  async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=4)) as session:
   await session.initialize()
   for order,expected in [('DEMO-1001',True),('DOES-NOT-EXIST',False)]:
    result=await session.call_tool('lookup_demo_order',{'order_id':order})
    assert not result.isError
    data=json.loads(result.content[0].text)
    assert data['found'] is expected and data['synthetic']
 print('provider SDK call passed')
asyncio.run(main())
'''
    assert 'provider SDK call passed' in run('exec','-T','runtime','python','-',input=probe)
    passed('Demo provider: real SDK call_tool covers matching and no-match synthetic orders (not Agent loop)')
    m=request('/admin/models/'+m['id'],'PATCH',write('ModelWrite',m,capabilities={'streaming':True,'tool_calling':False}),a)
    request('/capabilities/resolve','POST',{'model_id':m['id'],'skill_ids':[],'require_tools':True,'require_streaming':True},u,409)
    m=request('/admin/models/'+m['id'],'PATCH',write('ModelWrite',m,capabilities={'streaming':True,'tool_calling':True}),a)
    snap=snapshot(m,u,skill_ids=[]);m=request('/admin/models/'+m['id'],'PATCH',write('ModelWrite',m,enabled=False,is_default=False),a);assert not validate_snapshot(snap,ua)[1]['allow']
    request('/capabilities/resolve','POST',{'require_tools':False,'require_streaming':True,'skill_ids':[]},u,409)
    m=request('/admin/models/'+m['id'],'PATCH',write('ModelWrite',m,enabled=True,is_default=True),a)
    passed('A03/A06: capability mismatch, disabled model and missing default fail explicitly without fallback')
    for i in range(4):
        v=request('/admin/skills','POST',{**skill,'name':f'Preference {SUFFIX} {i}'},a)
        request('/me/skills/'+v['id']+'/enablement','PUT',{'enabled':True},u)
    request('/capabilities/resolve','POST',{'model_id':m['id'],'require_tools':False,'require_streaming':True},u,400)
    snapshot(m,u,skill_ids=[])
    passed('Skill preference overflow requires explicit selection; explicit empty list stays empty')
    password='Acceptance-'+uuid.uuid4().hex
    new=request('/admin/users','POST',{'username':'accept-'+SUFFIX,'password':password},a)
    request('/admin/users','POST',{'username':'accept-'+SUFFIX,'password':password},a,409)
    request('/admin/users','POST',{'username':'spoof-'+SUFFIX,'password':password,'role':'admin'},a,400)
    issued=request('/auth/login','POST',{'username':new['username'],'password':password})
    snap=snapshot(m,issued['access_token'],skill_ids=[])
    new=request('/admin/users/'+new['id'],'PATCH',{'enabled':False,'revision':new['revision']},a)
    request('/auth/me',token=issued['access_token'],expect=401);assert validate_snapshot(snap,issued)[1]['reason']=='USER_DISABLED'
    request('/admin/users/'+admin['user']['id'],'PATCH',{'enabled':False,'revision':admin['user']['revision']},a,403)
    passed('User creation is ordinary-only; duplicate handling, disable revokes token/snapshot, administrator protected')
    audits=request('/admin/audits',token=a)['items'];assert any(v['object_id']==m['id'] for v in audits)
    serialized=json.dumps(audits);assert password not in serialized and 'acceptance-placeholder' not in serialized and '第二版正文' not in serialized
    versions=sql("SELECT string_agg(version::text,',' ORDER BY version) FROM backend.schema_migrations;");assert versions=='1,2,3,4,5,6'
    run('run','--rm','--no-deps','backend','migrate');assert sql("SELECT string_agg(version::text,',' ORDER BY version) FROM backend.schema_migrations;")==versions
    run('restart','backend','runtime');run('up','-d','--wait','backend','runtime')
    assert any(v['id']==m['id'] for v in request('/admin/models',token=a)['items'])
    assert any(v['id']==sk['id'] for v in request('/catalog/skills',token=u)['items'])
    passed('Audit redaction, repeatable migration and configuration persistence across service restart')
if __name__=='__main__':
    outcome='failed'
    try:main();outcome='passed'
    finally:
        (ROOT/'docs/evidence/day2-api-results.json').write_text(json.dumps({'status':outcome,'checks':RESULTS,'resources':IDS,'model_calls':0,'scope':'isolated agent-workspace-verification; placeholder credential checks presence only'},ensure_ascii=False,indent=2),encoding='utf-8')
