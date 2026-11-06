"""Fixed file tools: data parsing and Decimal aggregation, never model-generated code."""
import csv,io,json,math,hashlib,re
from datetime import datetime,timezone
from uuid import UUID,uuid5
from decimal import Decimal,InvalidOperation
from contracts.validate import validate
from .models import RunError,safe_text

def summarize(text,file_id,args):
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    names=reader.fieldnames or []
    if not names or len(names)>30 or len(set(names))!=len(names) or any(not h for h in names):raise RunError('INVALID_CSV_HEADER')
    dim=args['dimension'];measure=args['measure'];agg=args['aggregation']
    if dim not in names or measure not in names:raise RunError('CSV_COLUMN_NOT_FOUND')
    groups={};rows=0
    for row in reader:
        rows+=1
        if rows>10000:raise RunError('CSV_ROW_LIMIT')
        if None in row or any(v is None for v in row.values()):raise RunError('INVALID_CSV')
        label=row[dim]
        if len(label)>200:raise RunError('CSV_LABEL_TOO_LONG')
        if label not in groups:
            if len(groups)>=50:raise RunError('CSV_GROUP_LIMIT')
            groups[label]=[Decimal(0),0]
        value=Decimal(0)
        if agg!='count':
            try:value=Decimal(row[measure].strip())
            except InvalidOperation:raise RunError('CSV_NON_NUMERIC') from None
            if not value.is_finite() or abs(value)>Decimal('1e15'):raise RunError('CSV_NON_NUMERIC')
        groups[label][0]+=value;groups[label][1]+=1
    points=[]
    for label,(total,count) in groups.items():
        value=count if agg=='count' else total if agg=='sum' else total/count
        value=float(value)
        if not math.isfinite(value):raise RunError('CSV_NON_NUMERIC')
        points.append({'label':label,'value':value})
    chart={'type':args['chart_type'],'file_id':file_id,'dimension':dim,'measure':measure,'aggregation':agg,'row_count':rows,'points':points,'unit':args.get('unit','')}
    validate('Chart',chart)
    output=io.StringIO(newline='');writer=csv.writer(output)
    def cell(value):return "'"+value if value.startswith(('=','+','-','@','\t','\r')) else value
    writer.writerow([cell(dim),cell(agg+'_'+measure)])
    for p in points:writer.writerow([cell(p['label']),p['value']])
    return chart,output.getvalue()

async def publish_artifact(engine,run,key,name,media,content):
    response=await engine.backend.post('/internal/artifacts',json={'run_id':run,'artifact_key':key,'name':name,'media_type':media,'content':content})
    if response.status_code!=200:raise RunError('ARTIFACT_STORAGE_FAILED')
    file=response.json();validate('File',file)
    if file['status']!='READY':raise RunError('ARTIFACT_NOT_READY')
    async with engine.pool.connection() as conn:
        async with conn.transaction():
            row=await (await conn.execute('INSERT INTO runtime.artifact_events(run_id,artifact_key,file_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING file_id',(run,key,file['id']))).fetchone()
            if row:await engine.event_on(conn,run,'artifact.ready',file)
    return file

async def publish_binary(engine,run,key,name,media,content,parent=None):
    meta={'run_id':run,'artifact_key':key,'name':name,'media_type':media}
    if parent:meta['parent_file_id']=parent
    response=await engine.backend.post('/internal/artifacts/blob',headers={'X-Artifact-Metadata':json.dumps(meta,ensure_ascii=True)},content=content)
    if response.status_code!=200:raise RunError('ARTIFACT_STORAGE_FAILED')
    file=response.json();validate('File',file)
    async with engine.pool.connection() as c:
        async with c.transaction():
            row=await (await c.execute('INSERT INTO runtime.artifact_events(run_id,artifact_key,file_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING file_id',(run,key,file['id']))).fetchone()
            if row:await engine.event_on(c,run,'artifact.ready',file)
    return file

class MaterialTools:
    def __init__(self,engine,start):self.engine=engine;self.start=start
    async def execute(self,name,args,eid):
        if name=='builtin_publish_report':return await self.report(args,eid)
        if name=='builtin_python':
            from .compute import compute
            return await compute(self.engine,self.start,args,eid)
        file_id=args['file_id'];refs=self.start['file_refs']
        if not any(f['id']==file_id for f in refs):raise RunError('FILE_NOT_AUTHORIZED')
        if name=='builtin_read_material':return json.dumps(await self.read(file_id,args),ensure_ascii=False)
        response=await self.engine.backend.get('/internal/files/'+file_id+'/content',params={'run_id':self.start['run_id']})
        if response.status_code!=200:raise RunError('FILE_UNAVAILABLE')
        content=response.json();validate('FileContent',content)
        if not any(f['id']==file_id and f['sha256']==content['file']['sha256'] for f in refs):raise RunError('FILE_CHANGED')
        if content['file']['media_type']=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            doc=await self.document(file_id)
            if not doc:raise RunError('PARSE_NOT_READY')
            groups={}
            for chunk in doc['chunks']:groups.setdefault(chunk['locator'].split(' · 行 ',1)[0],[]).append(chunk['text'])
            selected='工作表 '+args['sheet'] if args.get('sheet') else next(iter(groups),'')
            if selected not in groups:raise RunError('CSV_COLUMN_NOT_FOUND')
            if any(w.startswith('公式无缓存值：'+selected[4:]+'!') for w in doc['warnings']):raise RunError('FORMULA_CACHE_MISSING')
            content['text']=''.join(groups[selected])
        elif content['file']['media_type']!='text/csv':raise RunError('CSV_REQUIRED')
        chart,csv_text=summarize(content['text'],file_id,args)
        chart_file=await publish_artifact(self.engine,self.start['run_id'],eid+':chart','分析图表.json','application/json',json.dumps(chart,ensure_ascii=False))
        csv_file=await publish_artifact(self.engine,self.start['run_id'],eid+':csv','汇总结果.csv','text/csv',csv_text)
        return json.dumps({'calculation':'fixed_decimal_aggregation','source_file':content['file']['name'],'chart':chart,'artifacts':[chart_file['id'],csv_file['id']]},ensure_ascii=False)

    async def document(self,file_id):
        if not any(f['id']==file_id for f in self.start['file_refs']):raise RunError('FILE_NOT_AUTHORIZED')
        metadata=await self.engine.backend.get('/internal/files/'+file_id+'/content',params={'run_id':self.start['run_id'],'metadata_only':'1'})
        if metadata.status_code!=200:raise RunError('FILE_UNAVAILABLE')
        media=metadata.json()['file']['media_type']
        if media not in ('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'):return None
        from .document_tools import OnDemandDocuments
        doc=await OnDemandDocuments(self.engine,self.start).get(file_id)
        if not any(f['id']==file_id and f['sha256']==doc['sha256'] for f in self.start['file_refs']):raise RunError('FILE_CHANGED')
        if doc['status']!='ready':raise RunError('PARSE_UNSUPPORTED' if doc['status']=='unsupported' else 'PARSE_NOT_READY')
        return doc
    async def read(self,file_id,args):
        if not any(f['id']==file_id for f in self.start['file_refs']):raise RunError('FILE_NOT_AUTHORIZED')
        doc=await self.document(file_id)
        warnings=[]
        title=file_id
        if doc:
            chunks=doc['chunks'];sha=doc['sha256'];warnings=doc['warnings']
            metadata=await self.engine.backend.get('/internal/files/'+file_id+'/content',params={'run_id':self.start['run_id'],'metadata_only':'1'})
            if metadata.status_code==200:title=metadata.json()['file']['name']
        else:
            r=await self.engine.backend.get('/internal/files/'+file_id+'/content',params={'run_id':self.start['run_id']})
            if r.status_code!=200:raise RunError('FILE_UNAVAILABLE')
            content=r.json();validate('FileContent',content);sha=content['file']['sha256'];title=content['file']['name']
            if not any(f['id']==file_id and f['sha256']==sha for f in self.start['file_refs']):raise RunError('FILE_CHANGED')
            text=content['text'];chunks=[{'id':'text-'+str(i),'locator':f'正文字符 {i+1}–{min(i+3500,len(text))}','text':text[i:i+3500]} for i in range(0,len(text),3500)]
        query=args.get('query','');matches=[c for c in chunks if not query or query.lower() in c['text'].lower()]
        offset=args.get('offset',0);selected=matches[offset:offset+args.get('limit',10)];sources=[]
        for chunk in selected:
            text=chunk['text'][:4000]
            source={'source_id':str(uuid5(UUID(self.start['run_id']),'file:'+file_id+sha+chunk['id'])),'kind':'file','file_id':file_id,'title':title,'sha256':sha,'locator':chunk['locator'],'excerpt':safe_text(text),'read_status':'truncated' if len(chunk['text'])>4000 else 'read','retrieved_at':datetime.now(timezone.utc).isoformat()}
            sources.append(await self.engine.source(self.start['run_id'],source))
        return {'file_id':file_id,'sources':sources,'warnings':warnings,'total_chunks':len(matches),'next_offset':offset+len(selected) if offset+len(selected)<len(matches) else None,'untrusted_material':True}
    async def document_text(self,file_id):
        result=await self.read(file_id,{'limit':20})
        text='\n\n'.join('['+s['locator']+' · source:'+s['source_id']+']\n'+s['excerpt'] for s in result['sources'])
        if result['next_offset'] is not None:text+='\n[内容未全部读取，请用 builtin_read_material 的 offset/limit 继续读取]'
        return text
    async def report(self,args,eid):
        from .documents import DOCX,render_docx
        parent=args.get('parent_file_id')
        if parent and not any(f['id']==parent for f in self.start['file_refs']):raise RunError('FILE_NOT_AUTHORIZED')
        ids=args['source_ids'];mentioned=set(re.findall(r'\[source:([0-9a-f-]{36})\]',args['content']))
        if not mentioned.issubset(set(ids)):raise RunError('CITATION_INVALID')
        sources=[]
        async with self.engine.pool.connection() as c:
            for id in ids:
                row=await (await c.execute('SELECT data FROM runtime.sources WHERE source_id=%s AND run_id=%s',(id,self.start['run_id']))).fetchone()
                if not row or row['data']['read_status']=='search_only':raise RunError('CITATION_INVALID')
                sources.append(row['data'])
        text=safe_text(args['content'])
        text+='\n\n## 来源\n'+('\n'.join('- [source:'+s['source_id']+'] '+s['title']+' · '+s['locator']+(' · '+s['url'] if s.get('url') else '') for s in sources) if sources else '本报告未提供外部事实来源；请核对涉及事实的内容。')
        # Published text remains within the existing file boundary.
        if len(text)>50000:raise RunError('TEXT_TOO_LARGE')
        meta={'run_id':self.start['run_id'],'artifact_key':'report-'+eid+'.md','name':args['title'][:90]+'.md','media_type':'text/markdown','content':text}
        if parent:meta['parent_file_id']=parent
        response=await self.engine.backend.post('/internal/artifacts',json=meta)
        if response.status_code!=200:raise RunError('ARTIFACT_STORAGE_FAILED')
        file=response.json();validate('File',file)
        async with self.engine.pool.connection() as c:
            async with c.transaction():
                row=await (await c.execute('INSERT INTO runtime.artifact_events(run_id,artifact_key,file_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING file_id',(self.start['run_id'],meta['artifact_key'],file['id']))).fetchone()
                if row:await self.engine.event_on(c,self.start['run_id'],'artifact.ready',file)
        files=[file]
        if args.get('docx'):files.append(await publish_binary(self.engine,self.start['run_id'],'report-'+eid+'.docx',args['title'][:90]+'.docx',DOCX,render_docx(args['title'],text),parent))
        return json.dumps({'completed':True,'files':files,'source_ids':ids},ensure_ascii=False)

async def export_report(engine,run,format='markdown'):
    async with engine.pool.connection() as c:
        row=await (await c.execute('SELECT * FROM runtime.runs WHERE run_id=%s',(run,))).fetchone()
        results=await (await c.execute("SELECT tool_name,result FROM runtime.tool_executions WHERE run_id=%s AND status='SUCCEEDED' ORDER BY execution_id",(run,))).fetchall()
    if not row or row['status']!='SUCCEEDED':raise RunError('RUN_NOT_COMPLETED')
    start=row['start_payload'];model=start['effective_capabilities']['model']
    text='# 序光运行报告\n\n运行 ID：'+run+'\n\n模式：'+row['mode']+'\n\n模型：'+model['name']+' / '+model['provider_model_name']+'（revision '+str(model['revision'])+'）\n\n## 最终回答\n\n'+row['final_text']
    if results:text+='\n\n## 已成功执行的工具\n'
    for r in results:text+='\n### '+r['tool_name']+'\n\n```json\n'+r['result'][:1000].replace('```','` ` `')+'\n```\n'+('（工具结果已截取，完整内容见运行记录。）\n' if len(r['result'])>1000 else '')
    text+='\n\n说明：演示订单与工单均为合成数据。报告直接使用持久结果生成，没有再次调用模型。\n'
    if format=='docx':
        from .documents import DOCX,render_docx
        return await publish_binary(engine,run,'export.docx','运行报告.docx',DOCX,render_docx('序光运行报告',safe_text(text)))
    if format!='markdown':raise RunError('UNSUPPORTED_FILE')
    return await publish_artifact(engine,run,'report.md','运行报告.md','text/markdown',safe_text(text))
