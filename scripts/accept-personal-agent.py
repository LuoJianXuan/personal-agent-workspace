"""Authorized S16-S20 acceptance; real files/processes/DB, deterministic model only."""
import importlib.util
import io
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phase", ROOT / "scripts/accept-phase1.py")
phase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase)
d = phase.base
checks = []


def passed(label):
    checks.append(label)
    print("PASS", label, flush=True)


def invalid_upload(token, name, data=b"legacy"):
    boundary = "personal-" + uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        d.BASE + "/files",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "multipart/form-data; boundary=" + boundary},
    )
    try:
        urllib.request.urlopen(request, timeout=20)
        raise AssertionError("unsupported upload succeeded")
    except urllib.error.HTTPError as error:
        assert error.code == 400, error.code
        return json.load(error)


def main():
    assert os.environ.get("WORKSPACE_PHASE1_AUTHORIZED") == "true"
    token = phase.login("user-a")
    before_runs = d.sql("SELECT count(*) FROM runtime.runs;")
    before_calls = d.sql("SELECT count(*) FROM runtime.model_calls;")
    before_jobs = d.sql("SELECT count(*) FROM backend.document_jobs;")
    file = phase.upload(token, "personal-cache.docx", phase.fixture_docx("按需解析缓存验收 2026。"))
    initial = d.request("/files/" + file["id"] + "/parsed", token=token)
    assert initial["status"] == "not_extracted"
    assert d.sql("SELECT count(*) FROM backend.document_jobs;") == before_jobs
    assert d.sql("SELECT count(*) FROM runtime.runs;") == before_runs
    assert d.sql("SELECT count(*) FROM runtime.model_calls;") == before_calls
    passed("upload and GET only save/query; no job, Agent Run, model call or eager parse")

    first = d.request("/files/" + file["id"] + "/extract", "POST", {}, token)
    stamp = d.sql("SELECT updated_at::text FROM backend.parsed_documents WHERE file_id='" + file["id"] + "';")
    second = d.request("/files/" + file["id"] + "/extract", "POST", {}, token)
    assert first == second and first["status"] == "ready" and first["parser_revision"] == "phase1-2"
    assert d.sql("SELECT count(*) FROM backend.parsed_documents WHERE file_id='" + file["id"] + "';") == "1"
    assert d.sql("SELECT updated_at::text FROM backend.parsed_documents WHERE file_id='" + file["id"] + "';") == stamp
    assert d.sql("SELECT count(*) FROM runtime.runs;") == before_runs
    assert d.sql("SELECT count(*) FROM runtime.model_calls;") == before_calls
    passed("first explicit preview parses once; repeat is an unchanged scoped cache hit without LLM")

    for name in ("legacy.doc", "native.wps", "slides.ppt"):
        result = invalid_upload(token, name)
        assert result["code"] == "UNSUPPORTED_FILE", result
    passed("legacy DOC, native WPS and PPT are explicitly rejected; supported formats stay bounded")

    run, state = phase.run(token, "mock:documents-skill")
    assert state["status"] == "SUCCEEDED" and "技能摘要装配=true" in state["final_text"] and "正文按需读取=true" in state["final_text"], state
    binding = d.sql("SELECT data->>'version' FROM runtime.run_skill_bindings WHERE run_id='" + run + "' AND skill_id='documents';")
    assert binding == "documents-1", binding
    _, denied = phase.run(token, "mock:documents-skill-write")
    assert denied["status"] == "SUCCEEDED" and "技能只读拒绝=true" in denied["final_text"], denied
    passed("document skill is summary-only in the prompt, frozen per Run, loaded on demand and read-only")

    probe = """from pathlib import Path
count=0
for p in Path('/proc').glob('[0-9]*'):
 try:
  args=(p/'cmdline').read_bytes().split(b'\\x00')
  if len(args)>2 and args[1:3]==[b'-m',b'app.document_cli']:count+=1
 except (FileNotFoundError,PermissionError,ProcessLookupError):pass
print(count)
"""
    assert d.run("exec", "-T", "runtime", "python", "-c", probe) == "0"
    services = set(d.run("ps", "--services", "--status", "running").splitlines())
    assert "document-worker" not in services
    assert {"postgres", "backend", "runtime", "web", "demo-mcp"}.issubset(services), services
    passed("no parser child remains and default deployment has no document-worker")

    output = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "checks": checks,
        "real_file_parses": 1,
        "real_model_calls": 0,
        "real_search_calls": 0,
    }
    (ROOT / "docs/evidence/personal-agent-results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
