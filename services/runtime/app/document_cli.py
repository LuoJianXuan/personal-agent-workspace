"""Fixed parser child entry point. It has no network or service credentials."""
import json
import sys

from .documents import parse_document
from .errors import RunError
from .execution import MAX_INPUT_BYTES


def set_limits() -> None:
    if sys.platform == "win32":
        return
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))


def main() -> None:
    set_limits()
    if len(sys.argv) != 4:
        raise SystemExit(2)
    media_type, file_id, sha256 = sys.argv[1:]
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    try:
        if len(raw) > MAX_INPUT_BYTES:
            raise RunError("FILE_TOO_LARGE")
        result = parse_document(raw, media_type, file_id, sha256)
    except BaseException as error:
        code = error.code if isinstance(error, RunError) else "PARSE_FAILED"
        permanent = code in {
            "PARSE_UNSUPPORTED", "DOCUMENT_ENCRYPTED", "DOCUMENT_UNSUPPORTED",
            "NO_EXTRACTABLE_TEXT",
        }
        result = {
            "file_id": file_id,
            "sha256": sha256,
            "parser_revision": "phase1-2",
            "status": "unsupported" if permanent else "failed",
            "error": code,
            "warnings": [],
            "chunks": [],
            "columns": [],
        }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
