"""Configure and verify the real MCP through the daily control plane; no write tool is enabled."""
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:5173/api"
ENDPOINT = "https://mcp.mcd.cn"
CREDENTIAL = "mcd_mcp_token"
WRITE_TOOLS = {
    "delivery-create-address",
    "create-order",
    "auto-bind-coupons",
    "mall-create-order",
}


def env():
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def request(path, method="GET", body=None, token=None, expected=(200,)):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    value = json.loads(raw)
    assert status in expected, (path, status, value)
    return value


def main():
    local = env()
    token = request("/auth/login", "POST", {
        "username": local["SEED_ADMIN_USERNAME"],
        "password": local["SEED_ADMIN_PASSWORD"],
    })["access_token"]
    connections = request("/admin/mcp-connections", token=token)["items"]
    connection = next((item for item in connections if item["endpoint"] == ENDPOINT), None)
    if connection is None:
        connection = request("/admin/mcp-connections", "POST", {
            "name": "麦当劳中国",
            "endpoint": ENDPOINT,
            "credential_ref": CREDENTIAL,
            "enabled": True,
            "revision": 0,
        }, token)
    elif not connection["enabled"]:
        connection = request("/admin/mcp-connections/" + connection["id"], "PATCH", {
            "name": connection["name"],
            "endpoint": connection["endpoint"],
            "credential_ref": connection["credential_ref"],
            "enabled": True,
            "revision": connection["revision"],
        }, token)
    base = "/admin/mcp-connections/" + connection["id"]
    connection = request(base + "/discover", "POST", {"revision": connection["revision"]}, token)
    assert connection["probe_status"] == "success", connection
    tools = request(base + "/tools", token=token)["items"]
    by_name = {tool["remote_name"]: tool for tool in tools}
    assert WRITE_TOOLS.issubset(by_name)
    assert all(by_name[name]["access_mode"] == "write" and by_name[name]["requires_approval"] for name in WRITE_TOOLS)
    now = by_name["now-time-info"]
    if not now["enabled"]:
        now = request(base + "/tools/" + now["namespaced_tool_id"], "PATCH", {
            "enabled": True,
            "revision": now["revision"],
        }, token)
    by_name["now-time-info"] = now
    tools = list(by_name.values())
    assert all(not by_name[name]["enabled"] for name in WRITE_TOOLS)
    catalog = request("/catalog/tools", token=token)["items"]
    assert any(item["namespaced_tool_id"] == now["namespaced_tool_id"] for item in catalog)
    serialized = json.dumps({"connection": connection, "tools": tools, "catalog": catalog})
    secret = local.get("MCD_MCP_TOKEN", "")
    assert not secret or secret not in serialized
    counts = {mode: sum(tool["access_mode"] == mode for tool in tools) for mode in ("read", "write", "blocked")}
    print(json.dumps({
        "status": "passed",
        "connection_id": connection["id"],
        "probe_status": connection["probe_status"],
        "discovered_tool_count": len(tools),
        "classification": counts,
        "enabled_read_tools": [item["remote_name"] for item in tools if item["enabled"] and item["access_mode"] == "read"],
        "enabled_write_tools": [item["remote_name"] for item in tools if item["enabled"] and item["access_mode"] == "write"],
        "secret_exposed": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
