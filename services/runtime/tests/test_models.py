"""Authorized offline transport acceptance for the maintained ChatModel client."""
import json,os,unittest
from unittest.mock import patch
import httpx
from app.models import build_model,RunError

MODEL={'protocol':'openai_chat_completions','base_url':'https://model.example/v1','credential_ref':'fixture','protocol_options':{'thinking':{'type':'disabled'}},'provider_model_name':'fixture','max_output_tokens':64}
def packet(delta,finish=None):return 'data: '+json.dumps({'id':'fixture-1','object':'chat.completion.chunk','created':0,'model':'fixture','choices':[{'index':0,'delta':delta,'finish_reason':finish}]})+'\n\n'
class Engine:
 def __init__(self,limit=12):self.calls=0;self.limit=limit
 async def authorize(self,start):pass
 async def reserve_model(self,start):
  if self.calls>=self.limit:raise RunError('REAL_CALL_BUDGET_EXHAUSTED')
  self.calls+=1;return str(self.calls)
 async def model_result(self,*args):pass
class Models(unittest.IsolatedAsyncioTestCase):
 async def invoke(self,body,tools=None,engine=None):
  engine=engine or Engine();start={'mode':'real','effective_capabilities':{'model':MODEL}}
  with patch('app.models.target',return_value={'env_var':'WORKSPACE_FIXTURE_KEY'}),patch.dict(os.environ,{'WORKSPACE_FIXTURE_KEY':'offline-fixture-only'}):
   model,resources=build_model(engine,start)
   def handle(request):
    value=json.loads(request.content);self.assertEqual(value['thinking'],{'type':'disabled'});self.assertTrue(value['stream']);self.assertEqual(value['max_tokens'],64);self.assertNotIn('max_completion_tokens',value);self.assertEqual(request.url.path,'/v1/chat/completions')
    return httpx.Response(200,headers={'Content-Type':'text/event-stream'},text=body)
   resources[1].inner=httpx.MockTransport(handle)
   try:
    configured=model.bind_tools(tools) if tools else model
    return await configured.ainvoke('fixture'),engine
   finally:await resources[0].aclose()
 async def test_text_stream_and_reasoning_filter(self):
  result,engine=await self.invoke(packet({'role':'assistant','content':'你好','reasoning_content':'private-reason'})+packet({'content':'世界'},'stop')+'data: [DONE]\n\n')
  self.assertEqual(result.content,'你好世界');self.assertNotIn('private-reason',result.content);self.assertEqual(engine.calls,1)
 async def test_tool_arguments_are_assembled_by_standard_client(self):
  body=packet({'role':'assistant','tool_calls':[{'index':0,'id':'call-1','type':'function','function':{'name':'lookup','arguments':'{"order'}}]})+packet({'tool_calls':[{'index':0,'function':{'arguments':'_id":"1001"}'}}]},'tool_calls')+'data: [DONE]\n\n'
  result,_=await self.invoke(body,[{'type':'function','function':{'name':'lookup','description':'lookup','parameters':{'type':'object','properties':{'order_id':{'type':'string'}}}}}])
  self.assertEqual(result.tool_calls[0]['args'],{'order_id':'1001'});self.assertEqual(result.tool_calls[0]['id'],'call-1')
 async def test_actual_request_guard_can_stop_sdk(self):
  with self.assertRaises(RunError):await self.invoke(packet({'content':'x'},'stop')+'data: [DONE]\n\n',engine=Engine(0))
 async def test_missing_credential_fails_before_transport(self):
  with patch('app.models.target',return_value={'env_var':'ABSENT_PHASE1_KEY'}),patch.dict(os.environ,{},clear=True):
   with self.assertRaises(RunError):build_model(Engine(),{'mode':'real','effective_capabilities':{'model':MODEL}})
 async def test_unknown_protocol_is_not_platform_fallback(self):
  with self.assertRaises(RunError):build_model(Engine(),{'mode':'real','effective_capabilities':{'model':{**MODEL,'protocol':'unimplemented'}}})
 async def test_unknown_options_are_not_forwarded(self):
  with patch('app.models.target',return_value={'env_var':'WORKSPACE_FIXTURE_KEY'}),patch.dict(os.environ,{'WORKSPACE_FIXTURE_KEY':'offline-fixture-only'}):
   with self.assertRaises(RunError):build_model(Engine(),{'mode':'real','effective_capabilities':{'model':{**MODEL,'protocol_options':{'headers':{'Authorization':'override'}}}}})
if __name__=='__main__':unittest.main()
