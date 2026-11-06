import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from app.access import configuration_status, run_worker, safe_client, target

class AccessBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_target_and_alias_are_bound(self):
        fixture={'mcp':[{'endpoint':'http://demo-mcp:8001/mcp/','credential_ref':'','read_only_tools':['lookup_demo_order']}],'models':[]}
        with patch('app.access.policy',return_value=fixture):
            for endpoint,alias in [('http://169.254.169.254/',''),('http://demo-mcp:8001/mcp/?x=1',''),('http://demo-mcp:8001/mcp/','unrelated'),('https://api.deepseek.com.evil.invalid','deepseek_primary')]:
                with self.assertRaises(ValueError):target('mcp',endpoint,alias)
            self.assertEqual(target('mcp','http://demo-mcp:8001/mcp/','')['read_only_tools'],['lookup_demo_order'])

    async def test_credential_presence_without_model_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'policy.json'
            path.write_text(json.dumps({'models':[{'endpoint':'https://example.invalid','credential_ref':'absent','env_var':'DAY2_TEST_ABSENT'}],'mcp':[]}))
            with patch.dict(os.environ,{'ACCESS_POLICY_PATH':str(path)}):
                self.assertFalse(configuration_status()['models'][0]['credential_configured'])
                with patch.dict(os.environ,{'DAY2_TEST_ABSENT':'not-a-real-secret'}):
                    result=configuration_status()
                    self.assertTrue(result['models'][0]['credential_configured'])
                    self.assertNotIn('not-a-real-secret',json.dumps(result))

    async def test_transport_does_not_follow_redirects(self):
        async with safe_client() as client:self.assertFalse(client.follow_redirects)
        requests=[]
        async def serve(reader,writer):
            try:
                head=await reader.readuntil(b'\r\n\r\n');requests.append(head.decode().splitlines()[0])
                location=f'http://127.0.0.1:{port}/trap'
                writer.write(f'HTTP/1.1 307 Temporary Redirect\r\nLocation: {location}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'.encode());await writer.drain()
            finally:writer.close();await writer.wait_closed()
        server=await asyncio.start_server(serve,'127.0.0.1',0);port=server.sockets[0].getsockname()[1]
        async with server:
            async with safe_client() as client:
                response = await client.get(f'http://127.0.0.1:{port}/mcp')
                self.assertEqual(response.status_code,307)
        self.assertTrue(requests)
        self.assertFalse(any('/trap' in line for line in requests))

    async def test_stuck_worker_has_bounded_timeout(self):
        start=time.monotonic()
        with self.assertRaises(TimeoutError):
            await run_worker({}, command=[sys.executable,'-c','import time; time.sleep(60)'], deadline=0.5)
        self.assertLess(time.monotonic()-start,3)

if __name__=='__main__':unittest.main(verbosity=2)
