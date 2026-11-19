"""Provider-neutral sandbox-as-tool contract; current provider is local Docker."""
import asyncio,base64,hashlib,os
from dataclasses import dataclass,asdict,field
from typing import Protocol
import httpx
from .artifact_collector import CandidateArtifact
from .models import RunError,safe_text

@dataclass(frozen=True)
class SandboxLimits:
    wall_seconds:int=35
    cpu_seconds:int=30
    memory_bytes:int=512*1024*1024
    pids:int=64

SandboxOutput=CandidateArtifact

@dataclass(frozen=True)
class SandboxTask:
    execution_id:str
    run_id:str
    code:str
    files:tuple
    limits:SandboxLimits=field(default_factory=SandboxLimits)
@dataclass(frozen=True)
class SandboxResult:
    stdout:str
    stderr:str
    outputs:tuple[CandidateArtifact,...]

class SandboxExecutor(Protocol):
    async def execute(self,task:SandboxTask)->SandboxResult:...
    async def cancel(self,execution_id:str)->bool:...

class LocalDockerExecutor:
    # Broker owns create/upload/execute/collect/destroy as one bounded lease.
    def __init__(self):
        self.root=os.environ['COMPUTE_BROKER_URL'].rstrip('/')
        self.headers={'Authorization':'Bearer '+os.environ['COMPUTE_BROKER_TOKEN']}
    def client(self):
        return httpx.AsyncClient(base_url=self.root,headers=self.headers,trust_env=False,follow_redirects=False,timeout=45)
    async def cancel(self,eid):
        try:
            async with self.client() as c:r=await c.delete('/jobs/'+eid,timeout=5)
            return r.status_code==200 and r.json().get('cancel_requested') is True
        except Exception:return False
    async def execute(self,task):
        try:
            async with self.client() as c:
                r=await c.post('/jobs',json={'execution_id':task.execution_id,'run_id':task.run_id,'code':task.code,'files':list(task.files),'limits':asdict(task.limits)})
            if r.status_code!=200:
                try:code=r.json().get('error','COMPUTE_FAILED')
                except Exception:code='COMPUTE_FAILED'
                raise RunError(code)
            data=r.json()
            if data.get('error'):raise RunError('OUTCOME_UNKNOWN' if data['error']=='COMPUTE_CLEANUP_FAILED' else data['error'])
            if len(data.get('files',[]))>5:raise RunError('COMPUTE_OUTPUT_LIMIT')
            outputs=[];total=0
            for item in data['files']:
                raw=base64.b64decode(item['content'],validate=True);total+=len(raw)
                if len(raw)>5*1024*1024 or total>10*1024*1024:raise RunError('COMPUTE_OUTPUT_LIMIT')
                digest=hashlib.sha256(raw).hexdigest()
                if item.get('sha256',digest)!=digest or item.get('size',len(raw))!=len(raw):raise RunError('FILE_INTEGRITY_ERROR')
                outputs.append(CandidateArtifact(item['name'],item['media_type'],raw,digest))
            return SandboxResult(safe_text(data.get('stdout','')),safe_text(data.get('stderr','')),tuple(outputs))
        except asyncio.CancelledError:
            task_cancel=asyncio.create_task(self.cancel(task.execution_id))
            confirmed=await asyncio.shield(task_cancel)
            if confirmed:raise RunError('COMPUTE_CANCELLED') from None
            raise RunError('OUTCOME_UNKNOWN') from None
        except httpx.TimeoutException:
            if not await self.cancel(task.execution_id):raise RunError('OUTCOME_UNKNOWN') from None
            raise RunError('COMPUTE_TIMEOUT') from None
        except httpx.TransportError:
            raise RunError('OUTCOME_UNKNOWN') from None

def executor():
    provider=os.getenv('SANDBOX_PROVIDER','local_docker')
    if provider!='local_docker':raise RunError('SANDBOX_PROVIDER_UNSUPPORTED')
    if not os.getenv('COMPUTE_BROKER_URL') or not os.getenv('COMPUTE_BROKER_TOKEN'):raise RunError('COMPUTE_NOT_CONFIGURED')
    return LocalDockerExecutor()
