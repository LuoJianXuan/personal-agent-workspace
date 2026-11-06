"""Bounded MCP discovery worker; receives only endpoint and credential reference."""
import asyncio
import json
import sys
from .access import discover_in_process

async def main():
    payload = json.loads(sys.stdin.buffer.read(8192))
    result = await discover_in_process(payload["endpoint"], payload["credential_ref"])
    sys.stdout.write(json.dumps(result))

if __name__ == "__main__":
    asyncio.run(main())
