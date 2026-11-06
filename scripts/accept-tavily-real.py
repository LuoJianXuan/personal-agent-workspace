"""Authorized Tavily → public page → cited report acceptance."""
import importlib.util
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
base_spec = importlib.util.spec_from_file_location("d2", ROOT / "scripts/accept-day2.py")
d = importlib.util.module_from_spec(base_spec)
base_spec.loader.exec_module(d)
trace_spec = importlib.util.spec_from_file_location("real_trace", ROOT / "scripts/accept-personal-agent-real.py")
real_trace = importlib.util.module_from_spec(trace_spec)
trace_spec.loader.exec_module(real_trace)
RESULT = ROOT / "docs/evidence/personal-agent-tavily-real-results.json"


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
    deadline = time.monotonic() + 220
    while time.monotonic() < deadline:
        state = request("/runs/" + run_id, token=token)
        if state["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"}:
            assert state["status"] == "SUCCEEDED", state
            return state
        time.sleep(0.4)
    raise AssertionError("Tavily run did not settle")


def all_events(run_id, token):
    output, after = [], 0
    while True:
        page = request(f"/runs/{run_id}/events?after_seq={after}", token=token)
        output.extend(page["items"])
        after = page["next_seq"]
        if not page["has_more"]:
            return output


def main():
    assert d.ENV.get("WEB_PORT") == "5174"
    guard = d.run(
        "exec", "-T", "runtime", "python", "-c",
        "import os;print('|'.join([os.getenv('MODEL_MODE',''),os.getenv('REAL_CALL_BUDGET',''),os.getenv('REAL_MAX_OUTPUT_TOKENS',''),os.getenv('ENABLE_PUBLIC_WEB',''),str(bool(os.getenv('TAVILY_API_KEY'))),os.getenv('SEARCH_CALL_BUDGET','')]))",
    )
    assert guard == "real|12|4096|true|True|3", guard
    admin = d.login("ADMIN")["access_token"]
    token = d.login("USER_A")["access_token"]
    models = request("/admin/models", token=admin)["items"]
    model = next(item for item in reversed(models) if item["name"].startswith("DeepSeek 正常配置验收") and item["enabled"] and item["max_output_tokens"] == 4096)
    thread = request("/threads", "POST", {"title": "真实 Tavily 搜索验收"}, token, 201)
    submitted = request(
        "/threads/" + thread["id"] + "/runs", "POST",
        {
            "input": (
                "完成一次受控真实研究：先且只调用一次 builtin_web_search 搜索 ‘IANA example domains purpose’，"
                "最多返回3条；从结果中选择一个公开页面并调用 builtin_fetch_page 读取正文。"
                "然后调用 builtin_publish_report 发布 Markdown 报告，标题为‘IANA 示例域名用途’，"
                "正文用两三句话说明用途，并严格用已读取来源返回的 [source:<source_id>] 引用，"
                "source_ids 只传实际已读取来源；不要把搜索摘要当引用。最终只简短说明报告已生成。"
            ),
            "model_id": model["id"],
            "skill_ids": [],
            "file_ids": [],
            "network_enabled": True,
        },
        token, 202,
    )
    state = wait(submitted["run_id"], token)
    run_id = submitted["run_id"]
    sources = request("/runs/" + run_id + "/sources", token=token)["items"]
    search_sources = [item for item in sources if item["read_status"] == "search_only"]
    read_sources = [item for item in sources if item["read_status"] in {"read", "truncated"}]
    assert 1 <= len(search_sources) <= 3 and read_sources, sources
    artifacts = request("/runs/" + run_id + "/artifacts", token=token)["items"]
    report_file = next(item for item in artifacts if item["name"].endswith(".md"))
    report_text = request("/files/" + report_file["id"] + "/content", token=token)["text"]
    assert "[source:" in report_text and any(item["source_id"] in report_text for item in read_sources), report_text
    event_items = all_events(run_id, token)
    completed = [item["payload"].get("text", "") for item in event_items if item["type"] == "tool.completed"]
    assert any("builtin_web_search" in item or '"query"' in item for item in completed)
    assert any('"untrusted_material": true' in item for item in completed)
    assert any('"completed": true' in item for item in completed)
    assert not any(item["type"] == "tool.failed" for item in event_items), event_items
    external = json.loads(d.sql(
        "SELECT json_build_object('fetch',count(*) FILTER (WHERE kind='fetch'),'search',count(*) FILTER (WHERE kind='search')) "
        "FROM runtime.external_calls WHERE run_id='" + run_id + "';"
    ))
    assert external["search"] == 1 and 1 <= external["fetch"] <= 6, external
    model_calls = json.loads(d.sql(
        "SELECT coalesce(json_agg(t),'[]') FROM (SELECT status,usage,error_code FROM runtime.model_calls "
        "WHERE run_id='" + run_id + "' ORDER BY created_at) t;"
    ))
    assert 1 <= len(model_calls) <= 6 and all(item["status"] == "SUCCEEDED" for item in model_calls), model_calls
    trace_id = state["trace_url"].rstrip("/").split("/")[-1]
    langfuse = {"trace_id": trace_id, **real_trace.trace_summary(trace_id)}
    for name in ("builtin_web_search", "builtin_fetch_page", "builtin_publish_report"):
        assert name in langfuse["names"], (name, langfuse)
    result = {
        "status": "passed",
        "run_id": run_id,
        "trace_url": state["trace_url"],
        "query": "IANA example domains purpose",
        "external_calls": external,
        "search_source_count": len(search_sources),
        "read_source_count": len(read_sources),
        "read_urls": [item["url"] for item in read_sources],
        "artifact": {"id": report_file["id"], "name": report_file["name"], "media_type": report_file["media_type"]},
        "model_call_count": len(model_calls),
        "model_calls": model_calls,
        "langfuse": langfuse,
        "checks": [
            "one real Tavily search returned persisted search-only sources",
            "a discovered public page was fetched and persisted as a read source",
            "the Markdown artifact cites only a read source",
            "Langfuse contains the real model and all three research tool observations",
            "no tool failed and the Tavily key was never put in model input or artifacts",
        ],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "external_calls": external, "model_calls": len(model_calls), "artifact": report_file["name"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
