import { DocumentPreview, FileVersions } from "./phase1";
import { createPortal } from "react-dom";
import { Icon } from "./workspace-ui";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Collapse, Drawer, Popover, Empty, Form, Input, List, Select, Space, Tag, Typography, Upload } from "antd";
import { useNavigate } from "react-router-dom";
import Markdown from "react-markdown";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, AriaComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer]);
import { api, downloadFile } from "./api";
import { validate } from "./contracts/validate";
import type { Approval, Chart, File as StoredFile, FileContent, FileList, Submission, Thread, Scenario } from "./contracts/models";
const message = (e: unknown) => e instanceof Error ? e.message : "请求失败";
const terminal = (s: string) => ["SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(s);
async function upload(file: File) {
  if (file.size > 5 * 1024 * 1024) throw Error("文件不能超过 5 MB");
  const form = new FormData(); form.append("file", file);
  return validate<StoredFile>("File", await api("/files", { method: "POST", body: form }));
}
export function ChartView({ chart }: { chart: Chart }) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    validate("Chart", chart);
    const view = echarts.init(element.current!);
    view.setOption({ color: ["#2e6268"], tooltip: { trigger: "axis", renderMode: "richText" },
      grid: { left: 60, right: 24, top: 35, bottom: 65 },
      xAxis: { type: "category", data: chart.points.map(p => p.label), axisLabel: { rotate: 20, width: 90, overflow: "truncate" } },
      yAxis: { type: "value", name: chart.unit || chart.measure },
      series: [{ type: chart.type, data: chart.points.map(p => p.value) }], aria: { enabled: true } });
    const observer = new ResizeObserver(() => view.resize()); observer.observe(element.current!);
    return () => { observer.disconnect(); view.dispose(); };
  }, [chart]);
  return <><div ref={element} style={{ width: "100%", height: 320 }} role="img" aria-label={`${chart.dimension} ${chart.measure} ${chart.aggregation} 图表`} />
    <Typography.Text type="secondary">来源文件 {chart.file_id} · {chart.row_count} 行 · {chart.aggregation} · 固定程序计算</Typography.Text></>;
}
function FilePreview({ file: original }: { file: StoredFile }) {
  const [chosen,setChosen]=useState<StoredFile>();
  useEffect(()=>setChosen(undefined),[original.id]);
  const file=chosen||original;
  const binary=file.media_type.startsWith("application/vnd.openxmlformats")||file.media_type==="application/pdf";
  const [content, setContent] = useState<FileContent>(), [error, setError] = useState("");
  useEffect(() => { let live = true; setContent(undefined); setError("");
    if(binary)return ()=>{live=false};
    api<FileContent>(`/files/${file.id}/content`).then(r => { if (live) setContent(validate("FileContent", r)); }).catch(e => { if (live) setError(message(e)); });
    return () => { live = false; };
  }, [file.id]);
  let chart: Chart | undefined;
  try { if (content && file.media_type === "application/json") chart = validate<Chart>("Chart", JSON.parse(content.text)); } catch { return <Alert type="error" message="图表格式无效" />; }
  if(binary)return <><FileVersions file={original} selectedId={file.id} onSelect={setChosen}/><DocumentPreview file={file} locator={new URLSearchParams(window.location.search).get("locator")||undefined}/></>;
  return <><FileVersions file={original} selectedId={file.id} onSelect={setChosen}/>{error && <Alert type="error" message={error} description="可尝试下载原文件；超过预览限制的 CSV 仍可用于数据分析。" />}
    {chart ? <ChartView chart={chart} /> : content && (file.media_type === "text/markdown" ? <Markdown skipHtml components={{ img: () => null }}>{content.text}</Markdown> : <pre className="file-preview">{content.text}</pre>)}</>;
}
function FileActions({ file, preview, fail }: { file: StoredFile; preview: (f: StoredFile) => void; fail: (e: string) => void }) {
  return <Space wrap><Button size="small" onClick={() => preview(file)}>预览</Button><Button size="small" onClick={() => downloadFile(file.id, file.name).catch(e => fail(message(e)))}>下载</Button></Space>;
}
export function Library() {
  const nav = useNavigate(); const [files, setFiles] = useState<StoredFile[]>([]), [q, setQ] = useState(""), [source, setSource] = useState(""), [offset, setOffset] = useState(0), [more, setMore] = useState(false), [error, setError] = useState(""), [preview, setPreview] = useState<StoredFile>(), [busy, setBusy] = useState(false);
  const load = () => api<FileList>(`/files?q=${encodeURIComponent(q)}&source=${source}&offset=${offset}`).then(r => { setFiles(r.items); setMore(r.has_more); }).catch(e => setError(message(e)));
  useEffect(() => { void load(); }, [q, source, offset]);
  useEffect(()=>{const id=new URLSearchParams(window.location.search).get("file");if(id)api<StoredFile>(`/files/${id}`).then(setPreview).catch(e=>setError(message(e)));},[]);
  const sourceOptions = [{ value: "", label: "全部资料" }, { value: "upload", label: "上传资料" }, { value: "generated", label: "生成产物" }];
  return <section className="library-page">
    <div className="workspace-page-heading"><div><span className="page-kicker">工作资料</span><h1>资料库</h1><p>整理上传文件与生成产物，在对话中继续使用。</p></div>
      <Upload accept=".txt,.md,.csv,.pdf,.docx,.xlsx" showUploadList={false} beforeUpload={file => { setBusy(true); setError(""); upload(file).then(() => load()).catch(e => setError(message(e))).finally(() => setBusy(false)); return false; }}><Button type="primary" icon={<Icon name="plus" size={16} />} loading={busy}>上传资料</Button></Upload>
    </div>
    <div className="library-layout"><aside className="library-categories" aria-label="资料分类">
      {sourceOptions.map(item => <button key={item.value} className={source === item.value ? "selected" : ""} onClick={() => { setSource(item.value); setOffset(0); }}><Icon name="library" size={16} />{item.label}</button>)}
      <p>支持 TXT、Markdown、CSV、文字 PDF、DOCX、XLSX。<br />单个文件不超过 5 MB。</p>
    </aside><div className="library-main">
      <div className="library-list-heading"><strong>{sourceOptions.find(item => item.value === source)?.label}</strong><span className="muted">本页 {files.length} 份资料</span></div>
      <div className="library-search"><Input.Search aria-label="搜索文件" placeholder="搜索资料名称…" onSearch={v => { setQ(v); setOffset(0); }} allowClear /><Select aria-label="文件来源" value={source} onChange={v => { setSource(v); setOffset(0); }} options={sourceOptions} /></div>
      {error && <Alert type="error" message={error} closable onClose={() => setError("")} />}
      <List className="library-files" dataSource={files} locale={{ emptyText: <div className="artifact-empty"><Icon name="library" size={44} /><h3>还没有匹配的资料</h3><p>上传一份资料，或把对话中的成果留在这里。</p></div> }} renderItem={f => <List.Item><div className="file-row"><div className="library-file-info"><span className="file-type-icon"><Icon name={f.media_type === "text/csv" ? "chart" : "library"} size={20} /></span><div><Typography.Text strong>{f.name}</Typography.Text><p className="muted">{f.source === "upload" ? "上传资料" : "生成产物"} · {(f.size / 1024).toFixed(1)} KB · {new Date(f.created_at).toLocaleDateString()}</p></div></div><Space wrap><FileActions file={f} preview={setPreview} fail={setError} /><Button size="small" onClick={() => nav(`/app/chat?file=${f.id}`)}>用于对话</Button>{f.media_type === "text/csv" && <Button size="small" onClick={() => nav(`/app/scenes/data-analysis?file=${f.id}`)}>分析数据</Button>}</Space></div></List.Item>} />
      <div className="library-pagination"><span className="muted">第 {Math.floor(offset / 50) + 1} 页</span><Space><Button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>上一页</Button><Button disabled={!more} onClick={() => setOffset(offset + 50)}>下一页</Button></Space></div>
    </div></div>
    <Drawer width={760} title={preview?.name} open={!!preview} onClose={() => setPreview(undefined)}>{preview && <FilePreview file={preview} />}</Drawer>
  </section>;
}

export function FilePicker({ value, onChange, disabled, compact = false }: { value: string[]; onChange: (v: string[]) => void; disabled?: boolean; compact?: boolean }) {
  const [options, setOptions] = useState<StoredFile[]>([]), [error, setError] = useState("");
  const search = (q = "") => api<FileList>(`/files?q=${encodeURIComponent(q)}`).then(async r => {
    const missing = await Promise.all(value.filter(id => !r.items.some(f => f.id === id)).map(id => api<StoredFile>(`/files/${id}`)));
    setOptions([...r.items, ...missing]);
  }).catch(e => setError(message(e)));
  useEffect(() => { void search(); }, [value.join(",")]);
  const picker = <div className="file-picker"><Space wrap><Select aria-label="本轮资料" mode="multiple" maxCount={3} showSearch filterOption={false} onSearch={search} value={value} onChange={onChange} disabled={disabled} placeholder="选择本轮资料（最多 3 份）" style={{ minWidth: 260, maxWidth: "100%" }} options={options.map(f => ({ value: f.id, label: f.name }))} />
    <Upload disabled={disabled || value.length >= 3} accept=".txt,.md,.csv,.pdf,.docx,.xlsx" showUploadList={false} beforeUpload={file => { upload(file).then(f => onChange([...value, f.id])).catch(e => setError(message(e))); return false; }}><Button disabled={disabled || value.length >= 3}>上传并选择</Button></Upload></Space>{error && <Alert type="error" message={error} closable onClose={() => setError("")} />}</div>;
  return compact ? <Popover title="选择本轮资料" trigger="click" placement="topLeft" content={picker}><Button type="text" icon={<Icon name="library" size={16} />}>资料库{value.length > 0 ? ` · ${value.length}` : ""}</Button></Popover> : picker;
}
export function RunPanel({ id, onStatus, artifactsTarget }: { id: string; onStatus: (r: Submission) => void; artifactsTarget?: HTMLElement | null }) {
  const [run, setRun] = useState<Submission>(), [approvals, setApprovals] = useState<Approval[]>([]), [files, setFiles] = useState<StoredFile[]>([]), [error, setError] = useState(""), [busy, setBusy] = useState(false), [preview, setPreview] = useState<StoredFile>();
  useEffect(() => {
    let live = true; let timer: ReturnType<typeof setTimeout>; setApprovals([]); setFiles([]); setRun(undefined); setError("");
    const poll = async () => { try { const r = await api<Submission>(`/runs/${id}`); if (!live) return; setRun(r); onStatus(r);
      if(r.status==='PENDING'||r.status==='QUEUED'){setError('');return;}
      const [a, f] = await Promise.all([api<{ items: Approval[] }>(`/runs/${id}/approvals`), api<FileList>(`/runs/${id}/artifacts`)]);
      if (live) { setApprovals(a.items); setFiles(f.items); setError(previous => ["NOT_FOUND", "RUNTIME_UNAVAILABLE", "连接失败，请检查网络后重试"].includes(previous) ? "" : previous); }
    } catch (e) { if (live) setError(message(e)); } finally { if (live) timer = setTimeout(poll, 2000); } }; void poll();
    return () => { live = false; clearTimeout(timer); };
  }, [id, onStatus]);
  async function act(path: string, body?: unknown) { setBusy(true); setError(""); try { await api(path, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) }); } catch (e) { setError(message(e)); } finally { setBusy(false); } }
  const artifacts = files.length > 0 ? <div className="artifact-files"><List dataSource={files} renderItem={f => <List.Item><div className="file-row"><div className="artifact-file-name"><Icon name="library" /><strong>{f.name}</strong></div><FileActions file={f} preview={setPreview} fail={setError} /></div></List.Item>} />{files.filter(f => f.media_type === "application/json").map(f => <FilePreview key={f.id} file={f} />)}</div> : <div className="artifact-empty"><Icon name="library" size={44} /><h3>还没有产物</h3><p>{run?.status === "SUCCEEDED" ? "可以导出本轮报告，或继续对话生成文件。" : "本轮生成的报告与图表将显示在这里。"}</p></div>;
  return <div className="run-panel">{error && <Alert type="warning" message={error} closable onClose={() => setError("")} />}
    {approvals.map(a => <Card key={a.approval_id} size="small" className="approval-card" title="创建演示工单 · 需要你的决定" extra={<Tag color={a.status === "PENDING" ? "orange" : "default"}>{a.status}</Tag>}>
      <Typography.Paragraph>以下完整参数将写入演示工单。批准只适用于本次执行，参数不能修改。</Typography.Paragraph><pre className="file-preview">{JSON.stringify(JSON.parse(a.canonical_args), null, 2)}</pre>
      <Typography.Paragraph type="secondary">有效期至 {new Date(a.expires_at).toLocaleString()} · 能力版本 {a.capability_revision}</Typography.Paragraph>
      <Collapse items={[{ key: "binding", label: "查看审批绑定信息", children: <pre className="file-preview">{JSON.stringify({ approval_id: a.approval_id, execution_id: a.execution_id, run_id: a.run_id, snapshot_id: a.snapshot_id, args_hash: a.args_hash }, null, 2)}</pre> }]} />
      {a.status === "PENDING" && run?.status === "WAITING_APPROVAL" && <Space><Button type="primary" loading={busy} disabled={Date.parse(a.expires_at) <= Date.now()} onClick={() => act(`/approvals/${a.approval_id}/decision`, { decision: "approve" })}>批准并继续</Button><Button danger loading={busy} onClick={() => act(`/approvals/${a.approval_id}/decision`, { decision: "reject" })}>拒绝</Button></Space>}
    </Card>)}
    <Space wrap>{run && !terminal(run.status) && <Button danger loading={busy} disabled={run.cancel_requested} onClick={() => act(`/runs/${id}/cancel`)}>{run.cancel_requested ? "正在取消" : "取消任务"}</Button>}
      {run?.status === "WAITING_APPROVAL" && <Button loading={busy} onClick={() => act(`/runs/${id}/resume`)}>重试已保存的决定</Button>}
      {run?.status === "SUCCEEDED" && <Button loading={busy} onClick={() => act(`/runs/${id}/artifacts`)}>导出 Markdown 报告</Button>}
      {run?.status === "SUCCEEDED" && <Button loading={busy} onClick={() => act(`/runs/${id}/artifacts?format=docx`)}>导出 Word 报告</Button>}</Space>
    {artifactsTarget ? createPortal(artifacts, artifactsTarget) : artifactsTarget === undefined && files.length > 0 ? <Card size="small" title="本轮产物">{artifacts}</Card> : null}
    <Drawer title={preview?.name} width={760} open={!!preview} onClose={() => setPreview(undefined)}>{preview && <FilePreview file={preview} />}</Drawer>
  </div>;
}
export function DataAnalysis() {
  const nav = useNavigate(); const [files, setFiles] = useState<StoredFile[]>([]), [columns, setColumns] = useState<string[]>([]), [error, setError] = useState(""), [busy, setBusy] = useState(false); const [form] = Form.useForm();
  const initialFile = new URLSearchParams(window.location.search).get("file"); const key = useRef<{ signature: string; thread: string; id: string } | undefined>(undefined);
  async function select(id: string) { setColumns([]); form.setFieldsValue({ dimension: undefined, measure: undefined }); try { const r = await api<FileContent>(`/files/${id}/content?columns_only=1`); setColumns(r.columns); } catch (e) { setError(message(e)); } }
  const load = (q = "") => api<FileList>(`/files?q=${encodeURIComponent(q)}`).then(async r => { if (initialFile && !r.items.some(f => f.id === initialFile)) r.items.push(await api(`/files/${initialFile}`)); setFiles(r.items.filter(f => f.media_type === "text/csv")); }).catch(e => setError(message(e)));
  useEffect(() => { void load(); if (initialFile) { form.setFieldValue("file", initialFile); void select(initialFile); } }, []);
  async function submit(v: Scenario & { file: string; question: string }) {
    setBusy(true); setError(""); try {
      const body = { skill_ids: [], input: v.question || "请基于固定计算结果概括趋势和注意事项。", file_ids: [v.file], scenario: { dimension: v.dimension, measure: v.measure, aggregation: v.aggregation, chart_type: v.chart_type, unit: v.unit || "" } };
      const signature = JSON.stringify(body);
      if (key.current?.signature !== signature) { const t = await api<Thread>("/threads", { method: "POST", body: JSON.stringify({ title: "数据分析" }) }); key.current = { signature, thread: t.id, id: crypto.randomUUID() }; }
      await api(`/threads/${key.current.thread}/runs`, { method: "POST", headers: { "Idempotency-Key": key.current.id }, body: JSON.stringify(body) }); nav(`/app/chat?thread=${key.current.thread}`);
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <Card title="数据分析"><Typography.Paragraph>选择 CSV 与统计口径，固定程序生成汇总和图表，模型负责解读。沿用同一条对话、审批和运行记录链路。</Typography.Paragraph>{error && <Alert type="error" message={error} />}
    <Form form={form} layout="vertical" initialValues={{ aggregation: "sum", chart_type: "bar" }} onFinish={submit} style={{ maxWidth: 680 }}>
      <Form.Item name="file" label="CSV 数据" rules={[{ required: true }]}><Select showSearch filterOption={false} onSearch={load} onChange={select} options={files.map(f => ({ value: f.id, label: f.name }))} /></Form.Item>
      <Button onClick={() => nav("/app/library")}>去资料库上传</Button>
      <Form.Item name="dimension" label="分组维度（最多 50 组）" rules={[{ required: true }]}><Select options={columns.map(c => ({ value: c, label: c }))} /></Form.Item>
      <Form.Item name="measure" label="指标列" rules={[{ required: true }]}><Select options={columns.map(c => ({ value: c, label: c }))} /></Form.Item>
      <Form.Item name="aggregation" label="计算方式"><Select options={[{ value: "sum", label: "求和" }, { value: "count", label: "计数" }, { value: "avg", label: "平均值" }]} /></Form.Item>
      <Form.Item name="chart_type" label="图表"><Select options={[{ value: "bar", label: "柱状图" }, { value: "line", label: "折线图" }]} /></Form.Item>
      <Form.Item name="unit" label="单位（可选）"><Input maxLength={40} /></Form.Item><Form.Item name="question" label="希望了解什么（可选）"><Input.TextArea maxLength={2000} /></Form.Item>
      <Button type="primary" htmlType="submit" loading={busy}>分析并生成图表</Button>
    </Form></Card>;
}
