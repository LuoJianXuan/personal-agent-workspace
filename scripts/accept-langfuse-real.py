"""Authorized real local Langfuse ingestion check; model output remains deterministic."""
import importlib.util
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phase", ROOT / "scripts/accept-phase1.py")
phase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase)
d = phase.base

assert os.environ.get("WORKSPACE_PHASE1_AUTHORIZED") == "true"
token = phase.login("user-a")
run, state = phase.run(token, "mock:tool")
assert state["status"] == "SUCCEEDED", state
trace_id = state["trace_url"].rstrip("/").split("/")[-1]
assert state["trace_url"].startswith("http://localhost:3000/project/personal-agent-demo/traces/"), state

probe = r'''import base64,json,os,time,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timedelta,timezone
trace_id=%r
now=datetime.now(timezone.utc)
query=urllib.parse.urlencode({'fields':'core,basic,metadata','traceId':trace_id,'fromStartTime':(now-timedelta(minutes=10)).isoformat(),'toStartTime':(now+timedelta(minutes=2)).isoformat(),'limit':100})
url=os.environ['LANGFUSE_BASE_URL'].rstrip('/')+'/api/public/v2/observations?'+query
auth=base64.b64encode((os.environ['LANGFUSE_PUBLIC_KEY']+':'+os.environ['LANGFUSE_SECRET_KEY']).encode()).decode()
last=None
for _ in range(90):
 try:
  request=urllib.request.Request(url,headers={'Authorization':'Basic '+auth})
  with urllib.request.urlopen(request,timeout=5) as response:data=json.load(response)
  observations=data.get('data') or []
  types=sorted(set(str(item.get('type','')) for item in observations))
  names=sorted(set(str(item.get('name','')) for item in observations))
  serialized=json.dumps(data,ensure_ascii=False)
  assert os.environ['LANGFUSE_SECRET_KEY'] not in serialized
  has_model=any(value in types for value in ('GENERATION','CHATMODEL'))
  has_tool='TOOL' in types or any('mcp_' in name or 'tool' in name.lower() for name in names)
  has_root=any(item.get('isRootObservation') for item in observations)
  if has_model and has_tool and has_root:
   print(json.dumps({'trace_id':trace_id,'observation_count':len(observations),'types':types,'names':names[:30]},ensure_ascii=False));break
  last={'types':types,'names':names,'count':len(observations)}
 except Exception as error:last={'error':type(error).__name__}
 time.sleep(.5)
else:raise AssertionError('Langfuse trace did not contain model and tool observations: '+repr(last))
''' % trace_id
summary = json.loads(d.run("exec", "-T", "runtime", "python", "-c", probe))
assert summary["trace_id"] == trace_id and summary["observation_count"] >= 3, summary
result = {
    "checks": [
        "dedicated Personal Agent Demo project accepts a real local trace",
        "one stable trace contains Agent/model/tool observations",
        "trace secret is absent from the exported trace payload",
        "run details project a browser-safe localhost link",
    ],
    "run_id": run,
    "trace_id": trace_id,
    "observation_count": summary["observation_count"],
    "observation_types": summary["types"],
    "observation_names": summary["names"],
    "real_model_calls": 0,
    "real_search_calls": 0,
}
(ROOT / "docs/evidence/personal-agent-langfuse-real-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
