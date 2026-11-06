"""Short-lived transport worker. Tool authorization stays in ToolGatewayService."""
import asyncio,json,os,sys
from datetime import timedelta
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from .access import target,safe_client
async def main(p):
    item=target('mcp',p['endpoint'],p['credential_ref'])
    if p['name'] not in item.get('read_only_tools',[]):raise ValueError('APPROVAL_FLOW_NOT_READY')
    headers={}
    if p['credential_ref']:headers['Authorization']='Bearer '+os.environ[item['env_var']]
    async with streamablehttp_client(p['endpoint'],headers=headers,timeout=timedelta(seconds=3),sse_read_timeout=timedelta(seconds=15),httpx_client_factory=safe_client) as (r,w,_):
        async with ClientSession(r,w,read_timeout_seconds=timedelta(seconds=15)) as session:
            await session.initialize()
            result=await session.call_tool(p['name'],p['arguments'])
            text='\n'.join(c.text for c in result.content if c.type=='text')
            if len(text.encode())>32768:raise ValueError('TOOL_RESULT_TOO_LARGE')
            if result.isError:raise ValueError('MCP_TOOL_FAILED')
            return {'text':text}
if __name__=='__main__':
    try:print(json.dumps(asyncio.run(main(json.load(sys.stdin))),ensure_ascii=False))
    except Exception:sys.exit(1)
