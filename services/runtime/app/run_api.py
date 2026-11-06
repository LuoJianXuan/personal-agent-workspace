import asyncio,json,time
from uuid import UUID
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse,StreamingResponse
from .engine import TERMINAL
from .models import RunError
class BoundedStream(StreamingResponse):
    async def __call__(self, scope, receive, send):
        async def bounded_send(message):
            await asyncio.wait_for(send(message),10)
        await super().__call__(scope,receive,bounded_send)
router=APIRouter()

@router.get('/internal/runs/{id}/sources')
async def sources(id:str,request:Request):
    try:
        id=runid(id);await request.app.state.engine.get(id)
        async with request.app.state.pool.connection() as c:rows=await (await c.execute('SELECT data FROM runtime.sources WHERE run_id=%s ORDER BY created_at,source_id',(id,))).fetchall()
        return {'items':[r['data'] for r in rows]}
    except RunError as e:return error(request,e.code,404)
def error(request,code,status):return JSONResponse({'code':code,'message':code,'request_id':request.state.request_id},status_code=status,headers={'Retry-After':'3'} if status==429 else {})
def runid(value):
    try:return str(UUID(value))
    except ValueError:raise RunError('NOT_FOUND') from None
@router.post('/internal/runs')
async def start(request:Request):
    try:
        raw=await request.body()
        if len(raw)>262144:return error(request,'INVALID_ARGUMENT',400)
        result=await request.app.state.engine.accept(json.loads(raw))
        return JSONResponse({k:result[k] for k in ('run_id','thread_id','status','mode')},status_code=202)
    except RunError as e:return error(request,e.code,429 if e.code=='RESOURCE_EXHAUSTED' else 409)
    except Exception:return error(request,'INVALID_ARGUMENT',400)
@router.get('/internal/runs/{id}')
async def get(id:str,request:Request):
    try:return await request.app.state.engine.get(runid(id))
    except RunError as e:return error(request,e.code,404)
@router.get('/internal/runs/{id}/events')
async def events(id:str,request:Request,after_seq:int=0):
    if after_seq<0:return error(request,'INVALID_ARGUMENT',400)
    try:
        id=runid(id);await request.app.state.engine.get(id)
        return await request.app.state.engine.events(id,after_seq)
    except RunError as e:return error(request,e.code,404)
@router.get('/internal/runs/{id}/stream')
async def stream(id:str,request:Request,after_seq:int=0):
    engine=request.app.state.engine
    if after_seq<0:return error(request,'INVALID_ARGUMENT',400)
    try:id=runid(id);await engine.get(id)
    except RunError as e:return error(request,e.code,404)
    if engine.streams>=32:return error(request,'RESOURCE_EXHAUSTED',429)
    engine.streams+=1
    async def generate():
        seq=after_seq;heartbeat=time.monotonic()
        try:
            yield ': connected\n\n'
            while not await request.is_disconnected():
                page=await engine.events(id,seq)
                for event in page['items']:
                    yield 'id: '+str(event['seq'])+'\ndata: '+json.dumps(event,ensure_ascii=False)+'\n\n'
                    seq=event['seq']
                if not page['has_more']:
                    if (await engine.get(id))['status'] in TERMINAL:
                        # Re-read after terminal observation: completion may have committed after prior page.
                        last=await engine.events(id,seq)
                        if not last['items']:return
                        continue
                    if time.monotonic()-heartbeat>=15:yield ': heartbeat\n\n';heartbeat=time.monotonic()
                    await asyncio.sleep(.1)
        finally:engine.streams-=1
    return BoundedStream(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@router.get('/internal/runs/{id}/approvals')
async def approvals(id:str,request:Request):
    try:
        id=runid(id);await request.app.state.engine.get(id)
        return await request.app.state.engine.approvals.list(id)
    except RunError as e:return error(request,e.code,404)
@router.get('/internal/approvals/{id}')
async def proposal(id:str,request:Request):
    try:return await request.app.state.engine.approvals.get_published(runid(id))
    except RunError as e:return error(request,e.code,404)
@router.post('/internal/runs/{id}/resume')
async def resume(id:str,request:Request):
    from contracts.validate import validate
    try:
        p=await request.json();validate('Resume',p)
        return await request.app.state.engine.approvals.resume(runid(id),p['decision_id'])
    except RunError as e:return error(request,e.code,429 if e.code=='RESOURCE_EXHAUSTED' else 409)
    except Exception:return error(request,'INVALID_ARGUMENT',400)
@router.post('/internal/runs/{id}/cancel')
async def cancel(id:str,request:Request):
    from contracts.validate import validate
    try:
        p=await request.json();validate('Cancel',p)
        return await request.app.state.engine.cancel(runid(id),p['command_id'])
    except RunError as e:return error(request,e.code,409)
    except Exception:return error(request,'INVALID_ARGUMENT',400)

@router.post('/internal/runs/{id}/artifacts')
async def artifacts(id:str,request:Request):
    from .materials import export_report
    try:return await export_report(request.app.state.engine,runid(id),request.query_params.get('format','markdown'))
    except RunError as e:return error(request,e.code,409 if e.code=='RUN_NOT_COMPLETED' else 503)
    except Exception:return error(request,'ARTIFACT_UNAVAILABLE',503)
