"""Trusted launcher, opt-in Compose profile. Never executes generated code itself."""
import asyncio,base64,hashlib,hmac,io,json,logging,os,tarfile,time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
import httpx
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field
from .errors import safe_text

NAMESPACE=os.getenv('COMPUTE_NAMESPACE','agent-workspace-compute')
IMAGE=os.getenv('COMPUTE_RUNNER_IMAGE','agent-workspace-python-runner:phase1')
STATE=Path('/state');slots=asyncio.Semaphore(1);active={}
class LaunchError(Exception):pass
def checked(response,status,code):
    if response.status_code!=status:
        logging.warning('compute stage=%s status=%s detail=%s',code,response.status_code,safe_text(response.text)[:500])
        raise LaunchError(code)
def docker_client():return httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds='/var/run/docker.sock'),base_url='http://docker',timeout=40)
def job_name(eid):return 'aw-'+hashlib.sha256(NAMESPACE.encode()).hexdigest()[:10]+'-'+str(UUID(eid))
def archive(name,data):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w') as tar:
        info=tarfile.TarInfo(name);info.size=len(data);info.uid=10001;info.gid=10001;info.mode=0o600;tar.addfile(info,io.BytesIO(data))
    return out.getvalue()
async def remove(client,name):
    inspected=await client.get('/containers/'+name+'/json')
    if inspected.status_code!=404:
        if inspected.status_code!=200 or inspected.json().get('Config',{}).get('Labels',{}).get('agent.workspace.compute')!=NAMESPACE:raise ValueError('CONTAINER_SCOPE_DENIED')
        deleted=await client.delete('/containers/'+name,params={'force':'true','v':'true'})
        if deleted.status_code not in (204,404):raise ValueError('COMPUTE_CLEANUP_FAILED')
    await remove_volume(client,name+'-work')

async def remove_volume(client,name):
    volume=await client.get('/volumes/'+name)
    if volume.status_code==404:return
    if volume.status_code!=200 or volume.json().get('Labels',{}).get('agent.workspace.compute')!=NAMESPACE:raise ValueError('VOLUME_SCOPE_DENIED')
    deleted=await client.delete('/volumes/'+name)
    if deleted.status_code not in (204,404):raise ValueError('COMPUTE_CLEANUP_FAILED')

@asynccontextmanager
async def lifespan(app):
    if len(os.getenv('COMPUTE_BROKER_TOKEN',''))<32:raise RuntimeError('COMPUTE_BROKER_TOKEN_REQUIRED')
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    # Only this stack's labelled jobs are reclaimed after launcher restart.
    async with docker_client() as client:
        r=await client.get('/containers/json',params={'all':'true','filters':json.dumps({'label':['agent.workspace.compute='+NAMESPACE]})})
        r.raise_for_status()
        for item in r.json():await remove(client,item['Id'])
        volumes=await client.get('/volumes',params={'filters':json.dumps({'label':['agent.workspace.compute='+NAMESPACE]})})
        volumes.raise_for_status()
        for volume in volumes.json().get('Volumes') or []:await remove_volume(client,volume['Name'])
    for f in STATE.glob('*.json'):
        if f.is_file() and time.time()-f.stat().st_mtime>86400:f.unlink()
    yield

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
@app.middleware('http')
async def auth(request,call_next):
    if not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+os.environ.get('COMPUTE_BROKER_TOKEN','')):return JSONResponse({'error':'UNAUTHENTICATED'},401)
    return await call_next(request)
class InputFile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:UUID
    content:str=Field(max_length=7*1024*1024)
class Job(BaseModel):
    model_config=ConfigDict(extra='forbid')
    execution_id:UUID
    run_id:UUID
    code:str=Field(max_length=30000)
    files:list[InputFile]=Field(max_length=3)

@app.post('/jobs')
async def execute(request:Request):
    buf=bytearray()
    async for part in request.stream():
        buf.extend(part)
        if len(buf)>22*1024*1024:return JSONResponse({'error':'COMPUTE_INPUT_LIMIT'},413)
    try:job=Job.model_validate_json(buf)
    except Exception:return JSONResponse({'error':'INVALID_ARGUMENT'},400)
    eid=str(job.execution_id);name=job_name(eid);digest=hashlib.sha256(buf).hexdigest();record=STATE/(eid+'.json');cancelled=STATE/(eid+'.cancel')
    async with slots:
        if cancelled.exists():return JSONResponse({'error':'COMPUTE_CANCELLED'},409)
        if record.exists():
            saved=json.loads(record.read_text())
            if saved['hash']!=digest:return JSONResponse({'error':'IDEMPOTENCY_CONFLICT'},409)
            return saved['result']
        if (STATE/(eid+'.pending')).exists():return JSONResponse({'error':'OUTCOME_UNKNOWN'},409)
        try:
            for f in job.files:
                if len(base64.b64decode(f.content,validate=True))>5*1024*1024:raise ValueError()
        except Exception:return JSONResponse({'error':'COMPUTE_INPUT_LIMIT'},400)
        pending=STATE/(eid+'.pending');pending.write_text(digest)
        result={'error':'COMPUTE_FAILED','files':[],'stdout':'','stderr':''}
        async with docker_client() as client:
            try:
                if cancelled.exists():raise ValueError('COMPUTE_CANCELLED')
                # Docker archive PUT rejects rootfs-readonly containers' Tmpfs paths.
                # A private local tmpfs volume is an explicit writable mount, keeps
                # the rootfs readonly, and exposes no host directory or credentials.
                volume=name+'-work'
                created=await client.post('/volumes/create',json={'Name':volume,'Driver':'local',
                    'DriverOpts':{'type':'tmpfs','device':'tmpfs','o':'size=67108864,uid=10001,gid=10001,mode=0700,noexec,nosuid,nodev'},
                    'Labels':{'agent.workspace.compute':NAMESPACE,'agent.workspace.execution':eid}})
                checked(created,201,'COMPUTE_CREATE_FAILED')
                if cancelled.exists():raise ValueError('COMPUTE_CANCELLED')
                settings={'Image':IMAGE,'User':'10001:10001','WorkingDir':'/work','NetworkDisabled':True,
                    'Labels':{'agent.workspace.compute':NAMESPACE,'agent.workspace.execution':eid,'agent.workspace.request':digest},
                    'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],
                        'Memory':512*1024*1024,'MemorySwap':512*1024*1024,'NanoCpus':1000000000,'PidsLimit':64,
                        'Mounts':[{'Type':'volume','Source':volume,'Target':'/work','ReadOnly':False,'VolumeOptions':{'NoCopy':True}}],
                        'Tmpfs':{'/tmp':'rw,noexec,nosuid,nodev,size=8388608'},
                        'Ulimits':[{'Name':'cpu','Soft':30,'Hard':30},{'Name':'fsize','Soft':16*1024*1024,'Hard':16*1024*1024}],
                        'LogConfig':{'Type':'none'}}}
                r=await client.post('/containers/create',params={'name':name},json=settings)
                checked(r,201,'COMPUTE_CREATE_FAILED')
                active[eid]=name
                if cancelled.exists():raise ValueError('COMPUTE_CANCELLED')
                r=await client.post('/containers/'+name+'/start');checked(r,204,'COMPUTE_START_FAILED')
                if cancelled.exists():raise ValueError('COMPUTE_CANCELLED')
                # The trusted runner waits for job.json in its mounted tmpfs.
                r=await client.put('/containers/'+name+'/archive',params={'path':'/work'},content=archive('job.json',job.model_dump_json().encode()),headers={'Content-Type':'application/x-tar'});checked(r,200,'COMPUTE_INPUT_TRANSFER_FAILED')
                # Read tmpfs output while the trusted wrapper is alive. Stopping a
                # container first would discard its tmpfs output.
                async with asyncio.timeout(35):
                    while True:
                        if cancelled.exists():raise ValueError('COMPUTE_CANCELLED')
                        r=await client.get('/containers/'+name+'/archive',params={'path':'/work/result.json'})
                        if r.status_code==200:break
                        await asyncio.sleep(.3)
                if len(r.content)>16*1024*1024:raise ValueError('OUTPUT_LIMIT')
                with tarfile.open(fileobj=io.BytesIO(r.content)) as tar:
                    member=next((m for m in tar.getmembers() if m.name=='result.json' and m.isfile() and m.size<=15*1024*1024),None)
                    if member is None:raise ValueError('OUTPUT_INVALID')
                    result=json.load(tar.extractfile(member))
                if not isinstance(result,dict) or not isinstance(result.get('files'),list) or len(result['files'])>5:raise ValueError('OUTPUT_INVALID')
                total=0
                for item in result['files']:
                    if not isinstance(item.get('name'),str) or Path(item['name']).name!=item['name'] or '/' in item['name'] or '\\' in item['name'] or len(item['name'])>120:raise ValueError('OUTPUT_INVALID')
                    raw=base64.b64decode(item['content'],validate=True);total+=len(raw)
                    if len(raw)>5*1024*1024 or total>10*1024*1024:raise ValueError('OUTPUT_LIMIT')
                result['stdout']=str(result.get('stdout',''))[:65536];result['stderr']=str(result.get('stderr',''))[:65536]
            except asyncio.TimeoutError:result['error']='COMPUTE_TIMEOUT'
            except Exception as error:result={'error':'COMPUTE_CANCELLED' if cancelled.exists() else str(error) if isinstance(error,LaunchError) else 'COMPUTE_FAILED','files':[],'stdout':'','stderr':''}
            finally:
                try:await remove(client,name)
                except Exception:result['error']='COMPUTE_CLEANUP_FAILED'
                active.pop(eid,None)
        tmp=record.with_suffix('.tmp');tmp.write_text(json.dumps({'hash':digest,'result':result}),encoding='utf-8');tmp.replace(record);pending.unlink(missing_ok=True)
        return result

@app.delete('/jobs/{eid}')
async def cancel(eid:str):
    try:eid=str(UUID(eid));name=job_name(eid)
    except ValueError:return JSONResponse({'error':'INVALID_ARGUMENT'},400)
    # Persist before inspecting Docker: a queued/not-yet-created job must also stop.
    (STATE/(eid+'.cancel')).touch(mode=0o600,exist_ok=True)
    async with docker_client() as client:
        try:await remove(client,name)
        except Exception:return JSONResponse({'error':'COMPUTE_CLEANUP_PENDING'},503)
    return {'cancel_requested':True}
