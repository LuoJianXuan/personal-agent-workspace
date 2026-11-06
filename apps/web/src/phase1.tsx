import { useEffect, useState } from 'react';
import { Alert, Button, Collapse, Empty, Select, Space, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import { api } from './api';
import { validate } from './contracts/validate';
import type { Event as RunEvent, TaskUpdate, SourceRecord, ParsedDocument, File as StoredFile, FileList } from './contracts/models';

export function Phase1Activity({ events }: { events: RunEvent[] }) {
  const nav=useNavigate();
  const tasks=events.filter(e=>e.type==='task.updated').at(-1)?.payload as TaskUpdate|undefined;
  const sources=Array.from(new Map(events.filter(e=>e.type==='source.ready').map(e=>{const s=e.payload as SourceRecord;return [s.source_id,s] as const})).values());
  const compacted=events.some(e=>e.type==='context.compacted');
  const labels:Record<string,string>={pending:'待处理',in_progress:'进行中',completed:'已完成',failed:'失败',skipped:'已跳过'};
  if(!tasks&&!sources.length&&!compacted)return null;
  return <section className="phase1-activity">{compacted&&<Tag>已整理较早上下文，原历史保留</Tag>}
    <Collapse size="small" items={[
      ...(tasks?[{key:'steps',label:`工作步骤 · ${tasks.tasks.filter(t=>t.status==='completed').length}/${tasks.tasks.length}`,children:<ol className="task-steps">{tasks.tasks.map(t=><li key={t.id}><Tag color={t.status==='in_progress'?'processing':t.status==='completed'?'success':'default'}>{labels[t.status]}</Tag>{t.title}</li>)}</ol>}]:[]),
      ...(sources.length?[{key:'sources',label:`资料与来源 · ${sources.length}`,children:<div className="source-list">{sources.map(s=><article key={s.source_id}>
        <Space wrap><Tag>{s.kind==='file'?'资料':s.read_status==='search_only'?'搜索摘要':'已读取网页'}</Tag>{s.read_status==='truncated'&&<Tag color="warning">部分读取</Tag>}<strong>{s.title}</strong></Space>
        <p>{s.locator} · {new Date(s.retrieved_at).toLocaleString()}</p><blockquote>{s.excerpt}</blockquote>
        {s.url&&<a href={s.url} target="_blank" rel="noopener noreferrer">打开原网页</a>}
        {s.file_id&&<Button size="small" onClick={()=>nav(`/app/library?file=${s.file_id}&locator=${encodeURIComponent(s.locator)}`)}>定位资料</Button>}
        <small>引用：{s.source_id}</small>
      </article>)}</div>}]:[])
    ]}/>
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
  const [files,setFiles]=useState<StoredFile[]>([]);
  useEffect(()=>{let live=true;api<FileList>(`/files/${file.id}/versions`).then(r=>{if(live)setFiles(r.items)}).catch(()=>{if(live)setFiles([])});return()=>{live=false};},[file.id]);
  return files.length>1?<Space className="file-versions"><span>产物版本</span><Select value={selectedId||file.id} style={{minWidth:230}} options={files.map(f=>({value:f.id,label:`v${f.version||1} · ${f.name}`}))} onChange={id=>{const next=files.find(f=>f.id===id);if(next)onSelect(next)}}/></Space>:null;
}
