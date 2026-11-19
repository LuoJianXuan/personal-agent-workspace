"""Short-lived transport worker. Tool authorization stays in ToolGatewayService."""
import asyncio,json,os,sys
from datetime import timedelta
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from .access import target,safe_client,tool_access
from .personal_mcp import authentication_failed, safe_result
async def main(p):
    token = p.get("token")
    item=target('mcp',p['endpoint'],p['credential_ref'],personal=token is not None)
    access_mode,requires_approval=tool_access(item,p['name'],personal=token is not None)
    if access_mode=='blocked' or access_mode!=p.get('access_mode') or requires_approval!=bool(p.get('requires_approval')):raise ValueError('TOOL_DENIED')
    headers={}
    if p['credential_ref']:headers['Authorization']='Bearer '+(token if token is not None else os.environ[item['env_var']])
    async with streamablehttp_client(p['endpoint'],headers=headers,timeout=timedelta(seconds=3),sse_read_timeout=timedelta(seconds=15),httpx_client_factory=safe_client) as (r,w,_):
        async with ClientSession(r,w,read_timeout_seconds=timedelta(seconds=15)) as session:
            await session.initialize()
            result=await session.call_tool(p['name'],p['arguments'])
            text='\n'.join(c.text for c in result.content if c.type=='text')
            if len(text.encode())>32768:raise ValueError('TOOL_RESULT_TOO_LARGE')
            if result.isError:raise ValueError('MCP_TOOL_FAILED')
            return {'text':safe_result(text, token) if token else text}
if __name__=='__main__':
    payload = json.load(sys.stdin)
    try:
        result = asyncio.run(main(payload))
    except Exception as error:
        if "token" not in payload:
            sys.exit(1)
        code = "CONNECTION_AUTH_REQUIRED" if authentication_failed(error) else "MCP_UNAVAILABLE"
        if payload.get("requires_approval") and code != "CONNECTION_AUTH_REQUIRED":
            code = "OUTCOME_UNKNOWN"
        result = {"error": code}
    print(json.dumps(result, ensure_ascii=False), flush=True)
