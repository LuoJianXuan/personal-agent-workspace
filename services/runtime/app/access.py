"""Deployment allowlist and SDK transport boundary; no provider calls for config checks."""
import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# The SDK can log raw upstream exception bodies. Only our safe error codes leave this boundary.
logging.getLogger("mcp").setLevel(logging.CRITICAL)

def policy():
    return json.loads(Path(os.environ.get("ACCESS_POLICY_PATH", "/config/targets.json")).read_text(encoding="utf-8"))

def target(kind, endpoint, credential_ref, *, personal=False):
    parsed = urlsplit(endpoint)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("TARGET_DENIED")
    for item in policy()[kind]:
        if item["endpoint"] == endpoint and item["credential_ref"] == credential_ref:
            if kind == "mcp" and bool(item.get("personal_connector")) != personal:
                continue
            local_demo = kind == "mcp" and endpoint == "http://demo-mcp:8001/mcp/"
            local_fixture = kind == "mcp" and endpoint == "http://personal-mcp-fixture:8004/mcp/" and item.get("test_only") is True
            if parsed.scheme != "https" and not (local_demo or local_fixture):
                raise ValueError("TARGET_DENIED")
            return item
    raise ValueError("TARGET_DENIED")

def configuration_status():
    return {kind: [{"endpoint": t["endpoint"], "credential_ref": t["credential_ref"],
        "credential_configured": not t["credential_ref"] or bool(os.getenv(t["env_var"], ""))}
        for t in policy()[kind] if not t.get("personal_connector")] for kind in ("models", "mcp")}

def tool_access(item, name, *, personal=False):
    if name in item.get("blocked_tools", []):
        return "blocked", False
    if name in item.get("read_only_tools", []):
        return "read", False
    if name in item.get("approval_required_tools", []):
        return "write", True
    if personal:
        return "write", True
    return "blocked", False

def safe_client(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(headers=headers, timeout=timeout, auth=auth,
        follow_redirects=False, trust_env=False, limits=httpx.Limits(max_connections=4))

async def discover_in_process(endpoint, credential_ref, token=None):
    item = target("mcp", endpoint, credential_ref, personal=token is not None)
    headers = {}
    if credential_ref:
        key = token if token is not None else os.getenv(item["env_var"], "")
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
                        unsupported = False
                        try:
                            Draft202012Validator.check_schema(tool.inputSchema)
                            if tool.inputSchema.get("type") != "object":
                                raise ValueError("INVALID_TOOL_SCHEMA")
                            schema_text = json.dumps(tool.inputSchema)
                            if '"$ref"' in schema_text or '"$dynamicRef"' in schema_text:
                                raise ValueError("UNSUPPORTED_SCHEMA_REFERENCE")
                        except (ValueError, SchemaError):
                            if token is None:
                                raise
                            unsupported = True
                        access_mode, _ = tool_access(item, tool.name, personal=token is not None)
                        annotations = getattr(tool, "annotations", None)
                        hint = getattr(annotations, "readOnlyHint", None) if annotations is not None else None
                        discovered = {"remote_name":tool.name,"description":(tool.description or "")[:2000],
                            "input_schema":tool.inputSchema if not unsupported else {"type": "object"},"trusted_read_only":access_mode == "read" and not unsupported,
                            "server_read_only_hint":hint if isinstance(hint, bool) else False,
                            "server_hint_present":isinstance(hint, bool)}
                        if unsupported:
                            discovered["unsupported_schema"] = True
                        if token is not None:
                            remote_definition = tool.model_dump(mode="json", exclude_none=True)
                            canonical = json.dumps(remote_definition, sort_keys=True, ensure_ascii=False).encode()
                            discovered["provider_fingerprint"] = hashlib.sha256(canonical).hexdigest()
                        tools.append(discovered)
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

async def run_worker(payload, *, command=None, deadline=6, private=False):
    env = None
    if private:
        env = {name: os.environ[name] for name in ("ACCESS_POLICY_PATH", "PATH", "SYSTEMROOT", "SSL_CERT_FILE", "SSL_CERT_DIR", "LANG") if name in os.environ}
    process = await asyncio.create_subprocess_exec(
        *(command or [sys.executable, "-m", "app.mcp_worker"]),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, limit=262145, env=env)
    try:
        try:
            async with asyncio.timeout(deadline):
                process.stdin.write(json.dumps(payload).encode())
                await process.stdin.drain()
                process.stdin.close()
                # Take the flushed result without waiting for MCP session cleanup.
                output = await process.stdout.readline()
        except TimeoutError:
            raise TimeoutError("TOOL_TIMEOUT") from None
        if not output or len(output) > 262144:
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
        # Discovery can return a large catalog and pays the cold Python/MCP SDK
        # import cost. Keep it bounded, but give it a longer budget than a tool
        # call; Backend applies a matching path-specific outer deadline.
        return await run_worker({"endpoint": endpoint, "credential_ref": credential_ref}, deadline=12)


async def discover_personal(material):
    target("mcp", material["endpoint"], material["credential_ref"], personal=True)
    if _discovery_slots.locked():
        raise ValueError("DISCOVERY_BUSY")
    async with _discovery_slots:
        return await run_worker(material, deadline=12, private=True)
