"""Bounded MCP discovery worker; receives only endpoint and credential reference."""
import asyncio
import json
import sys
from .access import discover_in_process
from .personal_mcp import authentication_failed, contains_secret

async def main():
    payload = json.loads(sys.stdin.buffer.read(8192))
    token = payload.get("token")
    try:
        result = await discover_in_process(payload["endpoint"], payload["credential_ref"], token)
        if token and contains_secret(result, token):
            result = {"error": "MCP_UNSAFE_CATALOG"}
    except Exception as error:
        if not token:
            return
        result = {"error": "CONNECTION_AUTH_REQUIRED" if authentication_failed(error) else "MCP_UNAVAILABLE"}
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(main())
