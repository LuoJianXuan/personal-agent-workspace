"""Bounded lifecycle for fixed local subprocesses; never accepts shell commands."""
import asyncio
import os
import sys

from .errors import RunError

MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 35


def child_environment() -> dict[str, str]:
    allowed = {
        "PATH", "PYTHONPATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
        "LANG", "LC_ALL", "PYTHONDONTWRITEBYTECODE",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


class FixedProcessPool:
    """One active parser and at most four in-memory waiters per Runtime process."""

    def __init__(self, waiters: int = 4):
        self._slot = asyncio.Semaphore(1)
        self._state_lock = asyncio.Lock()
        self._waiting = 0
        self._max_waiters = waiters

    async def _acquire(self) -> None:
        waiting = False
        async with self._state_lock:
            if self._slot.locked():
                if self._waiting >= self._max_waiters:
                    raise RunError("DOCUMENT_BUSY")
                self._waiting += 1
                waiting = True
        try:
            await asyncio.wait_for(self._slot.acquire(), PROCESS_TIMEOUT_SECONDS)
        except TimeoutError:
            raise RunError("DOCUMENT_BUSY") from None
        finally:
            async with self._state_lock:
                if waiting:
                    self._waiting -= 1

    async def run_document(self, data: bytes, media_type: str, file_id: str, sha256: str) -> bytes:
        if len(data) > MAX_INPUT_BYTES:
            raise RunError("FILE_TOO_LARGE")
        await self._acquire()
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.document_cli",
                media_type,
                file_id,
                sha256,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=child_environment(),
                start_new_session=sys.platform != "win32",
            )
            try:
                output, _ = await asyncio.wait_for(
                    process.communicate(data), PROCESS_TIMEOUT_SECONDS
                )
            except TimeoutError:
                raise RunError("PARSE_TIMEOUT") from None
            if process.returncode != 0:
                raise RunError("PARSE_FAILED")
            if len(output) > MAX_OUTPUT_BYTES:
                raise RunError("DOCUMENT_TEXT_LIMIT")
            return output
        except asyncio.CancelledError:
            raise
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), 3)
                except TimeoutError:
                    pass
            self._slot.release()
