"""Public research tools. Public web and paid search are separately enabled."""
import asyncio,hashlib,ipaddress,json,os,socket
from datetime import datetime,timezone
from urllib.parse import urlsplit,urlunsplit,urljoin,parse_qs
from uuid import UUID,uuid5
import httpx
from bs4 import BeautifulSoup
from .models import RunError,safe_text,budget_window

def fixture_active(start):
    return os.getenv('MODEL_MODE')=='mock' and os.getenv('ALLOW_MOCK')=='true' and start['mode']=='mock' and os.getenv('NETWORK_FIXTURE_URL')=='http://web-fixture:8003'

def fixture_page(url):
    return url in tuple('http://web-fixture:8003/page/'+str(i) for i in (1,2,3))

def normalized_url(value):
    try:
        p=urlsplit(value)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443):raise ValueError()
        if any(k.lower() in ('token','key','api_key','access_token','secret','password') for k in parse_qs(p.query)):raise ValueError()
        if len(value)>3000:raise ValueError()
        return urlunsplit((p.scheme,p.netloc,p.path or '/',p.query,''))
    except ValueError:raise RunError('NETWORK_TARGET_DENIED') from None

async def public_address(host,port):
    try:
        records=await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM),3)
        addresses=list(dict.fromkeys(r[4][0] for r in records))
        def safe(address):
            ip=ipaddress.ip_address(address)
            if not ip.is_global or ip.is_multicast or ip.is_reserved:return False
            mapped=getattr(ip,'ipv4_mapped',None) or getattr(ip,'sixtofour',None)
            if mapped and not mapped.is_global:return False
            return True
        if not addresses or any(not safe(a) for a in addresses):raise RunError('NETWORK_TARGET_DENIED')
        return addresses[0]
    except RunError:raise
    except Exception:raise RunError('SOURCE_UNAVAILABLE') from None

async def fetch_public(url):
    async with asyncio.timeout(20):
        async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=httpx.Timeout(15,connect=3)) as client:
            for redirect in range(4):
                url=normalized_url(url);parts=urlsplit(url)
                address=await public_address(parts.hostname,parts.port or (443 if parts.scheme=='https' else 80))
                # Pin the validated address; TLS still verifies the original hostname.
                pinned=httpx.URL(url).copy_with(host=address)
                req=client.build_request('GET',pinned,headers={'Host':parts.netloc,'Accept-Encoding':'identity','User-Agent':'AgentWorkspace/0.2'},extensions={'sni_hostname':parts.hostname})
                response=await client.send(req,stream=True)
                try:
                    if response.status_code in (301,302,303,307,308):
                        if redirect==3 or 'location' not in response.headers:raise RunError('SOURCE_UNAVAILABLE')
                        url=urljoin(url,response.headers['location']);continue
                    if response.status_code!=200 or response.headers.get('content-encoding','identity') not in ('','identity'):raise RunError('SOURCE_UNAVAILABLE')
                    media=response.headers.get('content-type','').lower()
                    if not any(m in media for m in ('text/html','text/plain','application/xhtml+xml')):raise RunError('SOURCE_UNAVAILABLE')
                    body=bytearray()
                    async for chunk in response.aiter_raw():
                        body.extend(chunk)
                        if len(body)>2*1024*1024:raise RunError('SOURCE_UNAVAILABLE')
                    text=body.decode('utf-8',errors='replace')
                    if 'html' in media:
                        soup=BeautifulSoup(text,'html.parser');title=soup.title.get_text(' ',strip=True) if soup.title else parts.hostname
                        for tag in soup(['script','style','nav','footer','noscript','iframe','form']):tag.decompose()
                        text=(soup.find('main') or soup.find('article') or soup).get_text('\n',strip=True)
                    else:title=parts.hostname
                    lines=[line.strip() for line in text.splitlines() if line.strip()]
                    if sum(map(len,lines))<30:raise RunError('SOURCE_UNAVAILABLE')
                    return url,title[:500],'\n'.join(lines)
                finally:await response.aclose()
    raise RunError('SOURCE_UNAVAILABLE')

class ResearchTools:
    def __init__(self,engine,start):self.engine=engine;self.start=start
    async def budget(self,kind,eid):
        if os.getenv('ENABLE_PUBLIC_WEB')!='true' or not self.start['effective_capabilities'].get('network_enabled'):raise RunError('NETWORK_DISABLED')
        async with self.engine.pool.connection() as c:
            async with c.transaction():
                await c.execute('SELECT pg_advisory_xact_lock(310005)')
                count=await (await c.execute('SELECT count(*) AS n FROM runtime.external_calls WHERE run_id=%s AND kind=%s',(self.start['run_id'],kind))).fetchone()
                if count['n']>=(2 if kind=='search' else 6):raise RunError('NETWORK_CALL_LIMIT')
                if kind=='search':
                    if not fixture_active(self.start):
                        if not os.getenv('SEARCH_CALL_BUDGET') or not os.getenv('SEARCH_CALL_BUDGET_SINCE'):raise RunError('SEARCH_BUDGET_REQUIRED')
                        allowed,since=budget_window('SEARCH')
                        total=await (await c.execute("SELECT count(*) AS n FROM runtime.external_calls WHERE kind='search' AND created_at>=%s::timestamptz",(since,))).fetchone()
                        if total['n']>=allowed:raise RunError('SEARCH_BUDGET_EXHAUSTED')
                await c.execute('INSERT INTO runtime.external_calls(execution_id,run_id,kind) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(eid,self.start['run_id'],kind))
    async def source(self,key,title,url,text,status,locator):
        source={'source_id':str(uuid5(UUID(self.start['run_id']),key)),'kind':'web','title':safe_text(title),'url':url,'sha256':hashlib.sha256(text.encode()).hexdigest(),'locator':locator,'excerpt':safe_text(text[:4000]),'read_status':status,'retrieved_at':datetime.now(timezone.utc).isoformat()}
        return await self.engine.source(self.start['run_id'],source)
    async def execute(self,name,args,eid):
        if name=='builtin_web_search':
            key=os.getenv('TAVILY_API_KEY','')
            fixture=fixture_active(self.start)
            if not key and not fixture:raise RunError('SEARCH_NOT_CONFIGURED')
            await self.budget('search',eid)
            try:
                async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=20) as client:
                    r=await client.post('http://web-fixture:8003/search' if fixture else 'https://api.tavily.com/search',headers={} if fixture else {'Authorization':'Bearer '+key},json={'query':safe_text(args['query']),'search_depth':'basic','max_results':args.get('max_results',5),'include_answer':False,'include_raw_content':False,'include_images':False,'auto_parameters':False})
                    if r.status_code!=200 or len(r.content)>2*1024*1024:raise RunError('SOURCE_UNAVAILABLE')
                    results=[]
                    for i,item in enumerate(r.json().get('results',[])[:5]):
                        try:url=item['url'] if fixture and fixture_page(item['url']) else normalized_url(item['url'])
                        except RunError:continue
                        results.append(await self.source(eid+str(i),item.get('title',url),url,item.get('content','')[:4000],'search_only','搜索摘要，未读取正文'))
                    if not results:raise RunError('SEARCH_EMPTY')
                    return json.dumps({'query':safe_text(args['query']),'sources':results},ensure_ascii=False)
            except RunError:raise
            except Exception:raise RunError('SOURCE_UNAVAILABLE') from None
        await self.budget('fetch',eid)
        try:
            if fixture_active(self.start) and fixture_page(args['url']):
                async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=10) as client:
                    r=await client.get(args['url']);r.raise_for_status();soup=BeautifulSoup(r.text,'html.parser');url=args['url'];title=soup.title.get_text();text=soup.get_text('\n',strip=True)
            else:url,title,text=await fetch_public(args['url'])
        except RunError:raise
        except Exception:raise RunError('SOURCE_UNAVAILABLE') from None
        truncated=len(text)>20000;text=text[:20000]
        sources=[]
        for i in range(0,len(text),3500):
            sources.append(await self.source(eid+':'+str(i),title,url,text[i:i+3500],'truncated' if truncated else 'read',f'正文字符 {i+1}–{i+len(text[i:i+3500])}'))
        return json.dumps({'sources':sources,'truncated':truncated,'untrusted_material':True},ensure_ascii=False)
