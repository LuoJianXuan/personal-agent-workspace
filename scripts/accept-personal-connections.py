"""Isolated API acceptance, plus provisioning for the local browser scenario.

The browser flow is deliberately separate: it submits the actual chat from the UI.
The provider token is consumed directly from the ignored local deployment file.
"""
import argparse
import importlib.util
import json
import os
import secrets
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("day3", ROOT / "scripts/accept-day3.py")
d3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d3)
d = d3.d
CONNECTION_RESPONSES = []


def login(name, password):
    return d.request("/auth/login", "POST", {"username": name, "password": password})["access_token"]


def connection(slug, bearer):
    return d.request("/me/connections/" + slug, token=bearer)


def change(slug, bearer, path, method, fields=None, expected=200):
    state = connection(slug, bearer)
    result = d.request("/me/connections/" + slug + path, method,
                       {"revision": state["revision"], **(fields or {})}, bearer, expected)
    if expected == 200:
        CONNECTION_RESPONSES.append(result)
        current = connection(slug, bearer)
        assert result['presentation'] == current['presentation']
        assert result['name'] == current['name']
    return result


def grant(slug, bearer, mode):
    state = connection(slug, bearer)
    assert state["pending"]
    return change(slug, bearer, "/grant", "PUT", {"catalog_hash": state["catalog_hash"], "mode": mode})


def enabled_tools(bearer, connection_id):
    return [item for item in d.request("/catalog/tools", token=bearer)["items"] if item["connection_id"] == connection_id]


def browser_setup(name):
    assert d.BASE == "http://127.0.0.1:5174/api"
    password = os.environ["PERSONAL_ACCEPTANCE_BROWSER_PASSWORD"]
    admin = d.login("ADMIN")["access_token"]
    existing = d.request("/admin/users", token=admin)["items"]
    if not any(row["username"] == name for row in existing):
        d.request("/admin/users", "POST", {"username": name, "password": password}, admin)
    session = login(name, password)
    home = dict(line.split("=", 1) for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
                if "=" in line and not line.startswith("#"))
    token = home["MCD_MCP_TOKEN"].strip().strip("'").strip('"')
    row = connection("mcd-cn", session)
    if row["status"] != "ready" or os.getenv("PERSONAL_ACCEPTANCE_REPLACE_TOKEN") == "true":
        probed = change("mcd-cn", session, "/probe", "POST", {"token": token})
        assert token not in json.dumps(probed)
        row = grant("mcd-cn", session, "query")
    visible = enabled_tools(session, row["connection_id"])
    campaign = next(item for item in visible if item["remote_name"] == "campaign-calendar")
    assert not campaign["requires_approval"]
    assert all(item["access_mode"] == "read" for item in visible)
    other = d.login("USER_B")["access_token"]
    assert not enabled_tools(other, row["connection_id"])
    print(json.dumps({"configured_test_user": name, "tool_count": len(visible),
                      "campaign_required_fields": campaign["input_schema"].get("required", []),
                      "other_user_sees_connection_tools": False}, ensure_ascii=False))


def create_run(session, prompt):
    thread = d.request("/threads", "POST", {"title": "Personal connector fixture"}, session, 201)
    result = d3.req("/threads/" + thread["id"] + "/runs", "POST",
                    {"input": prompt, "skill_ids": [], "connector_ids": ["fixture-personal"]},
                    session, str(uuid.uuid4()), 202)
    return result["run_id"]


def wait_approval(run_id, session):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if d.request("/runs/" + run_id, token=session)["status"] == "WAITING_APPROVAL":
            return d.request("/runs/" + run_id + "/approvals", token=session)["items"][0]
        time.sleep(0.25)
    raise AssertionError("Personal MCP write did not pause for approval")


def fixture():
    slug = "fixture-personal"
    a, b = (d.login(user)["access_token"] for user in ("USER_A", "USER_B"))
    tokens = ["fixture-" + secrets.token_hex(16) + user for user in ("A", "B")]
    rows = []
    for session, token in zip((a, b), tokens, strict=True):
        catalog = change(slug, session, "/probe", "POST", {"token": token})
        assert not any(item["granted"] for item in catalog["tools"]) or catalog["status"] == "ready"
        policies = {item["name"]: item["policy"] for item in catalog["tools"]}
        assert policies == {"fixture_account": "read", "fixture_blocked": "blocked",
                            "fixture_unknown": "unknown", "fixture_write": "confirm"}
        rows.append(grant(slug, session, "full"))
    assert rows[0]["connection_id"] != rows[1]["connection_id"]
    assert not enabled_tools(a, rows[1]["connection_id"])
    assert not enabled_tools(b, rows[0]["connection_id"])
    d.request("/me/connections/" + rows[1]["connection_id"], token=a, expect=404)
    admin = d.login("ADMIN")["access_token"]
    d.request("/admin/connector-definitions", token=a, expect=403)
    publication = next(row for row in d.request("/admin/connector-definitions", token=admin)["items"]
                       if row["connector_id"] == slug)
    publication_path = "/admin/connector-definitions/" + slug
    original_name = publication["name"]
    disabled = d.request(publication_path, "PATCH", {
        "name": original_name, "enabled": False, "revision": publication["revision"],
    }, admin)
    assert not enabled_tools(a, rows[0]["connection_id"])
    assert not any(item["connector_id"] == slug for item in d.request("/catalog/connectors", token=a)["items"])
    d.request(publication_path, "PATCH", {
        "name": original_name, "enabled": True, "revision": disabled["revision"],
    }, admin)
    assert enabled_tools(a, rows[0]["connection_id"])
    mixed = d.request("/admin/skills", "POST", {
        "name": "Connection fixture " + uuid.uuid4().hex[:10],
        "description": "Synthetic mixed capability selection",
        "category": "Verification",
        "content": "Read the authorized personal account if available.",
        "enabled": True,
        "revision": 0,
        "dependencies": [
            {"kind": "connector", "capability_id": slug, "required": True},
            {"kind": "builtin", "capability_id": "builtin_web_search", "required": False},
        ],
    }, admin)
    preview = {"skill_ids": [mixed["id"]], "require_tools": True, "require_streaming": True}
    denied = d.request("/capabilities/resolve", "POST", {**preview, "connector_ids": []}, a, 409)
    assert denied["code"] == "SKILL_DEPENDENCY_MISSING"
    resolved = d.request("/capabilities/resolve", "POST", {**preview, "connector_ids": [slug]}, a)
    missing = d.sql("SELECT data#>>'{skills,0,missing_optional_dependencies,0,capability_id}' FROM backend.capability_snapshots "
                    "WHERE id='" + resolved["snapshot_id"] + "';")
    assert missing == "builtin_web_search"
    for session, marker in ((a, "A"), (b, "B")):
        run_id = create_run(session, "mock:personal-account")
        state = d3.wait(run_id, session)
        events = d3.all_events(run_id, session)
        assert '"account": "' + marker + '"' in state["final_text"]
        assert "[REDACTED]" in state["final_text"]
        assert not any(token in json.dumps(events) for token in tokens)
        assert [event["type"] for event in events if event["type"].startswith("tool.")] == ["tool.requested", "tool.started", "tool.completed"]
    invalid = "fixture-" + secrets.token_hex(16) + "X"
    denied = change(slug, a, "/probe", "POST", {"token": invalid}, 409)
    assert denied["code"] == "CONNECTION_AUTH_REQUIRED" and invalid not in json.dumps(denied)
    assert connection(slug, a)["status"] == "ready"
    run_id = create_run(a, "mock:personal-write")
    pending = wait_approval(run_id, a)
    assert d.sql("SELECT count(*) FROM runtime.tool_executions WHERE run_id='" + run_id + "';") == "0"
    d.request("/approvals/" + pending["approval_id"] + "/decision", "POST", {"decision": "approve"}, a)
    state = d3.wait(run_id, a)
    assert "synthetic_write" in state["final_text"]
    assert d.sql("SELECT count(*) FROM runtime.tool_executions WHERE run_id='" + run_id + "';") == "1"
    stale = create_run(a, "mock:personal-write")
    proposal = wait_approval(stale, a)
    assert change(slug, a, "", "DELETE")["status"] == "disconnected"
    d.request("/approvals/" + proposal["approval_id"] + "/decision", "POST", {"decision": "approve"}, a, 409)
    assert d.sql("SELECT count(*) FROM runtime.tool_executions WHERE run_id='" + stale + "';") == "0"
    d.request("/runs/" + stale + "/cancel", "POST", {"command_id": str(uuid.uuid4())}, a, 202)
    d.run('exec', '-T', 'runtime', 'python', '-', input='from contracts.validate import validate\nimport json\nfor value in json.loads('+repr(json.dumps(CONNECTION_RESPONSES))+'):\n validate("PersonalConnection", value)\nprint("Mutation response contracts passed")\n')
    print("PASS: personal isolation, connector publication, policies, mixed Skill dependencies, invalid credential, no secret echo, approval exactly once, revoke stale approval, mutation response contracts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-user")
    options = parser.parse_args()
    if options.browser_user:
        browser_setup(options.browser_user)
    else:
        fixture()
