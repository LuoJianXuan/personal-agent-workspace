import { Phase1Activity } from "./phase1";
import { FilePicker, RunPanel } from "./delivery";
import { Fragment, useContext, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Input,
  Select,
  Space,
  Tag,
  Typography,
  List,
  Drawer,
  Collapse,
  Table,
} from "antd";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import type { ToolChatIntent } from "./tool-center";
import { createPortal } from "react-dom";
import { ConversationSidebar, Icon } from "./workspace-ui";
import Markdown from "react-markdown";
import { api, authHeaders, ApiError } from "./api";
import { validate } from "./contracts/validate";
import { PersonalConnections, usePersonalConnections } from "./connection-manager";
import { ToolResult } from "./tool-result";
import { AssistantReply, ReplyMarkdown } from "./assistant-reply";
import type {
  Thread,
  Message,
  Submission,
  Event as RunEvent,
  ModelCatalog,
  SkillConfig,
  Clarification,
} from "./contracts/models";
const terminal = (s: string) =>
  ["SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(s);
function errorText(e: unknown) {
  return e instanceof Error ? e.message : "请求失败";
}
const failureGuidance: Record<string, { title: string; detail: string }> = {
  REAL_CALL_BUDGET_EXHAUSTED: { title: "模型调用额度已用完", detail: "当前部署的模型调用额度已用完。请联系管理员调整额度后重试。若工具已返回结果，可在本轮工具卡查看。" },
  MCP_UNAVAILABLE: { title: "MCP 服务暂不可用", detail: "连接可能下线、超时或凭据失效。请在 MCP 管理中检查个人授权；平台服务请联系管理员。" },
  MCP_RATE_LIMIT: { title: "MCP 调用过于频繁", detail: "连接已达到本分钟调用上限。请稍后重试，本次不会自动重复外部操作。" },
  CONNECTION_AUTH_REQUIRED: { title: "个人 MCP 需要重新授权", detail: "服务已拒绝当前 Token。请在 MCP 管理中更换 Token 后重新提交。" },
  CONNECTION_REVOKED: { title: "个人连接已经断开", detail: "重新连接账户后，再提交原问题。" },
  TOOL_TIMEOUT: { title: "工具执行超时", detail: "远端工具没有在限制时间内返回。已停止等待；如果工具可能产生写入，请先核对外部系统再重试。" },
  TOOL_DENIED: { title: "工具当前不可用", detail: "工具未启用、已变更或不在本轮能力快照中。请检查当前 MCP 授权状态。" },
  NETWORK_DISABLED: { title: "本轮未允许联网", detail: "如需搜索或读取公开网页，请在输入区开启联网后重新发送。" },
  SEARCH_CREDENTIAL_MISSING: { title: "搜索服务尚未配置", detail: "公开网页直读仍可使用；搜索需要管理员配置搜索凭据与额度。" },
  COMPUTE_NOT_CONFIGURED: { title: "隔离计算尚未启用", detail: "当前任务需要 Python 沙箱。请启用计算环境后重试，系统不会在 Runtime 或宿主机直接运行生成代码。" },
  CAPABILITY_CHANGED: { title: "能力配置已经变化", detail: "本轮冻结的模型、技能或工具已被修改。请刷新能力状态后重新提交。" },
};
const unknownToolFailure = {
  title: "工具执行未完成",
  detail: "远端工具返回失败或中断。已有对话和产物仍会保留；请核对能力状态后再决定是否重试。",
};
function FailureCard({ code, retry, connections }: { code: string; retry: () => void; connections: () => void }) {
  const item=failureGuidance[code]||{title:"任务未完成",detail:`错误代码：${code}。已有结果仍会保留，可核对能力状态后重试。`};
  return <Alert className="actionable-failure" type="error" showIcon message={item.title} description={<><p>{item.detail}</p><Space wrap><Button size="small" onClick={retry}>将原问题放回输入框</Button>{/^(CONNECTION_|MCP_|TOOL_|CAPABILITY_)/.test(code) && <Button size="small" onClick={connections}>管理 MCP</Button>}</Space></>} />;
}
type Draft = {
  id: string;
  text: string;
  done: boolean;
  final: boolean;
  index: number;
};
export function Chat() {
  const location = useLocation();
  const navigate = useNavigate();
  const appliedIntent = useRef<string | undefined>(undefined);
  const connectors = usePersonalConnections();
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [connectorIds, setConnectorIds] = useState<string[]>();
  const [connectionAction, setConnectionAction] = useState(false);
  const [params, setParams] = useSearchParams();
  const tid = params.get("thread") || "";
  const [network,setNetwork]=useState(false);
  const [networkStatus,setNetworkStatus]=useState<{fetch_available:boolean;search_available:boolean;compute_available:boolean}>();
  const [threadQuery,setThreadQuery]=useState("");
  const [welcomeTarget,setWelcomeTarget]=useState<HTMLDivElement|null>(null);
  useEffect(()=>{api<{fetch_available:boolean;search_available:boolean;compute_available:boolean}>("/capabilities/network").then(setNetworkStatus).catch(()=>setNetworkStatus(undefined));},[]);
  const [fileIds, setFileIds] = useState<string[]>(params.get("file") ? [params.get("file")!] : []);
  const selectedRevisionFile = params.get("file");
  useEffect(() => { if (selectedRevisionFile) setFileIds([selectedRevisionFile]); }, [selectedRevisionFile]);
  const [threads, setThreads] = useState<Thread[]>([]),
    [messages, setMessages] = useState<Message[]>([]),
    [models, setModels] = useState<ModelCatalog[]>([]),
    [skills, setSkills] = useState<SkillConfig[]>([]);
  const [model, setModel] = useState<string>(),
    [selected, setSelected] = useState<string[] | undefined>(),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [runId, setRunId] = useState(""),
    [run, setRun] = useState<Submission>(),
    [events, setEvents] = useState<RunEvent[]>([]),
    [connection, setConnection] = useState("");
  const sidebar = useContext(ConversationSidebar);
  const [threadDrawer, setThreadDrawer] = useState(false);
  const [artifactsOpen, setArtifactsOpen] = useState(false);
  const [artifactsTarget, setArtifactsTarget] = useState<HTMLDivElement | null>(null);
  const scrollArea = useRef<HTMLDivElement>(null);
  const followBottom = useRef(true);
  useEffect(() => {
    if (followBottom.current && scrollArea.current) scrollArea.current.scrollTop = scrollArea.current.scrollHeight;
  }, [events, messages]);
  useEffect(() => { followBottom.current = true; }, [tid]);
  const pending = useRef<{ signature: string; key: string } | null>(null);
  useEffect(() => {
    const intent = (location.state as { toolIntent?: ToolChatIntent } | null)?.toolIntent;
    if (!intent || appliedIntent.current === intent.id) return;
    appliedIntent.current = intent.id;
    setInput(intent.draft);
    setSelected(intent.skillId ? [intent.skillId] : undefined);
    setConnectorIds(intent.connectorId ? [intent.connectorId] : undefined);
    navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: null });
  }, [location.state, location.pathname, location.search, navigate]);
  const refreshThreads = () =>
    api<{ items: Thread[] }>("/threads").then((r) => setThreads(r.items));
  useEffect(() => {
    refreshThreads().catch((e) => setError(errorText(e)));
    api<{ items: ModelCatalog[] }>("/catalog/models")
      .then((r) => setModels(r.items))
      .catch((e) => setError(errorText(e)));
    api<{ items: SkillConfig[] }>("/catalog/skills")
      .then((r) => setSkills(r.items))
      .catch((e) => setError(errorText(e)));
  }, []);
  useEffect(() => {
    let live = true;
    setMessages([]);
    setRunId("");
    setRun(undefined);
    setEvents([]);
    if (tid)
      api<{ items: Message[] }>(`/threads/${tid}/messages`)
        .then((r) => {
          if (live) {
            setMessages(r.items);
            setRunId(r.items.at(-1)?.run_id || "");
          }
        })
        .catch((e) => {
          if (live) setError(errorText(e));
        });
    return () => {
      live = false;
    };
  }, [tid]);
  useEffect(() => {
    if (!runId) return;
    let stopped = false;
    let current: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let idle: ReturnType<typeof setTimeout> | undefined;
    let seq = 0;
    let received = false;
    const saved: RunEvent[] = [];
    setEvents([]);
    setRun(undefined);
    const apply = (event: RunEvent) => {
      validate("Event", event);
      if (event.run_id !== runId) throw Error("运行事件不匹配");
      if (event.seq <= seq) return;
      if (event.seq !== seq + 1) throw Error("事件缺块，正在补读");
      seq = event.seq;
      received = true;
      saved.push(event);
      if (!stopped) {
        setEvents([...saved]);
        if (event.type === "run.started")
          setRun((r) =>
            r && !terminal(r.status) ? { ...r, status: "RUNNING", runtime_unavailable: false } : r,
          );
      }
    };
    async function connect() {
      current = new AbortController();
      try {
        if (!stopped) setConnection("正在连接");
        const initial = validate<Submission>(
          "Submission",
          await api(`/runs/${runId}`),
        );
        if (stopped) return;
        setRun(initial);
        const page = await api<{ items: RunEvent[]; has_more: boolean }>(
          `/runs/${runId}/events?after_seq=${seq}`,
        );
        if (stopped) return;
        page.items.forEach(apply);
        const response = await fetch(
          `/api/runs/${runId}/stream?after_seq=${seq}`,
          { headers: authHeaders(), signal: current.signal },
        );
        if (!response.ok || !response.body)
          throw Error(
            response.status === 429 ? "订阅达到上限，稍后重试" : "等待运行接入",
          );
        if (!stopped) setConnection("实时接收");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!stopped) {
          clearTimeout(idle);
          idle = setTimeout(() => current?.abort(), 45000);
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let end: number;
          while ((end = buffer.indexOf("\n\n")) >= 0) {
            const frame = buffer.slice(0, end);
            buffer = buffer.slice(end + 2);
            const line = frame.split("\n").find((l) => l.startsWith("data:"));
            if (line) apply(JSON.parse(line.slice(5)));
          }
        }
        if (stopped) return;
        const state = validate<Submission>(
          "Submission",
          await api(`/runs/${runId}`),
        );
        setRun(state);
        if (terminal(state.status)) {
          setConnection("已同步");
          const history = await api<{ items: Message[] }>(
            `/threads/${tid}/messages`,
          );
          if (!stopped) setMessages(history.items);
          return;
        }
      } catch (e) {
        if (!stopped) setConnection(e instanceof ApiError&&e.status===404&&!received?"等待运行接入":errorText(e));
      } finally {
        clearTimeout(idle);
      }
      if (!stopped) {
        try {
          const state = validate<Submission>(
            "Submission",
            await api(`/runs/${runId}`),
          );
          if (!stopped) setRun(state);
        } catch {
          /* retry preserves same cursor, never submits */
        }
        timer = setTimeout(connect, 1500);
      }
    }
    void connect();
    return () => {
      stopped = true;
      current?.abort();
      clearTimeout(timer);
      clearTimeout(idle);
    };
  }, [runId, tid]);
  async function create() {
    try {
      const t = await api<Thread>("/threads", {
        method: "POST",
        body: JSON.stringify({ title: "新对话" }),
      });
      await refreshThreads();
      setParams({ thread: t.id });
      setThreadDrawer(false);
      setInput("");
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function rename() {
    const title = window.prompt(
      "会话名称",
      threads.find((t) => t.id === tid)?.title,
    );
    if (!title?.trim()) return;
    try {
      await api(`/threads/${tid}`, {
        method: "PATCH",
        body: JSON.stringify({ title: title.trim() }),
      });
      await refreshThreads();
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function send() {
    if (!input.trim() || busy || active) return;
    if(selected===undefined&&skills.filter(s=>s.enabled&&s.personal_enabled).length>3){
      setError('个人默认技能超过 3 个，请明确选择最多 3 个技能，或点击“默认”切换为无技能。');
      return;
    }
    setBusy(true);
    setError("");
    setConnectionAction(false);
    const body = {
      input: input.trim(),
      file_ids: fileIds,
      network_enabled: network,
      ...(model ? { model_id: model } : {}),
      ...(selected ? { skill_ids: selected } : {}),
      ...(connectorIds ? { connector_ids: connectorIds } : {}),
    };
    try {
      let currentThread = tid;
      if (!currentThread) {
        const created = await api<Thread>("/threads", { method: "POST", body: JSON.stringify({ title: input.trim().slice(0, 36) }) });
        currentThread = created.id;
        setParams({ thread: currentThread });
        await refreshThreads();
      }
      const signature = JSON.stringify({ tid: currentThread, body });
      if (pending.current?.signature !== signature)
        pending.current = { signature, key: crypto.randomUUID() };
      followBottom.current = true;
      const result = validate<Submission>(
        "Submission",
        await api(`/threads/${currentThread}/runs`, {
          method: "POST",
          headers: { "Idempotency-Key": pending.current.key },
          body: JSON.stringify(body),
        }),
      );
      pending.current = null;
      setInput("");
      const history = await api<{ items: Message[] }>(
        `/threads/${currentThread}/messages`,
      );
      setMessages(history.items);
      setRunId(result.run_id);
      setRun(result);
    } catch (e) {
      setError(errorText(e));
      setConnectionAction(e instanceof ApiError && /^(CONNECTION_|SKILL_DEPENDENCY_)/.test(e.code));
    } finally {
      setBusy(false);
    }
  }
  const drafts: Draft[] = [];
  for (const e of events) {
    const p = e.payload as unknown as Record<string, unknown>;
    if (e.type === "message.started")
      drafts.push({
        id: String(p.message_id),
        text: "",
        done: false,
        final: false,
        index: 0,
      });
    if (e.type === "message.delta") {
      const d = drafts.find((d) => d.id === p.message_id);
      if (d && p.chunk_index === d.index) {
        d.text += String(p.text);
        d.index++;
      }
    }
    if (e.type === "message.completed") {
      const d = drafts.find((d) => d.id === p.message_id);
      if (d) {
        d.text = String(p.text);
        d.done = true;
        d.final = !!p.is_final;
      }
    }
  }
  const active = !!runId && (!run || !terminal(run.status));
  const persistedRuns = new Set(messages.filter(m => m.role === "assistant").map(m => m.run_id));
  const historyReplies = (id: string) => messages.filter(a => a.role === "assistant" && a.run_id === id).map(a => <article className="chat-message assistant" key={a.id}><div className="message-author"><span className="assistant-symbol"><Icon name="skill" size={14} /></span>序光</div><div className="message-body"><AssistantReply text={a.text} runId={id} events={id === runId ? events : undefined} /></div></article>);
  const toolEvents = events.filter(e => e.type.startsWith("tool."));
  const clarification=(events.filter(e=>e.type==="message.completed"&&Boolean((e.payload as {clarification?:Clarification}).clarification)).at(-1)?.payload as {clarification?:Clarification}|undefined)?.clarification;
  const toolRuns = Array.from(toolEvents.reduce((items, event) => {
    const payload = event.payload as unknown as { execution_id?: string; text?: string; status?: string };
    const key = payload.execution_id || event.event_id;
    const previous = items.get(key) || { key, name: "工具", result: "", status: "REQUESTED" };
    if (event.type === "tool.requested") previous.name = payload.text || "工具";
    if (event.type === "tool.completed" || event.type === "tool.failed") previous.result = payload.text || "";
    previous.status = payload.status || previous.status;
    items.set(key, previous);
    return items;
  }, new Map<string, { key: string; name: string; result: string; status: string }>()).values());
  const statusNames: Record<string, string> = { PENDING: "等待开始", QUEUED: "等待处理", RUNNING: "正在处理", WAITING_APPROVAL: "等待确认", SUCCEEDED: "已完成", FAILED: "运行失败", CANCELLED: "已取消", INTERRUPTED: "已中断" };
  const newButton = <Button block icon={<Icon name="plus" />} onClick={create}>新建对话</Button>;
  const visibleThreads=threads.filter(t=>t.title.toLowerCase().includes(threadQuery.toLowerCase()));
  const threadDay=(t:Thread)=>new Date(t.created_at).toLocaleDateString();
  const threadList = <section className="thread-panel" aria-label="近期对话">
    <div className="thread-heading"><Icon name="chat" size={15} /><span>近期对话</span><small>{threads.length}</small></div>
    <Input.Search aria-label="搜索会话标题" placeholder="搜索会话标题" allowClear value={threadQuery} onChange={e=>setThreadQuery(e.target.value)}/>
    <List dataSource={visibleThreads} locale={{ emptyText: <span className="thread-empty">开始你的第一段对话</span> }} renderItem={(t,index) => <List.Item><div className="recent-thread-item">{(index===0||threadDay(visibleThreads[index-1])!==threadDay(t))&&<small className="thread-date">{threadDay(t)}</small>}
      <Button type="text" block className={tid === t.id ? "thread-selected" : ""} title={t.title} onClick={() => { setParams({ thread: t.id }); setThreadDrawer(false); }}>{t.title}</Button></div>
    </List.Item>} />
  </section>;
  const composer = (<div className="composer-area">
          {selected===undefined&&skills.filter(s=>s.enabled&&s.personal_enabled).length>3&&<Alert type="warning" showIcon message="个人默认技能超过 3 个" description="请明确选择最多 3 个技能，或点击“默认”切换为无技能后发送。"/>}
          <div className="composer">
            <Input.TextArea aria-label="消息内容" placeholder="描述你想完成的工作…" maxLength={16000} value={input} onChange={e => setInput(e.target.value)} autoSize={{ minRows: 2, maxRows: 6 }} />
            <div className="composer-toolbar">
              <FilePicker value={fileIds} onChange={setFileIds} disabled={active || busy} compact />
              <Select aria-label="本轮技能" mode="multiple" placeholder="技能" variant="borderless" className="composer-skills" value={selected} onChange={setSelected} maxCount={3} maxTagCount="responsive" options={skills.filter(s => s.enabled).map(s => ({ value: s.id, label: s.name }))} notFoundContent="暂无可用技能" />
              <Button className="skill-preference" type="text" size="small" title={selected?.length === 0 ? "恢复个人技能偏好" : "本轮不使用技能"} onClick={() => setSelected(selected?.length === 0 ? undefined : [])}>{selected?.length === 0 ? "无技能" : "默认"}</Button>
              <Button type={network?"primary":"text"} disabled={!networkStatus?.fetch_available} title={networkStatus?.search_available?"允许本轮访问公开网页与搜索":"公开网页读取；搜索还需配置凭据与额度"} onClick={()=>setNetwork(!network)}>{network?"已允许联网":"联网"}</Button>
              <div className="composer-spacer" />
              <Select aria-label="本轮模型" placeholder="默认模型" variant="borderless" allowClear className="composer-model" value={model} onChange={setModel} options={models.map(m => ({ value: m.id, label: m.name }))} notFoundContent="暂无可用模型" />
              <Button className="send-button" type="primary" aria-label="发送消息" title="发送消息" icon={<Icon name="arrow" />} onClick={send} loading={busy} disabled={active || !input.trim()} />
            </div>
          </div>
          <p className="composer-note">{active ? "任务进行中，关闭页面后仍会继续执行。" : "回答由 AI 生成，请核对重要信息"}</p>
        </div>);
  return (
    <div className={`chat-workspace ${artifactsOpen ? "with-artifacts" : ""}`}>
      {sidebar.action && createPortal(newButton, sidebar.action)}
      {sidebar.recent && createPortal(threadList, sidebar.recent)}
      <Drawer title="近期对话" placement="left" open={threadDrawer} onClose={() => setThreadDrawer(false)}>{newButton}{threadList}</Drawer>
      <Drawer title="本轮 MCP" open={connectionsOpen} onClose={() => setConnectionsOpen(false)}>
        <Space direction="vertical" style={{ width: "100%" }}>
          <Select aria-label="选择本轮个人连接" mode="multiple" style={{ width: "100%" }}
            value={connectorIds ?? connectors.data?.items.filter((item) => item.status === "ready").map((item) => item.connector_id) ?? []}
            options={connectors.data?.items.filter((item) => item.status === "ready").map((item) => ({ value: item.connector_id, label: item.name }))}
            onChange={setConnectorIds} notFoundContent="暂无已安装的个人 MCP" />
          <Button type="text" onClick={() => setConnectorIds(undefined)}>使用全部已授权 MCP</Button>
          <PersonalConnections />
        </Space>
      </Drawer>
      <section className={`chat-main ${messages.length===0?"is-welcome":""}`} aria-label="对话工作台">
        <header className="chat-heading">
          <div className="chat-title"><Button className="mobile-threads" type="text" aria-label="打开近期对话" icon={<Icon name="chat" />} onClick={() => setThreadDrawer(true)} /><Icon name="chat" size={17} /><strong>{threads.find(t => t.id === tid)?.title || "新对话"}</strong>
            {tid && <Button type="text" size="small" aria-label="重命名对话" title="重命名对话" icon={<Icon name="edit" size={14} />} onClick={rename} />}
          </div>
          <Space>
            <Button size="small" icon={<Icon name="plug" size={14} />} onClick={() => setConnectionsOpen(true)}>MCP</Button>
            <Button type={artifactsOpen ? "primary" : "default"} aria-label={artifactsOpen ? "收起产物面板" : "打开产物面板"} aria-expanded={artifactsOpen} icon={<Icon name="panel" />} onClick={() => setArtifactsOpen(!artifactsOpen)} />
          </Space>
        </header>
        <div className="conversation" ref={scrollArea} onScroll={() => { const el = scrollArea.current; if (el) followBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }}>
          <div className="conversation-inner">
            {error && <Alert type="error" showIcon message={error} action={connectionAction && <Button onClick={() => setConnectionsOpen(true)}>管理 MCP</Button>} closable onClose={() => setError("")} />}
            {messages.length === 0 && <section className="chat-welcome">
              <h1>今天帮你完成什么？</h1>
              <p>带上资料，整理内容、比较方案，或交付一份报告。</p><div className="welcome-composer" ref={setWelcomeTarget}/>
              <div className="suggestion-grid">{[
                { icon: "library" as const, text: "阅读所选资料，整理重点并标明依据" },
                { icon: "chat" as const, text: "比较所选两份材料的变化，生成对比报告" },
                { icon: "chart" as const, text: "分析所选 CSV，先确认统计口径再生成图表" },
                { icon: "skill" as const, text: "根据提供的信息起草报告，输出可下载文件" },
              ].map(item => <button key={item.text} onClick={() => setInput(item.text)}><Icon name={item.icon} /><span>{item.text}</span></button>)}</div>
            </section>}
            <div aria-live="polite" aria-relevant="additions text">
              {messages.filter(m => m.role === "user").map(m => <Fragment key={m.id}>
                <article className="chat-message user"><div className="message-author">你</div><div className="message-body"><Markdown skipHtml components={{ img: () => null }}>{m.text}</Markdown></div>
                  {m.run_id !== runId && <Button size="small" type="text" disabled={active || busy} title={active ? "当前任务完成后可切换过程记录" : undefined} onClick={() => setRunId(m.run_id)}>查看本轮过程</Button>}
                </article>
                {m.run_id === runId ? <>
                  {drafts.filter(d => (!d.done || d.text.trim().length > 0) && (!persistedRuns.has(m.run_id) || (d.done && !d.final))).map(d => <article className="chat-message assistant" key={d.id}>
                    <div className="message-author"><span className="assistant-symbol"><Icon name="skill" size={14} /></span>序光{!d.done && <span className="message-progress">{run && terminal(run.status) ? "未完成" : "正在生成…"}</span>}</div>
                    <div className="message-body">{d.done && d.final ? <AssistantReply text={d.text} runId={m.run_id} events={events} /> : <ReplyMarkdown text={d.text} />}</div>
                  </article>)}
                  {historyReplies(m.run_id)}
                  {toolRuns.length > 0 && <Collapse ghost className="tool-process" items={[{ key: "tools", label: <span>工具执行 · {toolRuns.length} 项{toolRuns.some(t => t.status === "FAILED") && <Tag color="error">存在失败</Tag>}</span>, children: toolRuns.map(tool => <div key={tool.key} className={`tool-event ${tool.status === "FAILED" ? "failed" : ""}`}>
                    <Space wrap><strong>{tool.name}</strong><Tag color={tool.status === "SUCCEEDED" ? "success" : tool.status === "FAILED" ? "error" : "processing"}>{({ REQUESTED: "已请求", RUNNING: "执行中", SUCCEEDED: "已完成", FAILED: "失败", CANCELLED: "已取消", UNKNOWN: "结果未知" } as Record<string,string>)[tool.status] || tool.status}</Tag></Space>
                    {tool.result && (tool.status === "SUCCEEDED" ? <ToolResult text={tool.result} /> : <pre>{tool.result}</pre>)}
                    {tool.status === "FAILED" && <p className="tool-guidance">{(failureGuidance[tool.result] || unknownToolFailure).detail}</p>}
                  </div>) }]} />}
                </> : historyReplies(m.run_id)}
              </Fragment>)}
            </div>
            {runId && <div className="run-meta"><span className={`status-dot ${run?.status === "FAILED" ? "failed" : ""}`} /><span>{statusNames[run?.status || "PENDING"] || run?.status}</span><span>{connection}</span>{run?.mode === "mock" && <Tag>Mock 模式</Tag>}<details><summary>运行详情</summary><Typography.Text copyable>{runId}</Typography.Text><p>{run?.mode === "mock" ? "Mock 验收模式" : "真实模型"}</p>{run?.trace_url&&<a href={run.trace_url} target="_blank" rel="noopener noreferrer">查看 Agent 调用</a>}</details></div>}
            {run?.runtime_unavailable && <Alert type={run.status==='PENDING'||run.status==='QUEUED'?"info":"warning"} message={run.status==='PENDING'||run.status==='QUEUED'?"已保存提交，正在等待运行接入":"服务暂不可达，已保留提交，正在等待同步"} />}
            {run?.error_code && <FailureCard code={run.error_code} retry={()=>setInput(messages.find(m=>m.role==="user"&&m.run_id===runId)?.text||"")} connections={() => { void connectors.refetch(); setConnectionsOpen(true); }} />}
            {runId && <Phase1Activity events={events}/>}
            {clarification&&<Card size="small" className="clarification-card" title="需要你的选择" extra={<Tag color="blue">继续前确认</Tag>}><Typography.Paragraph>{clarification.question}</Typography.Paragraph><Space wrap>{clarification.options.map(option=><Button key={option.id} onClick={()=>setInput(option.value)}>{option.label}</Button>)}{clarification.allow_custom&&<Button type="text" onClick={()=>setInput(clarification.question+" ")}>自行说明</Button>}</Space><Typography.Paragraph type="secondary">选择只会填入输入框，发送后才会继续任务。</Typography.Paragraph></Card>}
            {runId && <RunPanel id={runId} onStatus={setRun} artifactsTarget={artifactsTarget} />}
          </div>
        </div>
        {messages.length===0&&welcomeTarget?createPortal(composer,welcomeTarget):composer}
      </section>
      {artifactsOpen && <button className="artifact-backdrop" aria-label="关闭产物面板" onClick={() => setArtifactsOpen(false)} />}
      <aside className="artifact-panel" hidden={!artifactsOpen} aria-label="产物与结果">
        <header><span><Icon name="library" size={16} />产物</span><Button type="text" aria-label="关闭产物面板" icon={<Icon name="close" />} onClick={() => setArtifactsOpen(false)} /></header>
        <div className="artifact-content"><span className="muted">本轮对话</span><h2>产物与结果</h2><p className="muted">查看生成的报告、数据与图表，预览或下载后继续使用。</p>
          <div ref={setArtifactsTarget} />
          {!runId && <div className="artifact-empty"><Icon name="library" size={44} /><h3>还没有产物</h3><p>对话生成的文件会保存在这里。</p></div>}
        </div>
      </aside>
    </div>
  );
}

export function Runs() {
  const [rows, setRows] = useState<Record<string, string>[]>([]),
    [id, setId] = useState(""),
    [error, setError] = useState("");
  const load = () =>
    api<{ items: Record<string, string>[] }>(
      "/admin/runs" + (id ? "/" + encodeURIComponent(id) : ""),
    )
      .then((r) => setRows(r.items))
      .catch((e) => setError(errorText(e)));
  useEffect(() => {
    void load();
  }, []);
  return (
    <Card title="运行记录（脱敏）">
      <Space>
        <Input
          aria-label="运行 ID"
          value={id}
          onChange={(e) => setId(e.target.value)}
          placeholder="按 run_id 查询"
        />
        <Button onClick={load}>查询</Button>
      </Space>
      {error && <Alert type="error" message={error} />}
      <Table
        rowKey="run_id"
        dataSource={rows}
        scroll={{ x: 800 }}
        columns={["run_id", "owner_id", "model", "created_at", "status", "mode", "error_code"].map(
          (k) => ({ title: k, dataIndex: k }),
        )}
      />
    </Card>
  );
}
