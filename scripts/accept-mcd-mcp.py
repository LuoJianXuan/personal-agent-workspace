"""Real, read-only McDonald's China MCP acceptance. Never invokes mutation tools."""
import asyncio
import hashlib
import json
import os
import sys

from app.access import discover_in_process, run_worker

ENDPOINT = "https://mcp.mcd.cn"
CREDENTIAL = "mcd_mcp_token"
WRITE_TOOLS = {
    "delivery-create-address",
    "create-order",
    "auto-bind-coupons",
    "mall-create-order",
}


async def main():
    discovered = await discover_in_process(ENDPOINT, CREDENTIAL)
    tools = {tool["remote_name"]: tool for tool in discovered["tools"]}
    assert "now-time-info" in tools
    assert WRITE_TOOLS.issubset(tools)
    assert all(not tools[name]["trusted_read_only"] for name in WRITE_TOOLS)
    result = await run_worker(
        {
            "endpoint": ENDPOINT,
            "credential_ref": CREDENTIAL,
            "name": "now-time-info",
            "arguments": {},
            "access_mode": "read",
            "requires_approval": False,
        },
        command=[sys.executable, "-m", "app.tool_worker"],
        deadline=20,
    )
    text = result["text"]
    secret = os.environ.get("MCD_MCP_TOKEN", "")
    assert text and (not secret or secret not in text)
    print(json.dumps({
        "status": "passed",
        "endpoint": ENDPOINT,
        "discovered_tool_count": len(tools),
        "read_tool": "now-time-info",
        "write_tools_discovered_but_not_called": sorted(WRITE_TOOLS),
        "result_bytes": len(text.encode()),
        "result_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "secret_exposed": False,
        "real_model_calls": 0,
        "real_mcp_write_calls": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
