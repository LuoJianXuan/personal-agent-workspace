"""Runs inside the Runtime container; exercises a real fixed parser child."""
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path

from openpyxl import Workbook

from app import execution
from app.errors import RunError
from app.execution import FixedProcessPool, child_environment


def parser_pids():
    result = []
    for path in Path("/proc").glob("[0-9]*"):
        try:
            args = (path / "cmdline").read_bytes().split(b"\0")
            if len(args) > 2 and args[1:3] == [b"-m", b"app.document_cli"]:
                result.append(int(path.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
            pass
    return result


def xlsx_fixture():
    book = Workbook(write_only=True)
    sheet = book.create_sheet("data")
    for index in range(20_000):
        sheet.append([index, index + 1, index + 2, index + 3, index + 4])
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


async def main():
    assert os.environ.get("WORKSPACE_PHASE1_AUTHORIZED") == "true"
    safe = child_environment()
    assert not any(name in safe for name in (
        "DEEPSEEK_API_KEY", "LANGFUSE_SECRET_KEY", "BACKEND_TO_RUNTIME_TOKEN",
        "RUNTIME_TO_BACKEND_TOKEN", "RUNTIME_DATABASE_URL",
    ))
    data = xlsx_fixture()
    digest = hashlib.sha256(data).hexdigest()

    pool = FixedProcessPool()
    task = asyncio.create_task(pool.run_document(
        data,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "00000000-0000-4000-8000-000000000001",
        digest,
    ))
    for _ in range(1000):
        if parser_pids():
            break
        if task.done():
            raise AssertionError("parser completed before cancellation could be observed")
        await asyncio.sleep(0.002)
    else:
        raise AssertionError("real parser child did not start")
    task.cancel()
    try:
        await task
        raise AssertionError("cancelled parser returned normally")
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(0.05)
    assert not parser_pids() and not pool._slot.locked() and pool._waiting == 0

    original_timeout = execution.PROCESS_TIMEOUT_SECONDS
    execution.PROCESS_TIMEOUT_SECONDS = 0.001
    try:
        try:
            await pool.run_document(
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "00000000-0000-4000-8000-000000000002",
                digest,
            )
            raise AssertionError("parser exceeded test timeout without failing")
        except RunError as error:
            assert error.code in {"PARSE_TIMEOUT", "DOCUMENT_BUSY"}, error.code
    finally:
        execution.PROCESS_TIMEOUT_SECONDS = original_timeout
    await asyncio.sleep(0.05)
    assert not parser_pids() and not pool._slot.locked() and pool._waiting == 0
    print(json.dumps({
        "checks": [
            "child environment allowlist excludes deployment credentials",
            "real parser child cancellation kills and waits",
            "real parser timeout kills and releases the only slot",
        ],
        "fixture_bytes": len(data),
        "parser_processes_after": len(parser_pids()),
        "real_model_calls": 0,
        "real_search_calls": 0,
    }))


asyncio.run(main())
