from contextlib import asynccontextmanager
from hmac import compare_digest
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.base import MIGRATIONS
from psycopg_pool import AsyncConnectionPool
from .config import required, service_token
from .engine import Engine
from .run_api import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.token = service_token()
    pool = AsyncConnectionPool(required("RUNTIME_DATABASE_URL"), min_size=1, max_size=6,
        open=False, timeout=3, kwargs={"autocommit": True, "row_factory": dict_row,
        "options": "-c search_path=runtime -c statement_timeout=3000"})
    await pool.open(wait=True)
    app.state.pool = pool
    checkpoint_pool=AsyncConnectionPool(required("RUNTIME_DATABASE_URL"),min_size=1,max_size=4,open=False,
        kwargs={"autocommit":True,"row_factory":dict_row,"options":"-c search_path=runtime_harness_v2 -c statement_timeout=3000"})
    await checkpoint_pool.open(wait=True)
    engine=Engine(pool,checkpoint_pool); app.state.engine=engine
    await engine.boot()
    try:
        yield
    finally:
        await engine.close()
        await checkpoint_pool.close()
        await pool.close()

app = FastAPI(title="Agent Workspace Runtime", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

@app.middleware("http")
async def authentication(request: Request, call_next):
    request.state.request_id = str(uuid4())
    if not compare_digest(request.headers.get("authorization", ""), "Bearer " + request.app.state.token):
        return JSONResponse({"code":"UNAUTHENTICATED", "message":"Invalid service credential", "request_id":request.state.request_id}, status_code=401)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response

@app.get("/internal/health")
async def health():
    return {"status":"alive"}

@app.get("/internal/ready")
async def ready(request: Request):
    try:
        async with request.app.state.pool.connection() as conn:
            row = await (await conn.execute("SELECT version FROM runtime.schema_migrations WHERE version = 6")).fetchone()
            checkpoint = await (await conn.execute("SELECT to_regclass('runtime_harness_v2.checkpoints') AS table_name")).fetchone()
            version = await (await conn.execute("SELECT max(v) AS v FROM runtime_harness_v2.checkpoint_migrations")).fetchone()
            if not row or not checkpoint or not checkpoint["table_name"] or not version or version["v"] != len(MIGRATIONS) - 1:
                raise RuntimeError("Migration missing")
    except Exception:
        return JSONResponse({"code":"NOT_READY", "message":"Database, migration or checkpoint setup unavailable", "request_id":request.state.request_id}, status_code=503)
    return {"status":"ready"}


from contracts.validate import validate
from .access import configuration_status, discover

@app.get("/internal/configuration/status")
async def config_status():
    return configuration_status()

@app.post("/internal/mcp/discover")
async def discover_endpoint(request: Request):
    try:
        raw = await request.body()
        if len(raw) > 8192:
            raise ValueError()
        payload = await request.json()
        validate("DiscoverRequest", payload)
    except Exception:
        return JSONResponse({"code":"INVALID_ARGUMENT","message":"Invalid discovery request","request_id":request.state.request_id}, status_code=400)
    try:
        result = await discover(payload["endpoint"], payload["credential_ref"])
        validate("DiscoverResult", result)
        return result
    except Exception:
        return JSONResponse({"code":"MCP_UNAVAILABLE","message":"MCP discovery failed or timed out; check deployment allowlist and credentials","request_id":request.state.request_id}, status_code=502)

app.include_router(router)

@app.post('/internal/documents/extract')
async def extract_document(request: Request):
    from contracts.validate import validate
    from .errors import RunError
    import json
    try:
        header=request.headers.get('x-document-metadata','')
        if len(header)>2048:raise ValueError()
        metadata=json.loads(header);validate('DocumentExtractMetadata',metadata)
        body=await request.body()
        if len(body)>5*1024*1024:raise RunError('FILE_TOO_LARGE')
        document=await request.app.state.engine.documents.extract(body,metadata)
        return document
    except RunError as error:
        status=429 if error.code=='DOCUMENT_BUSY' else 422
        return JSONResponse({'code':error.code,'message':error.code,'request_id':request.state.request_id},status_code=status)
    except Exception:
        return JSONResponse({'code':'INVALID_ARGUMENT','message':'Invalid document extraction request','request_id':request.state.request_id},status_code=400)

@app.get('/internal/capabilities/network')
async def network_capabilities():
    import os
    return {'fetch_available':os.getenv('ENABLE_PUBLIC_WEB')=='true',
        'search_available':os.getenv('ENABLE_PUBLIC_WEB')=='true' and bool(os.getenv('TAVILY_API_KEY') and os.getenv('SEARCH_CALL_BUDGET') and os.getenv('SEARCH_CALL_BUDGET_SINCE')),
        'compute_available':Engine.compute_enabled()}
