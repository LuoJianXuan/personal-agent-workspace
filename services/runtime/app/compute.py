"""Scoped sandbox input bridge; ArtifactCollector settles all candidate outputs."""
import asyncio,base64,hashlib,json
from .models import RunError
from .artifact_collector import ArtifactCollector
from .sandbox import SandboxTask,executor

async def compute(engine,start,args,eid):
    inputs=[]
    for file_id in args['file_ids']:
        ref=next((f for f in start['file_refs'] if f['id']==file_id),None)
        if not ref:raise RunError('FILE_NOT_AUTHORIZED')
        r=await engine.backend.get('/internal/files/'+file_id+'/blob',params={'run_id':start['run_id']})
        if r.status_code!=200:raise RunError('FILE_UNAVAILABLE')
        if hashlib.sha256(r.content).hexdigest()!=ref['sha256']:raise RunError('FILE_CHANGED')
        inputs.append({'id':file_id,'content':base64.b64encode(r.content).decode()})
    result=await executor().execute(SandboxTask(eid,start['run_id'],args['code'],tuple(inputs)))
    collector=ArtifactCollector(engine,start['run_id'],eid);files=[]
    for i,item in enumerate(result.outputs):
        if asyncio.current_task().cancelling():raise asyncio.CancelledError()
        files.append(await collector.publish(f'compute-{eid}-{i}',item))
    return json.dumps({'completed':True,'stdout':result.stdout,'stderr':result.stderr,'files':files},ensure_ascii=False)
