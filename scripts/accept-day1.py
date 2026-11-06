"""Explicitly authorized isolated Day 1 acceptance. Never targets the development DB."""
import subprocess,json,urllib.request,urllib.error,time,base64,hmac,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ENV=dict(line.split('=',1) for line in (ROOT/'.env.test').read_text().splitlines() if '=' in line and not line.startswith('#'))
CMD=['docker','compose','--env-file','.env.test','-p','agent-workspace-verification','-f','compose.yaml','-f','tests/compose/postgres-port.yaml']
results=[]
def run(*args,input=None,ok=True):
 r=subprocess.run(CMD+list(args),cwd=ROOT,input=input,text=True,capture_output=True)
 if ok and r.returncode:raise RuntimeError('Compose command failed: '+ ' '.join(args[:4])+' '+r.stderr[-1500:])
 return r

def passed(name):results.append(name);print('PASS:',name,flush=True)
def sql(query):return run('exec','-T','postgres','psql','-U','workspace_admin','-d','workspace','-At','-v','ON_ERROR_STOP=1',input=query).stdout.strip()
def internal(path,token=True):
 script="""import urllib.request,urllib.error,os
r=urllib.request.Request(%r,headers={'Authorization':'Bearer '+os.environ['BACKEND_TO_RUNTIME_TOKEN']} if %r else {})
try:
 with urllib.request.urlopen(r,timeout=8) as res: print(res.status)
except urllib.error.HTTPError as e: print(e.code)
"""%(path,token)
 return int(run('exec','-T','runtime','python','-',input=script).stdout.strip())
def http(path,body=None,token=None):
 headers={'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 req=urllib.request.Request('http://127.0.0.1:5174'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=20) as r:return r.status,r.read().decode()
 except urllib.error.HTTPError as e:return e.code,e.read().decode()
def login(prefix):
 status,body=http('/api/auth/login',{'username':ENV['SEED_'+prefix+'_USERNAME'],'password':ENV['SEED_'+prefix+'_PASSWORD']})
 assert status==200,(status,body)
 return json.loads(body)['access_token']
try:
 assert internal('http://backend:8080/health',False)==200
 assert internal('http://backend:8080/ready',False)==503
 assert internal('http://runtime:8000/internal/health')==200
 assert internal('http://runtime:8000/internal/ready')==503
 passed('pre-migration health=200 ready=503 on both services')
 run('run','--rm','--no-deps','backend','migrate')
 # A version table without checkpoint setup must still be unready.
 sql('CREATE TABLE runtime.schema_migrations(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()); ALTER TABLE runtime.schema_migrations OWNER TO workspace_runtime; INSERT INTO runtime.schema_migrations VALUES(1,now());')
 assert internal('http://runtime:8000/internal/ready')==503
 passed('runtime rejects incomplete checkpoint setup')
 run('run','--rm','--no-deps','runtime','python','-m','app.migrate')
 run('run','--rm','--no-deps','backend','seed')
 run('up','-d','--wait','backend','runtime','web')
 a,b,admin=login('USER_A'),login('USER_B'),login('ADMIN')
 for token in (a,b,admin):assert http('/api/auth/me',token=token)[0]==200
 assert http('/api/admin/users',token=a)[0]==403
 assert len(json.loads(http('/api/admin/users',token=admin)[1])['items'])==3
 assert http('/api/auth/me')[0]==401
 assert http('/api/auth/me',token='invalid')[0]==401
 assert http('/api/auth/login',{'username':'user-a','password':'invalid'})[0]==401
 assert http('/api/auth/login',{'username':'user-a','password':ENV['SEED_USER_A_PASSWORD'],'user_id':'spoof'})[0]==400
 assert http('/internal/health')[0]==404
 passed('three identities, login, admin authorization, invalid auth, unknown fields, public internal-path blocking')
 sql("UPDATE backend.users SET enabled=false WHERE username='user-a';")
 try:assert http('/api/auth/me',token=a)[0]==401
 finally:sql("UPDATE backend.users SET enabled=true WHERE username='user-a';")
 assert http('/api/auth/me',token=a)[0]==200
 passed('disabled account immediately rejects previously issued token; restored afterward')
 def enc(x):return base64.urlsafe_b64encode(json.dumps(x,separators=(',',':')).encode()).decode().rstrip('=')
 payload=json.loads(base64.urlsafe_b64decode(a.split('.')[1]+'==='));payload['exp']=int(time.time())-60
 msg=enc({'alg':'HS256','typ':'JWT'})+'.'+enc(payload)
 expired=msg+'.'+base64.urlsafe_b64encode(hmac.new(ENV['JWT_SECRET'].encode(),msg.encode(),hashlib.sha256).digest()).decode().rstrip('=')
 assert http('/api/auth/me',token=expired)[0]==401
 passed('correctly signed expired token rejected')
 fingerprint=sql("SELECT md5(string_agg(id::text||password_hash,',' ORDER BY id)) FROM backend.users;")
 run('run','--rm','--no-deps','backend','migrate');run('run','--rm','--no-deps','runtime','python','-m','app.migrate')
 run('run','--rm','--no-deps','-e','SEED_USER_A_PASSWORD=Changed-Seed-Only-2026!','backend','seed')
 assert fingerprint==sql("SELECT md5(string_agg(id::text||password_hash,',' ORDER BY id)) FROM backend.users;")
 login('USER_A');passed('repeated migrations and changed seed password preserve existing identities/passwords')
 for role,own,foreign in [('workspace_backend','backend','runtime'),('workspace_runtime','runtime','backend')]:
  assert sql(f"SELECT rolsuper OR rolcreatedb OR rolcreaterole FROM pg_roles WHERE rolname='{role}';")=='f'
  sql(f'BEGIN; SET ROLE {role}; CREATE TABLE {own}.acceptance_probe(id int); INSERT INTO {own}.acceptance_probe VALUES(1); ROLLBACK;')
  r=run('exec','-T','postgres','psql','-U','workspace_admin','-d','workspace','-v','ON_ERROR_STOP=1',input=f'SET ROLE {role}; SELECT * FROM {foreign}.schema_migrations;',ok=False)
  assert r.returncode!=0 and 'permission denied' in r.stderr
 passed('both service roles can write own schema and cannot read foreign schema; no elevated role flags')
 assert internal('http://runtime:8000/internal/health',False)==401
 assert internal('http://backend:8080/internal/health')==401 # Wrong direction token
 passed('missing and wrong-direction service credentials rejected')
 run('stop','postgres')
 try:
  assert internal('http://backend:8080/health',False)==200
  assert internal('http://backend:8080/ready',False)==503
  assert internal('http://runtime:8000/internal/health')==200
  assert internal('http://runtime:8000/internal/ready')==503
 finally:run('up','-d','--wait','postgres')
 for _ in range(20):
  if internal('http://backend:8080/ready',False)==200 and internal('http://runtime:8000/internal/ready')==200:break
  time.sleep(1)
 else:raise AssertionError('readiness did not recover')
 login('USER_A');passed('database outage preserves process health, fails readiness and recovers login')
finally:
 (ROOT/'docs/evidence/day1-api-results.json').write_text(json.dumps({'passed':results},ensure_ascii=False,indent=2),encoding='utf-8')
