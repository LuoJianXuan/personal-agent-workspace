"""Explicit isolated acceptance upstream. Never a real search provider."""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
@app.post('/search')
async def search():
    return {'results':[{'title':'[验收 fixture] 方案 '+str(i),'url':f'http://web-fixture:8003/page/{i}','content':'合成资料，仅用于验证搜索、读取、引用与下载的真实服务链路。'} for i in range(1,4)]}
@app.get('/page/{id}',response_class=HTMLResponse)
async def page(id:int):
    return f'<html><title>[验收 fixture] 方案 {id}</title><main><h1>方案 {id}</h1><p>本材料为合成验收数据。月度成本 {id*100} 元，覆盖 {id+2} 个场景。方案之间存在成本和适用范围差异。</p><p>请以实际读取的内容为引用依据。这不是互联网研究结果。</p></main></html>'
