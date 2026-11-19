"""Authorized McDonald's authentication failure and bounded worker timeout."""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.access import discover, run_worker

ENDPOINT = "https://mcp.mcd.cn"
CREDENTIAL = "mcd_mcp_token"


async def main():
    assert os.environ.get("WORKSPACE_MCD_AUTHORIZED") == "true"
    started = time.monotonic()
    try:
        # Use the same child-process boundary as the Runtime API. Raw SDK
        # response details stay in the child; only the stable safe code exits.
        await discover(ENDPOINT, CREDENTIAL)
        raise AssertionError("invalid credential unexpectedly succeeded")
    except ValueError as error:
        assert str(error) == "MCP_UNAVAILABLE"
    auth_elapsed = time.monotonic() - started
    assert auth_elapsed < 15, auth_elapsed

    started = time.monotonic()
    try:
        await run_worker(
            {
                "endpoint": ENDPOINT,
                "credential_ref": CREDENTIAL,
                "name": "now-time-info",
                "arguments": {},
                "access_mode": "read",
                "requires_approval": False,
            },
            command=[sys.executable, "-c", "import time;time.sleep(30)"],
            deadline=0.35,
        )
        raise AssertionError("stuck worker unexpectedly completed")
    except TimeoutError as error:
        assert str(error) == "TOOL_TIMEOUT"
    timeout_elapsed = time.monotonic() - started
    assert timeout_elapsed < 2, timeout_elapsed
    result = {
        "status": "passed",
        "invalid_token_error": "MCP_UNAVAILABLE",
        "invalid_token_elapsed_seconds": round(auth_elapsed, 3),
        "timeout_error": "TOOL_TIMEOUT",
        "timeout_elapsed_seconds": round(timeout_elapsed, 3),
        "safe_error_only": True,
        "real_model_calls": 0,
        "real_mcp_read_calls": 0,
        "real_mcp_write_calls": 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    root = Path(__file__).resolve().parents[1]
    (root / "docs/evidence/mcp-preclose-fault-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
