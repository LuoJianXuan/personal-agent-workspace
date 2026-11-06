"""Protocol configuration builds maintained ChatModels; no provider SSE parser."""
import os
import json
import httpx
from langchain_openai import ChatOpenAI
from .access import target

from .errors import RunError,safe_text,budget_window

class ChatCompletionsModel(ChatOpenAI):
    """Keep the declared wire protocol's max_tokens spelling.

    ChatOpenAI 1.7 rewrites this to OpenAI's max_completion_tokens. Compatible
    endpoints need not implement that newer field. Parsing/streaming stays upstream.
    """
    def _get_request_payload(self,input_,*,stop=None,**kwargs):
        payload=super()._get_request_payload(input_,stop=stop,**kwargs)
        if 'max_completion_tokens' in payload:payload['max_tokens']=payload.pop('max_completion_tokens')
        return payload

class BoundedModelStream(httpx.AsyncByteStream):
    def __init__(self,stream):self.stream=stream
    async def __aiter__(self):
        size=0
        async for chunk in self.stream:
            size+=len(chunk)
            if size>2*1024*1024:raise RunError('MODEL_RESPONSE_TOO_LARGE')
            yield chunk
    async def aclose(self):await self.stream.aclose()

class ModelTransport(httpx.AsyncBaseTransport):
    """Every physical request, including summary calls, reserves durable quota."""
    def __init__(self,engine,start):
        self.engine=engine;self.start=start;self.inner=httpx.AsyncHTTPTransport(retries=0);self.calls=[]
    async def handle_async_request(self,request):
        model=self.start['effective_capabilities']['model']
        if str(request.url)!=model['base_url'].rstrip('/')+'/chat/completions' or request.method!='POST':raise RunError('MODEL_TARGET_DENIED')
        body=json.loads(request.content)
        output=body.get('max_tokens')
        if body.get('model')!=model['provider_model_name'] or not isinstance(output,int) or output<1 or output>model['max_output_tokens'] or 'max_completion_tokens' in body:raise RunError('MODEL_OPTIONS_INVALID')
        await self.engine.authorize(self.start)
        call=await self.engine.reserve_model(self.start);self.calls.append(call)
        try:
            response=await self.inner.handle_async_request(request)
            response.stream=BoundedModelStream(response.stream)
            await self.engine.model_result(call,'USAGE_PENDING' if response.status_code==200 else 'FAILED',{},'' if response.status_code==200 else 'MODEL_UNAVAILABLE')
            return response
        except BaseException:
            await self.engine.model_result(call,'FAILED',{},'MODEL_TRANSPORT_INTERRUPTED');raise
    async def aclose(self):await self.inner.aclose()

def build_model(engine,start):
    if start['mode']=='mock':
        from .mock_model import MockChatModel
        return MockChatModel(engine=engine,start=start),None
    model=start['effective_capabilities']['model']
    if model['protocol']!='openai_chat_completions':raise RunError('MODEL_PROTOCOL_UNSUPPORTED')
    item=target('models',model['base_url'],model['credential_ref']);key=os.getenv(item['env_var'],'')
    if not key:raise RunError('MODEL_CREDENTIAL_MISSING')
    options=model['protocol_options']
    if options not in ({},{'thinking':{'type':'disabled'}}):raise RunError('MODEL_OPTIONS_INVALID')
    transport=ModelTransport(engine,start)
    client=httpx.AsyncClient(transport=transport,trust_env=False,follow_redirects=False,timeout=httpx.Timeout(60,connect=3))
    chat=ChatCompletionsModel(model=model['provider_model_name'],base_url=model['base_url'],api_key=key,
        use_responses_api=False,streaming=True,max_tokens=model['max_output_tokens'],
        max_retries=0,timeout=60,http_async_client=client,extra_body=options,
        stream_usage=True)
    return chat,(client,transport)
