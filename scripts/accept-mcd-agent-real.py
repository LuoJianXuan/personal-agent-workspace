"""Authorized read-only McDonald's MCP run through the full Agent path.

The model is deterministic Mock. Exactly one real remote read tool is invoked;
known mutation tools are discovered but kept disabled and are never called.
"""
import base64
import importlib.util
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phase", ROOT / "scripts/accept-phase1.py")
phase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase)
d = phase.base

ENDPOINT = "https://mcp.mcd.cn"
CREDENTIAL = "mcd_mcp_token"
WRITE_TOOLS = {
    "delivery-create-address",
    "create-order",
    "auto-bind-coupons",
    "mall-create-order",
}


def all_events(run_id, token):
    output, after = [], 0
    while True:
        page = d.request(f"/runs/{run_id}/events?after_seq={after}", token=token)
        output.extend(page["items"])
        after = page["next_seq"]
        if not page["has_more"]:
            return output


def trace_summary(trace_id, expected_tool):
    code = r'''import base64,json,os,time,urllib.parse,urllib.request
from datetime import datetime,timedelta,timezone
trace_id=%r
expected_tool=%r
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
 assert os.environ.get('MCD_MCP_TOKEN','') not in serialized
 if 'GENERATION' in types and 'TOOL' in types and expected_tool in names:
  print(json.dumps({'count':len(items),'types':types,'names':names[:30]}));break
 last={'count':len(items),'types':types,'names':names}
 time.sleep(.5)
else:raise AssertionError('Langfuse observations incomplete: '+repr(last))
''' % (trace_id, expected_tool)
    return json.loads(d.run("exec", "-T", "runtime", "python", "-c", code))


def main():
    assert os.environ.get("WORKSPACE_MCD_AUTHORIZED") == "true"
    assert d.TEST_PROJECT in ("agent-workspace-verification", "agent-workspace-fresh")
    admin = d.login("ADMIN")["access_token"]
    token = d.login("USER_A")["access_token"]

    connections = d.request("/admin/mcp-connections", token=admin)["items"]
    connection = next((item for item in connections if item["endpoint"] == ENDPOINT), None)
    if connection is None:
        connection = d.request(
            "/admin/mcp-connections",
            "POST",
            {
                "name": "麦当劳中国只读验收",
                "endpoint": ENDPOINT,
                "credential_ref": CREDENTIAL,
                "enabled": True,
                "revision": 0,
            },
            admin,
        )
    elif not connection["enabled"]:
        connection = d.request(
            "/admin/mcp-connections/" + connection["id"],
            "PATCH",
            d.write("McpWrite", connection, enabled=True),
            admin,
        )

    path = "/admin/mcp-connections/" + connection["id"]
    connection = d.request(path + "/discover", "POST", {"revision": connection["revision"]}, admin)
    assert connection["probe_status"] == "success", connection
    tools = d.request(path + "/tools", token=admin)["items"]
    by_name = {item["remote_name"]: item for item in tools}
    assert "now-time-info" in by_name and WRITE_TOOLS.issubset(by_name)
    for name in WRITE_TOOLS:
        item = by_name[name]
        assert item["access_mode"] == "write" and item["requires_approval"]
        if item["enabled"]:
            item = d.request(
                path + "/tools/" + item["namespaced_tool_id"],
                "PATCH",
                {"enabled": False, "revision": item["revision"]},
                admin,
            )
        assert not item["enabled"]
    now = by_name["now-time-info"]
    assert now["access_mode"] == "read" and not now["requires_approval"]
    if now["enabled"]:
        now = d.request(
            path + "/tools/" + now["namespaced_tool_id"],
            "PATCH",
            {"enabled": False, "revision": now["revision"]},
            admin,
        )
    now = d.request(
        path + "/tools/" + now["namespaced_tool_id"],
        "PATCH",
        {"enabled": True, "revision": now["revision"]},
        admin,
    )

    run_id, state = phase.run(token, "mock:mcd")
    assert state["status"] == "SUCCEEDED", state
    events = all_events(run_id, token)
    lifecycle = [item for item in events if item["type"].startswith("tool.")]
    assert [item["type"] for item in lifecycle] == [
        "tool.requested",
        "tool.started",
        "tool.completed",
    ], lifecycle
    execution_ids = {item["payload"]["execution_id"] for item in lifecycle}
    assert len(execution_ids) == 1
    assert lifecycle[0]["payload"]["text"] == now["namespaced_tool_id"]
    assert lifecycle[1]["payload"]["text"] == now["namespaced_tool_id"]
    assert lifecycle[2]["payload"]["status"] == "SUCCEEDED"
    assert lifecycle[2]["payload"]["text"] and lifecycle[2]["payload"]["text"] in state["final_text"]
    assert not any(item["type"] == "approval.required" for item in events)

    serialized = json.dumps({"state": state, "events": events}, ensure_ascii=False)
    local_secret = d.run(
        "exec", "-T", "runtime", "python", "-c",
        "import os;print('configured' if os.getenv('MCD_MCP_TOKEN') else 'missing')",
    )
    assert local_secret == "configured"
    trace_id = state["trace_url"].rstrip("/").split("/")[-1]
    assert trace_id and state["trace_url"].startswith("http://localhost:3000/project/")
    langfuse = trace_summary(trace_id, now["namespaced_tool_id"])

    audits = d.request("/admin/audits", token=admin)["items"]
    assert any(item["action"] == "mcp.discover" and item["object_id"] == connection["id"] for item in audits)
    assert any(item["action"] == "mcp.tool_enablement" and item["object_id"] == now["namespaced_tool_id"] for item in audits)
    assert CREDENTIAL not in serialized

    report = {
        "status": "passed",
        "run_id": run_id,
        "trace_url": state["trace_url"],
        "connection_id": connection["id"],
        "tool_id": now["namespaced_tool_id"],
        "canonical_events": [item["type"] for item in lifecycle],
        "execution_id_stable": True,
        "langfuse": langfuse,
        "known_write_tools_disabled_and_not_called": sorted(WRITE_TOOLS),
        "credential_exposed": False,
        "real_model_calls": 0,
        "real_mcp_read_calls": 1,
        "real_mcp_write_calls": 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    (ROOT / "docs/evidence/mcp-preclose-real-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
