"""Explicit opt-in acceptance for the real, isolated Docker launcher."""
import asyncio
import base64
import json
import os
from uuid import uuid4
import httpx

assert os.environ.get('WORKSPACE_COMPUTE_AUTHORIZED') == 'true', 'Use verify-compute.ps1 -Authorized'

async def main():
    checks = []
    async with httpx.AsyncClient(base_url=os.environ['COMPUTE_BROKER_URL'], headers={
        'Authorization': 'Bearer ' + os.environ['COMPUTE_BROKER_TOKEN']
    }, trust_env=False, timeout=50) as client:
        def job(code):
            return {'execution_id': str(uuid4()), 'run_id': str(uuid4()), 'code': code, 'files': []}
        async def execute(payload):
            response = await client.post('/jobs', json=payload)
            assert response.status_code == 200, 'Compute request rejected'
            return response.json()
        payload = job("""import os,socket
from pathlib import Path
assert os.getuid()!=0
assert not Path('/var/run/docker.sock').exists()
assert not any(any(s in k for s in ('KEY','TOKEN','SECRET','PASSWORD','DATABASE_URL')) for k in os.environ)
try:
    Path('/var/isolation-probe').write_text('no')
    raise AssertionError('root filesystem writable')
except OSError:
    pass
try:
    socket.create_connection(('1.1.1.1',443),timeout=1).close()
    raise AssertionError('network accessible')
except OSError:
    pass
Path('/work/outputs/result.csv').write_text('group,total\\nA,3\\n')
print('isolation checks completed')
"""
        )
        first = await execute(payload)
        assert first['error'] == '', first['error']
        assert base64.b64decode(first['files'][0]['content']).decode() == 'group,total\nA,3\n'
        checks.append('nonroot / readonly root / no socket / no credentials / offline network / real output')
        again = await execute(payload)
        assert first == again
        checks.append('same execution and payload returns durable result')
        conflict = dict(payload, code='print(123)')
        response = await client.post('/jobs', json=conflict)
        assert response.status_code == 409
        checks.append('same execution with changed payload is rejected')
        overflow = await execute(job("from pathlib import Path\nfor i in range(6):Path('/work/outputs/'+str(i)+'.csv').write_text('x\\n1\\n')"))
        assert overflow['error'] == 'COMPUTE_OUTPUT_LIMIT' and not overflow['files']
        checks.append('excess output count is rejected')
        linked = await execute(job("from pathlib import Path\nPath('/work/outputs/link.csv').symlink_to('/etc/passwd')"))
        assert linked['error'] == 'COMPUTE_OUTPUT_INVALID' and not linked['files']
        checks.append('symlink output is rejected')
        pre = job('print(1)')
        await client.delete('/jobs/' + pre['execution_id'])
        response = await client.post('/jobs', json=pre)
        assert response.status_code == 409 and response.json()['error'] == 'COMPUTE_CANCELLED'
        checks.append('cancel before creation prevents later startup')
        pending = job('import time;time.sleep(25)')
        task = asyncio.create_task(execute(pending))
        await asyncio.sleep(2)
        response = await client.delete('/jobs/' + pending['execution_id'])
        assert response.status_code == 200
        stopped = await task
        assert stopped['error'] == 'COMPUTE_CANCELLED'
        checks.append('active cancellation reaches real container')
        timed = await execute(job('import time;time.sleep(60)'))
        assert timed['error'] == 'COMPUTE_TIMEOUT'
        checks.append('time budget stops real Python process')
    print(json.dumps({'checks': checks, 'real_model_calls': 0, 'real_search_calls': 0}))

asyncio.run(main())
