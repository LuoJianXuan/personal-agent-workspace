import { useEffect, useState } from 'react';
import { Alert, Button, Card, Collapse, Empty, Select, Space, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import { api, downloadFile } from './api';
import { validate } from './contracts/validate';
import type { Event as RunEvent, TaskUpdate, SourceRecord, ParsedDocument, File as StoredFile, FileList } from './contracts/models';

export function Phase1Activity({ events }: { events: RunEvent[] }) {
  const nav=useNavigate();
  const tasks=events.filter(e=>e.type==='task.updated').at(-1)?.payload as TaskUpdate|undefined;
  const sources=Array.from(new Map(events.filter(e=>e.type==='source.ready').map(e=>{const s=e.payload as SourceRecord;return [s.source_id,s] as const})).values());
  const compacted=events.some(e=>e.type==='context.compacted');
  const labels:Record<string,string>={pending:'待处理',in_progress:'进行中',completed:'已完成',failed:'失败',skipped:'已跳过'};
  if(!tasks&&!sources.length&&!compacted)return null;
  const completed=tasks?.tasks.filter(t=>t.status==='completed').length||0;
  return <section className="phase1-activity">
    {tasks&&<Card size="small" className="plan-card" title="执行计划" extra={<Tag color={completed===tasks.tasks.length?'success':'processing'}>{completed}/{tasks.tasks.length}</Tag>}>
      <ol className="task-steps">{tasks.tasks.map(t=><li key={t.id} className={`task-${t.status}`}><span className="task-marker" aria-hidden="true"/><div><Tag color={t.status==='in_progress'?'processing':t.status==='completed'?'success':t.status==='failed'?'error':'default'}>{labels[t.status]}</Tag><span>{t.title}</span></div></li>)}</ol>
    </Card>}
    {compacted&&<Tag>已整理较早上下文，原历史保留</Tag>}
    {sources.length>0&&<Collapse size="small" items={[
      {key:'sources',label:`资料与来源 · ${sources.length}`,children:<div className="source-list">{sources.map(s=><article key={s.source_id}>
        <Space wrap><Tag>{s.kind==='file'?'资料':s.read_status==='search_only'?'搜索摘要':'已读取网页'}</Tag>{s.read_status==='truncated'&&<Tag color="warning">部分读取</Tag>}<strong>{s.title}</strong></Space>
        <p>{s.locator} · {new Date(s.retrieved_at).toLocaleString()}</p><blockquote>{s.excerpt}</blockquote>
        {s.url&&<a href={s.url} target="_blank" rel="noopener noreferrer">打开原网页</a>}
        {s.file_id&&<Button size="small" onClick={()=>nav(`/app/library?file=${s.file_id}&locator=${encodeURIComponent(s.locator)}`)}>定位资料</Button>}
        <small>引用：{s.source_id}</small>
      </article>)}</div>}
    ]}/>}
  </section>;
}

export function DocumentPreview({file,locator}:{file:StoredFile;locator?:string}){
  const [doc,setDoc]=useState<ParsedDocument>(),[error,setError]=useState(''),[limit,setLimit]=useState(100),[extracting,setExtracting]=useState(false);
  useEffect(()=>{let live=true;setDoc(undefined);setError('');setLimit(100);setExtracting(false);
    api(`/files/${file.id}/parsed`).then(value=>{if(live)setDoc(validate<ParsedDocument>('ParsedDocument',value))}).catch(e=>{if(live)setError(e instanceof Error?e.message:'解析结果不可用')});
    return()=>{live=false};
  },[file.id]);
  const extract=async()=>{setExtracting(true);setError('');try{setDoc(validate<ParsedDocument>('ParsedDocument',await api(`/files/${file.id}/extract`,{method:'POST'})))}catch(e){setError(e instanceof Error?e.message:'提取失败')}finally{setExtracting(false)}};
  if(error)return <Alert type="warning" message={error} description="原文件仍可下载。"/>;
  if(!doc)return <p>正在读取解析状态…</p>;
  if(doc.status!=='ready')return <Space direction="vertical"><Alert type={doc.status==='failed'||doc.status==='unsupported'?'warning':'info'} message={doc.status==='not_extracted'?'文件已保存，尚未提取':`解析状态：${doc.status}`} description={doc.error||'按需提取不会创建 Agent 运行，也不会调用模型。'}/>{doc.status!=='unsupported'&&<Button loading={extracting} onClick={extract}>{doc.status==='not_extracted'?'提取并预览':'重试提取'}</Button>}</Space>;
  const chunks=locator?doc.chunks.filter(c=>c.locator===locator):doc.chunks.slice(0,limit);
  return <div className="parsed-document">{doc.warnings.map((w,i)=><Alert key={i} type="warning" message={w}/>)}
    {chunks.length?chunks.map(c=><section key={c.id} className={locator?'source-highlight':''}><strong>{c.locator}</strong><pre className="file-preview">{c.text}</pre></section>):<Empty description="未找到该定位，可下载原文件核对"/>}
    {!locator&&limit<doc.chunks.length&&<Button onClick={()=>setLimit(limit+100)}>继续显示片段（{limit}/{doc.chunks.length}）</Button>}
  </div>;
}

export function FileVersions({file,onSelect,selectedId}:{file:StoredFile;selectedId?:string;onSelect:(f:StoredFile)=>void}){
  const nav=useNavigate();
  const [files,setFiles]=useState<StoredFile[]>([]),[error,setError]=useState('');
  useEffect(()=>{let live=true;setError('');api<FileList>(`/files/${file.id}/versions`).then(r=>{if(live)setFiles(r.items)}).catch(()=>{if(live)setError('版本列表暂不可用，请稍后重试')});return()=>{live=false};},[file.id]);
  if(file.source!=='generated')return null;
  const chosen=files.find(f=>f.id===(selectedId||file.id))||file;
  return <Space direction="vertical" style={{width:'100%',marginBottom:16}}>
    {error&&<Alert type="warning" message={error}/>}
    <Space wrap className="file-versions"><span>产物版本</span><Select value={chosen.id} style={{minWidth:230,maxWidth:'100%'}} options={(files.length?files:[file]).map(f=>({value:f.id,label:`v${f.version||1} · ${f.name}`}))} onChange={id=>{const next=files.find(f=>f.id===id);if(next)onSelect(next)}}/>
      <Button size="small" disabled={chosen.status!=='READY'} onClick={()=>downloadFile(chosen.id,chosen.name).catch(()=>setError('下载暂不可用，请检查文件状态后重试'))}>下载此版本</Button>
      <Button size="small" disabled={chosen.status!=='READY'} onClick={()=>nav(`/app/chat?file=${chosen.id}`)}>基于此版本继续</Button>
    </Space>
    <Space wrap><Tag>{chosen.status==='READY'?'可用':chosen.status==='PENDING'?'正在发布':'发布失败'}</Tag><span>{new Date(chosen.created_at).toLocaleString()}</span>
      {chosen.source_thread_id&&<Button size="small" type="link" onClick={()=>nav(`/app/chat?thread=${chosen.source_thread_id}`)}>来源会话</Button>}
    </Space>
  </Space>;
}
