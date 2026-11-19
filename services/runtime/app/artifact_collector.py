"""Single Runtime publication boundary. Backend owns IDs, lineage and storage."""
import asyncio,hashlib,json
from dataclasses import dataclass
from pathlib import PurePosixPath
from contracts.validate import validate
from .models import RunError

@dataclass(frozen=True)
class CandidateArtifact:
    name:str
    media_type:str
    content:bytes
    sha256:str
    @property
    def size(self):return len(self.content)

class ArtifactCollector:
    def __init__(self,engine,run,execution=None):
        self.engine=engine;self.run=run;self.execution=execution
    async def publish(self,key,candidate,parent=None,binary=True):
        if asyncio.current_task().cancelling():raise asyncio.CancelledError()
        name=candidate.name
        if not name or len(name)>120 or '/' in name or '\\' in name or PurePosixPath(name).name!=name or name in ('.','..'):
            raise RunError('COMPUTE_OUTPUT_INVALID')
        allowed={'text/plain','text/markdown','text/csv','application/json','application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
        if candidate.media_type not in allowed:raise RunError('COMPUTE_OUTPUT_INVALID')
        validate('CandidateArtifact',{'name':name,'media_type':candidate.media_type,'size':candidate.size,'sha256':candidate.sha256})
        if hashlib.sha256(candidate.content).hexdigest()!=candidate.sha256:raise RunError('FILE_INTEGRITY_ERROR')
        # Recheck cancellation/authorization after execution, before publication.
        async with self.engine.pool.connection() as c:
            row=await (await c.execute('SELECT cancel_requested FROM runtime.runs WHERE run_id=%s',(self.run,))).fetchone()
            if row and row['cancel_requested']:raise RunError('RUN_CANCELLED')
        meta={'run_id':self.run,'artifact_key':key,'name':name,'media_type':candidate.media_type,'sha256':candidate.sha256,'size':candidate.size}
        if parent:meta['parent_file_id']=parent
        if self.execution:meta['execution_id']=self.execution
        if binary:
            r=await self.engine.backend.post('/internal/artifacts/blob',headers={'X-Artifact-Metadata':json.dumps(meta,ensure_ascii=True)},content=candidate.content)
        else:
            r=await self.engine.backend.post('/internal/artifacts',json={**meta,'content':candidate.content.decode('utf-8')})
        if r.status_code!=200:
            code=r.json().get('code','ARTIFACT_STORAGE_FAILED') if r.headers.get('content-type','').startswith('application/json') else 'ARTIFACT_STORAGE_FAILED'
            raise RunError(code)
        file=r.json();validate('File',file)
        if file['status']!='READY':raise RunError('ARTIFACT_NOT_READY')
        async with self.engine.pool.connection() as c:
            async with c.transaction():
                row=await (await c.execute('INSERT INTO runtime.artifact_events(run_id,artifact_key,file_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING file_id',(self.run,key,file['id']))).fetchone()
                if row:await self.engine.event_on(c,self.run,'artifact.ready',file)
        return file
