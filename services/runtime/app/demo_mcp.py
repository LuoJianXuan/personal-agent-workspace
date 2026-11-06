"""Synthetic read-only provider, isolated from model execution and real business data."""
import json
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse

mcp = FastMCP("Workspace Demo Orders", host="0.0.0.0", port=8001,
    stateless_http=True, json_response=True, streamable_http_path="/mcp/")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
def lookup_demo_order(order_id: str) -> str:
    """Look up synthetic order DEMO-1001 or DEMO-1002; never accesses real customer data."""
    orders = {"DEMO-1001": {"status":"shipped","amount":128,"currency":"CNY"},
        "DEMO-1002":{"status":"processing","amount":256,"currency":"CNY"}}
    item = orders.get(order_id)
    return json.dumps({"found":item is not None,"order_id":order_id,"order":item,"synthetic":True})

@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"status":"ready","data":"synthetic"})

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
