"""Deployment allowlist and SDK transport boundary; no provider calls for config checks."""
import asyncio
import json
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# The SDK can log raw upstream exception bodies. Only our safe error codes leave this boundary.
logging.getLogger("mcp").setLevel(logging.CRITICAL)

def policy():
    return json.loads(Path(os.environ.get("ACCESS_POLICY_PATH", "/config/targets.json")).read_text(encoding="utf-8"))

def target(kind, endpoint, credential_ref):
    parsed = urlsplit(endpoint)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("TARGET_DENIED")
    for item in policy()[kind]:
        if item["endpoint"] == endpoint and item["credential_ref"] == credential_ref:
            if parsed.scheme != "https" and not (kind == "mcp" and endpoint == "http://demo-mcp:8001/mcp/"):
                raise ValueError("TARGET_DENIED")
            return item
    raise ValueError("TARGET_DENIED")

def configuration_status():
    return {kind: [{"endpoint": t["endpoint"], "credential_ref": t["credential_ref"],
        "credential_configured": not t["credential_ref"] or bool(os.getenv(t["env_var"], ""))}
        for t in policy()[kind]] for kind in ("models", "mcp")}

def safe_client(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(headers=headers, timeout=timeout, auth=auth,
        follow_redirects=False, trust_env=False, limits=httpx.Limits(max_connections=4))

async def discover_in_process(endpoint, credential_ref):
    item = target("mcp", endpoint, credential_ref)
    headers = {}
    if credential_ref:
        key = os.getenv(item["env_var"], "")
        if not key:
            raise ValueError("CREDENTIAL_MISSING")
        headers["Authorization"] = "Bearer " + key
    async with asyncio.timeout(6):
        async with streamablehttp_client(endpoint, headers=headers, timeout=timedelta(seconds=3),
            sse_read_timeout=timedelta(seconds=4), httpx_client_factory=safe_client) as (read, write, _):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=4)) as session:
                await session.initialize()
                tools, names, cursors = [], set(), set()
                cursor = None
                while True:
                    page = await session.list_tools(cursor=cursor)
                    for tool in page.tools:
                        if tool.name in names or len(tools) >= 100 or len(tool.name) > 200:
                            raise ValueError("INVALID_DISCOVERY")
                        names.add(tool.name)
                        Draft202012Validator.check_schema(tool.inputSchema)
                        if tool.inputSchema.get("type") != "object":
                            raise ValueError("INVALID_TOOL_SCHEMA")
                        # Remote schema references must never trigger arbitrary network reads.
                        if '"$ref"' in json.dumps(tool.inputSchema) or '"$dynamicRef"' in json.dumps(tool.inputSchema):
                            raise ValueError("UNSUPPORTED_SCHEMA_REFERENCE")
                        tools.append({"remote_name":tool.name,"description":(tool.description or "")[:2000],
                            "input_schema":tool.inputSchema,"trusted_read_only":tool.name in item.get("read_only_tools", [])})
                    cursor = page.nextCursor
                    if not cursor:
                        break
                    if cursor in cursors:
                        raise ValueError("INVALID_DISCOVERY")
                    cursors.add(cursor)
                result = {"tools":tools}
                if len(json.dumps(result).encode()) > 200000:
                    raise ValueError("DISCOVERY_TOO_LARGE")
                return result


# MCP 1.9.3 transport cleanup can swallow task cancellation while a peer is silent.
# Isolate discovery in a short-lived worker so the total deadline is enforceable.
_discovery_slots = asyncio.Semaphore(4)

async def run_worker(payload, *, command=None, deadline=6):
    process = await asyncio.create_subprocess_exec(
        *(command or [sys.executable, "-m", "app.mcp_worker"]),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(json.dumps(payload).encode()), deadline)
        if process.returncode or len(output) > 262144:
            raise ValueError("MCP_UNAVAILABLE")
        return json.loads(output)
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()

async def discover(endpoint, credential_ref):
    target("mcp", endpoint, credential_ref)
    if _discovery_slots.locked():
        raise ValueError("DISCOVERY_BUSY")
    async with _discovery_slots:
        return await run_worker({"endpoint": endpoint, "credential_ref": credential_ref})
