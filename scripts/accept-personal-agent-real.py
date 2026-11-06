"""Authorized real DeepSeek acceptance for the personal-agent document/tool path.

The launcher must set the 12-request / 4096-output-token guard in Runtime. This
script never reads or persists the provider credential.
"""
import importlib.util
import json
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("d2", ROOT / "scripts/accept-day2.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

AUTHORIZED_CALLS = 12
MAX_OUTPUT_TOKENS = 4096
RESULT = ROOT / "docs/evidence/personal-agent-deepseek-real-results.json"
report = {
    "status": "running",
    "provider": "DeepSeek",
    "protocol": "openai_chat_completions",
    "authorized_calls": AUTHORIZED_CALLS,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "runs": [],
    "checks": [],
}


def save():
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def request(path, method="GET", body=None, token=None, expect=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if method == "POST" and path.endswith("/runs"):
        headers["Idempotency-Key"] = str(uuid.uuid4())
    req = urllib.request.Request(
        d.BASE + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    value = json.loads(raw)
    assert status == expect, (method, path, status, value)
    return value


def wait(run_id, token, timeout=190):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = request("/runs/" + run_id, token=token)
        if state["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"}:
            assert state["status"] == "SUCCEEDED", state
            return state
        time.sleep(0.35)
    raise AssertionError("Run did not settle: " + run_id)


def events(run_id, token):
    output, after = [], 0
    while True:
        page = request(f"/runs/{run_id}/events?after_seq={after}", token=token)
        output.extend(page["items"])
        after = page["next_seq"]
        if not page["has_more"]:
            return output


def docx_fixture():
    data = BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            '<w:p><w:r><w:t>个人助理真实验收：项目代号松岚-409，预算 672 元。</w:t></w:r></w:p>'
            '<w:sectPr/></w:body></w:document>',
        )
    return data.getvalue()


def upload(token, name, content):
    boundary = "workspace" + uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        d.BASE + "/files",
        data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "multipart/form-data; boundary=" + boundary},
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        assert response.status == 201
        return json.load(response)


def submit(token, model_id, text, file_ids=None):
    thread = request("/threads", "POST", {"title": "Personal Agent DeepSeek real " + uuid.uuid4().hex[:8]}, token, 201)
    run = request(
        "/threads/" + thread["id"] + "/runs",
        "POST",
        {"input": text, "model_id": model_id, "skill_ids": [], "file_ids": file_ids or []},
        token,
        202,
    )
    state = wait(run["run_id"], token)
    item = {"run_id": run["run_id"], "trace_url": state.get("trace_url", ""), "status": state["status"]}
    report["runs"].append(item)
    save()
    return state, events(run["run_id"], token)


def trace_summary(trace_id):
    code = r'''import base64,json,os,time,urllib.parse,urllib.request
from datetime import datetime,timedelta,timezone
trace_id=%r
now=datetime.now(timezone.utc)
query=urllib.parse.urlencode({'fields':'core,basic,metadata','traceId':trace_id,'fromStartTime':(now-timedelta(minutes=10)).isoformat(),'toStartTime':(now+timedelta(minutes=2)).isoformat(),'limit':100})
url=os.environ['LANGFUSE_BASE_URL'].rstrip('/')+'/api/public/v2/observations?'+query
auth=base64.b64encode((os.environ['LANGFUSE_PUBLIC_KEY']+':'+os.environ['LANGFUSE_SECRET_KEY']).encode()).decode()
last={}
for _ in range(90):
 request=urllib.request.Request(url,headers={'Authorization':'Basic '+auth})
 with urllib.request.urlopen(request,timeout=5) as response:data=json.load(response)
 items=data.get('data') or []
 types=sorted(set(str(item.get('type','')) for item in items))
 names=sorted(set(str(item.get('name','')) for item in items))
 serialized=json.dumps(data,ensure_ascii=False)
 assert os.environ['LANGFUSE_SECRET_KEY'] not in serialized
 if 'GENERATION' in types and 'TOOL' in types:
  print(json.dumps({'count':len(items),'types':types,'names':names[:30]}));break
 last={'count':len(items),'types':types,'names':names}
 time.sleep(.5)
else:raise AssertionError('Langfuse observations incomplete: '+repr(last))
''' % trace_id
    return json.loads(d.run("exec", "-T", "runtime", "python", "-c", code))


def main():
    assert d.ENV.get("WEB_PORT") == "5174", "Real acceptance is restricted to the isolated verification stack"
    guard = d.run(
        "exec", "-T", "runtime", "python", "-c",
        "import os;print('|'.join([os.getenv('MODEL_MODE',''),os.getenv('REAL_CALL_BUDGET',''),os.getenv('REAL_MAX_OUTPUT_TOKENS','')]))",
    )
    assert guard == "real|12|4096", "Runtime real-call guard is not the authorized normal-use configuration"

    admin = d.login("ADMIN")["access_token"]
    token = d.login("USER_A")["access_token"]
    suffix = uuid.uuid4().hex[:8]
    model = request(
        "/admin/models", "POST",
        {
            "name": "DeepSeek 正常配置验收 " + suffix,
            "provider": "deepseek",
            "protocol": "openai_chat_completions",
            "protocol_options": {"thinking": {"type": "disabled"}},
            "provider_model_name": "deepseek-flash",
            "base_url": "https://api.deepseek.com",
            "credential_ref": "deepseek_primary",
            "context_limit": 64000,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "capabilities": {"streaming": True, "tool_calling": True},
            "enabled": True,
            "is_default": False,
            "revision": 0,
        },
        admin,
    )
    report.update(model_id=model["id"], model_revision=model["revision"], provider_model_name=model["provider_model_name"])
    save()

    connections = request("/admin/mcp-connections", token=admin)["items"]
    connection = next((item for item in connections if item["endpoint"] == "http://demo-mcp:8001/mcp/"), None)
    if connection is None:
        connection = request(
            "/admin/mcp-connections", "POST",
            {"name": "DeepSeek real MCP " + suffix, "endpoint": "http://demo-mcp:8001/mcp/", "credential_ref": "", "enabled": True, "revision": 0},
            admin,
        )
    connection_path = "/admin/mcp-connections/" + connection["id"]
    connection = request(connection_path + "/discover", "POST", {"revision": connection["revision"]}, admin)
    for tool in request(connection_path + "/tools", token=admin)["items"]:
        if not tool["enabled"]:
            request(connection_path + "/tools/" + tool["namespaced_tool_id"], "PATCH", {"enabled": True, "revision": tool["revision"]}, admin)

    document = upload(token, "personal-agent-real.docx", docx_fixture())
    document_state, document_events = submit(
        token, model["id"],
        "请调用 builtin_read_material 读取本轮唯一附件，只回答项目代号和预算；不得猜测，也不要输出其他解释。",
        [document["id"]],
    )
    assert "松岚-409" in document_state["final_text"] and "672" in document_state["final_text"], document_state["final_text"]
    assert any(item["type"] == "tool.completed" and "松岚-409" in item["payload"].get("text", "") for item in document_events)
    report["checks"].append("real DeepSeek invoked on-demand DOCX material tool and grounded the final answer")

    order_state, order_events = submit(
        token, model["id"],
        "请务必调用订单查询工具查询合成订单 DEMO-1001，然后只回答订单号、状态和金额；不得猜测。",
    )
    assert "DEMO-1001" in order_state["final_text"], order_state["final_text"]
    assert any(item["type"] == "tool.completed" and "DEMO-1001" in item["payload"].get("text", "") for item in order_events)
    report["checks"].append("real DeepSeek completed the MCP tool loop and grounded the final answer")

    trace_results = []
    for run in report["runs"]:
        assert run["trace_url"].startswith("http://localhost:3000/project/personal-agent-demo/traces/"), run
        trace_results.append({"trace_id": run["trace_url"].rstrip("/").split("/")[-1], **trace_summary(run["trace_url"].rstrip("/").split("/")[-1])})
    report["langfuse"] = trace_results
    report["checks"].append("each real Agent run exported model and tool observations to the dedicated Langfuse project")

    run_ids = [item["run_id"] for item in report["runs"]]
    quoted = ",".join("'" + item + "'" for item in run_ids)
    calls = json.loads(d.sql(
        "SELECT coalesce(json_agg(t),'[]') FROM (SELECT run_id,status,usage,error_code FROM runtime.model_calls "
        "WHERE run_id IN (" + quoted + ") ORDER BY created_at) t;"
    ))
    assert 1 <= len(calls) <= AUTHORIZED_CALLS, calls
    assert all(item["status"] == "SUCCEEDED" for item in calls), calls
    report["model_calls"] = calls
    report["physical_request_count"] = len(calls)
    report["usage_total"] = {
        "input_tokens": sum(int(item.get("usage", {}).get("input_tokens", 0)) for item in calls),
        "output_tokens": sum(int(item.get("usage", {}).get("output_tokens", 0)) for item in calls),
        "total_tokens": sum(int(item.get("usage", {}).get("total_tokens", 0)) for item in calls),
        "cache_read_input_tokens": sum(
            int(item.get("usage", {}).get("input_token_details", {}).get("cache_read", 0)) for item in calls
        ),
    }
    report["checks"].append("physical provider requests stayed within the 12-request guard and all completed successfully")
    report["status"] = "passed"
    report["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save()
    print(json.dumps({"status": report["status"], "physical_request_count": len(calls), "usage_total": report["usage_total"]}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        report["status"] = "failed"
        save()
        raise
