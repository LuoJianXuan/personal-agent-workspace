"""Authorized real public-page acceptance; does not call Tavily search."""
import importlib.util
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("d2", ROOT / "scripts/accept-day2.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
RESULT = ROOT / "docs/evidence/personal-agent-public-web-real-results.json"
trace_spec = importlib.util.spec_from_file_location("real_trace", ROOT / "scripts/accept-personal-agent-real.py")
real_trace = importlib.util.module_from_spec(trace_spec)
trace_spec.loader.exec_module(real_trace)


def request(path, method="GET", body=None, token=None, expect=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if method == "POST" and path.endswith("/runs"):
        headers["Idempotency-Key"] = str(uuid.uuid4())
    item = urllib.request.Request(
        d.BASE + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(item, timeout=25) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    value = json.loads(raw)
    assert status == expect, (method, path, status, value)
    return value


def wait(run_id, token):
    deadline = time.monotonic() + 190
    while time.monotonic() < deadline:
        state = request("/runs/" + run_id, token=token)
        if state["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"}:
            assert state["status"] == "SUCCEEDED", state
            return state
        time.sleep(0.35)
    raise AssertionError("Public-web run did not settle")


def main():
    assert d.ENV.get("WEB_PORT") == "5174"
    guard = d.run(
        "exec", "-T", "runtime", "python", "-c",
        "import os;print('|'.join([os.getenv('MODEL_MODE',''),os.getenv('REAL_CALL_BUDGET',''),os.getenv('REAL_MAX_OUTPUT_TOKENS',''),os.getenv('ENABLE_PUBLIC_WEB','')]))",
    )
    assert guard == "real|12|4096|true", guard
    admin = d.login("ADMIN")["access_token"]
    token = d.login("USER_A")["access_token"]
    models = request("/admin/models", token=admin)["items"]
    model = next(item for item in reversed(models) if item["name"].startswith("DeepSeek 正常配置验收") and item["enabled"] and item["max_output_tokens"] == 4096)
    thread = request("/threads", "POST", {"title": "真实公网正文验收"}, token, 201)
    submitted = request(
        "/threads/" + thread["id"] + "/runs", "POST",
        {
            "input": "请务必调用 builtin_fetch_page 读取 https://example.com/ ，然后只回答页面标题，以及该页面允许用于什么场景；不得凭常识回答。",
            "model_id": model["id"],
            "skill_ids": [],
            "file_ids": [],
            "network_enabled": True,
        },
        token, 202,
    )
    state = wait(submitted["run_id"], token)
    assert "Example Domain" in state["final_text"], state["final_text"]
    sources = request("/runs/" + submitted["run_id"] + "/sources", token=token)["items"]
    assert len(sources) >= 1 and any(item["read_status"] == "read" and item["url"].startswith("https://example.com") for item in sources), sources
    events = request("/runs/" + submitted["run_id"] + "/events?after_seq=0", token=token)["items"]
    assert any(item["type"] == "tool.completed" and "Example Domain" in item["payload"].get("text", "") for item in events)
    calls = json.loads(d.sql(
        "SELECT json_build_object('fetch',count(*) FILTER (WHERE kind='fetch'),'search',count(*) FILTER (WHERE kind='search')) "
        "FROM runtime.external_calls WHERE run_id='" + submitted["run_id"] + "';"
    ))
    assert calls == {"fetch": 1, "search": 0}, calls
    model_calls = json.loads(d.sql(
        "SELECT coalesce(json_agg(t),'[]') FROM (SELECT status,usage,error_code FROM runtime.model_calls "
        "WHERE run_id='" + submitted["run_id"] + "' ORDER BY created_at) t;"
    ))
    assert 1 <= len(model_calls) <= 3 and all(item["status"] == "SUCCEEDED" for item in model_calls), model_calls
    trace_id = state["trace_url"].rstrip("/").split("/")[-1]
    langfuse = {"trace_id": trace_id, **real_trace.trace_summary(trace_id)}
    assert "GENERATION" in langfuse["types"] and "TOOL" in langfuse["types"] and "builtin_fetch_page" in langfuse["names"], langfuse
    result = {
        "status": "passed",
        "run_id": submitted["run_id"],
        "trace_url": state["trace_url"],
        "url": "https://example.com/",
        "source_count": len(sources),
        "external_calls": calls,
        "model_call_count": len(model_calls),
        "model_calls": model_calls,
        "langfuse": langfuse,
        "checks": [
            "real DeepSeek selected builtin_fetch_page",
            "public DNS/address validation and pinned HTTPS fetch succeeded",
            "read source was persisted and grounded the final answer",
            "Langfuse contains the real model and builtin_fetch_page tool observations",
            "Tavily search was not called without a credential",
        ],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "model_calls": len(model_calls), "external_calls": calls}, ensure_ascii=False))


if __name__ == "__main__":
    main()
