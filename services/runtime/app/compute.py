"""Scoped bridge to an explicitly enabled, trusted compute launcher."""
import base64,json,os
import httpx
from .models import RunError,safe_text
from .materials import publish_binary

async def compute(engine,start,args,eid):
    if not engine.compute_enabled():raise RunError('COMPUTE_NOT_CONFIGURED')
    inputs=[]
    for file_id in args['file_ids']:
        if not any(f['id']==file_id for f in start['file_refs']):raise RunError('FILE_NOT_AUTHORIZED')
        r=await engine.backend.get('/internal/files/'+file_id+'/blob',params={'run_id':start['run_id']})
        if r.status_code!=200:raise RunError('FILE_UNAVAILABLE')
        inputs.append({'id':file_id,'content':base64.b64encode(r.content).decode()})
    root=os.environ['COMPUTE_BROKER_URL'].rstrip('/')
    # Not supplied by the model, and never place this token in graph state.
    async with httpx.AsyncClient(base_url=root,headers={'Authorization':'Bearer '+os.environ['COMPUTE_BROKER_TOKEN']},trust_env=False,follow_redirects=False,timeout=45) as client:
        try:
            response=await client.post('/jobs',json={'execution_id':eid,'run_id':start['run_id'],'code':args['code'],'files':inputs})
            if response.status_code!=200:raise RunError('COMPUTE_FAILED')
            data=response.json()
            if data.get('error'):raise RunError(data['error'])
            files=[]
            for i,item in enumerate(data['files']):
                raw=base64.b64decode(item['content'],validate=True)
                files.append(await publish_binary(engine,start['run_id'],f'compute-{eid}-{i}',item['name'],item['media_type'],raw))
            return json.dumps({'completed':True,'stdout':safe_text(data.get('stdout','')),'stderr':safe_text(data.get('stderr','')),'files':files},ensure_ascii=False)
        except httpx.TimeoutException:raise RunError('COMPUTE_TIMEOUT') from None
        finally:
            # Cancellation also reaches the actual container; a closed stream alone is insufficient.
            try:await client.delete('/jobs/'+eid,timeout=5)
            except Exception:pass
