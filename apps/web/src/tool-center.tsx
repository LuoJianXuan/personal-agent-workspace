import { useState } from "react";
import { Alert, Button, Empty, Input, Modal, Space, Spin, Tag } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "./api";
import { validate } from "./contracts/validate";
import type { PersonalConnection, PlatformMcpService, PlatformMcpServiceList, SkillConfig, SkillConfigList } from "./contracts/models";
import { ConnectorLogo, connectionStatuses, installedConnection, useConnectionManager, usePersonalConnections } from "./connection-manager";
import { Icon } from "./workspace-ui";

export type ToolChatIntent = { id: string; draft: string; skillId?: string; connectorId?: string };
export function ToolCenter() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "skills" ? "skills" : "mcp";
  const [filter, setFilter] = useState<"all" | "mine">("all");
  const [search, setSearch] = useState("");
  const [help, setHelp] = useState(false);
  const [skillDetail, setSkillDetail] = useState<SkillConfig>();
  const [platformDetail, setPlatformDetail] = useState<PlatformMcpService>();
  const [busySkill, setBusySkill] = useState<string>();
  const [actionError, setActionError] = useState("");
  const nav = useNavigate();
  const cache = useQueryClient();
  const personal = usePersonalConnections();
  const skills = useQuery({ queryKey: ["catalog-skills"], queryFn: async () => validate<SkillConfigList>("SkillConfigList", await api("/catalog/skills")) });
  const platform = useQuery({ queryKey: ["catalog-mcp-services"], queryFn: async () => validate<PlatformMcpServiceList>("PlatformMcpServiceList", await api("/catalog/mcp-services")) });
  function useTool(draft: string, choice: Pick<ToolChatIntent, "skillId" | "connectorId"> = {}) {
    const intent: ToolChatIntent = { id: crypto.randomUUID(), draft, ...choice };
    nav("/app/chat", { state: { toolIntent: intent } });
  }
  function useConnection(row: PersonalConnection) { useTool(`请使用${row.name}帮我：`, { connectorId: row.connector_id }); }
  const manager = useConnectionManager(useConnection);
  const matches = (...values: (string | undefined)[]) => values.join(" ").toLowerCase().includes(search.trim().toLowerCase());
  const personalRows = (personal.data?.items ?? []).filter(row => (filter === "all" || installedConnection(row)) && matches(row.name, row.presentation?.description, row.presentation?.category));
  const platformRows = (platform.data?.items ?? []).filter(row => matches(row.name, ...row.tools.map(t => t.description)));
  const skillRows = (skills.data?.items ?? []).filter(row => (filter === "all" || row.personal_enabled) && matches(row.name, row.description, row.category));
  const displayedSkill = skills.data?.items.find(s => s.id === skillDetail?.id);
  const displayedPlatform = platform.data?.items.find(s => s.id === platformDetail?.id);
  const loading = tab === "mcp" ? personal.isPending || platform.isPending : skills.isPending;
  const count = tab === "mcp" ? personalRows.length + platformRows.length : skillRows.length;
  async function enableSkill(row: SkillConfig, enabled: boolean) {
    if (busySkill) return;
    setBusySkill(row.id); setActionError("");
    try {
      await api(`/me/skills/${row.id}/enablement`, { method: "PUT", body: JSON.stringify({ enabled }) });
      await cache.invalidateQueries({ queryKey: ["catalog-skills"] });
    } catch (e) { setActionError(e instanceof Error ? e.message : "无法更新技能，请重试"); }
    finally { setBusySkill(undefined); }
  }
  function selectTab(next: string) { setParams({ tab: next }); setFilter("all"); setSearch(""); setActionError(""); }
  function refresh() { void personal.refetch(); void platform.refetch(); void skills.refetch(); }
  const sources = tab === "mcp" ? [personal, platform] : [skills];
  return <section className="tool-center">
    <div className="tool-breadcrumb">工作空间 <span>/</span> <strong>工具</strong></div>
    <header className="tool-page-heading"><div><span className="tool-eyebrow">YOUR TOOLKIT</span><h1>让助手，更得心应手。</h1><p>找到合适的技能，连接常用服务，把想法交给助手。</p></div><Button type="text" className="tool-help-button" icon={<Icon name="help" />} onClick={() => setHelp(true)}>技能和 MCP 有什么区别？</Button></header>
    <div className="tool-tabs" role="tablist" aria-label="工具类型">{(["skills", "mcp"] as const).map(key => <button key={key} id={`tool-tab-${key}`} role="tab" aria-selected={tab === key} aria-controls="tool-catalog" className={tab === key ? "active" : ""} onClick={() => selectTab(key)}><Icon name={key === "skills" ? "skill" : "plug"} />{key === "skills" ? "技能" : "MCP"}<span>{key === "skills" ? skills.data?.items.length ?? "—" : personal.data && platform.data ? personal.data.items.length + platform.data.items.length : "—"}</span></button>)}</div>
    <section id="tool-catalog" role="tabpanel" aria-labelledby={`tool-tab-${tab}`}>
      <div className="tool-toolbar"><div className="tool-segments" aria-label="目录范围"><button aria-pressed={filter === "all"} className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>全部</button><button aria-pressed={filter === "mine"} className={filter === "mine" ? "active" : ""} onClick={() => setFilter("mine")}>{tab === "mcp" ? "已安装" : "已启用"}</button></div><div className="tool-search"><Input aria-label="搜索工具" prefix={<Icon name="search" size={16} />} placeholder={tab === "mcp" ? "搜索 MCP 服务…" : "搜索技能…"} value={search} allowClear onChange={e => setSearch(e.target.value)} /><Button type="text" onClick={refresh} loading={sources.some(q => q.isFetching)}>刷新</Button></div></div>
      <div className="tool-intro"><Icon name={tab === "mcp" ? "plug" : "skill"} /><div><strong>{tab === "mcp" ? "连接服务，让助手帮你做更多。" : "把好方法，变成助手的习惯。"}</strong> {tab === "mcp" ? "个人服务需要授权自己的账户；平台提供的服务无需填写个人 Token。" : "启用技能后，助手会按相应方法完成任务；技能不会自动授予工具权限。"}</div></div>
      {sources.map((q, i) => q.error && <Alert key={i} type="error" showIcon message={q.error instanceof Error ? q.error.message : "目录加载失败"} action={<Button onClick={() => void q.refetch()}>重试</Button>} />)}
      {actionError && <Alert type="error" showIcon message={actionError} />}
      <div className="tool-section-line"><strong>{tab === "mcp" ? filter === "mine" ? "我的 MCP" : "发现 MCP" : filter === "mine" ? "我的技能" : "发现技能"}</strong><span>{count} 项{tab === "mcp" && filter === "mine" ? " · 含平台提供" : ""}</span></div>
      {loading && <div className="tool-loading"><Spin /></div>}
      <div className="tool-grid">
        {tab === "mcp" && personalRows.map(row => <article className="tool-card" key={row.connector_id}>
          <div className="tool-card-head"><ConnectorLogo row={row} /><span className={`tool-badge ${row.status === "ready" ? "ready" : row.status === "auth_required" || row.pending ? "warn" : "personal"}`}>{row.pending ? "待确认授权" : connectionStatuses[row.status]}</span></div>
          <h3>{row.name}</h3><p>{row.presentation?.description || "连接你自己的账户，让助手使用已授权的服务能力。"}</p>
          <div className="tool-tags"><span>{row.presentation?.category || "外部服务"}</span><span>个人账户</span>{row.status === "ready" && <span>{row.tools.filter(t => t.granted).length} 项已授权</span>}</div>
          {row.status === "unconfigured" && <p className="tool-card-warning">凭据存储尚未就绪，请联系管理员。</p>}
          <footer><button className="tool-text-button" onClick={() => manager.open(row, true)}>查看详情</button><Space size={6}>
            {installedConnection(row) && <Button type="text" size="small" onClick={() => manager.open(row)}>管理</Button>}
            {row.status === "ready" && !row.pending ? <Button className="tool-use-button" onClick={() => useConnection(row)}>去使用</Button> : <Button type={row.status === "disconnected" ? "primary" : "default"} disabled={row.status === "unconfigured"} onClick={() => manager.open(row)}>{row.status === "auth_required" ? "重新授权" : row.pending ? "查看授权" : row.status === "unconfigured" ? "暂不可安装" : "+ 安装"}</Button>}
          </Space></footer>
        </article>)}
        {tab === "mcp" && platformRows.map(row => <article className="tool-card" key={row.id}><div className="tool-card-head"><span className="tool-logo tool-logo-blue"><Icon name="plug" size={23} /></span><span className="tool-badge platform">平台提供</span></div><h3>{row.name}</h3><p>{row.tools.length ? `由管理员配置，已开放 ${row.tools.length} 项工具。使用现有平台授权，无需填写个人 Token。` : row.reason}</p><div className="tool-tags"><span>平台服务</span><span>{row.availability === "configured" ? "已配置" : "暂不可用"}</span></div><footer><button className="tool-text-button" onClick={() => setPlatformDetail(row)}>查看详情</button><Button className="tool-use-button" disabled={row.availability !== "configured"} onClick={() => useTool(`请使用${row.name}帮我：`)}>去使用</Button></footer></article>)}
        {tab === "skills" && skillRows.map((row, index) => <article className="tool-card" key={row.id}><div className="tool-card-head"><span className={`tool-logo ${["tool-logo-sage", "tool-logo-blue", "tool-logo-sand"][index % 3]}`}><Icon name="skill" size={23} /></span><span className={`tool-badge ${row.personal_enabled ? "ready" : ""}`}>{row.personal_enabled ? "已启用" : "平台技能"}</span></div><h3>{row.name}</h3><p>{row.description || "按照预设的方法与输出规范，帮助你完成任务。"}</p><div className="tool-tags"><span>{row.category || "通用"}</span>{row.dependencies?.some(dep => dep.kind === "connector") && <span>需要个人服务</span>}</div><footer><button className="tool-text-button" onClick={() => setSkillDetail(row)}>查看详情</button>{row.personal_enabled ? <Button className="tool-use-button" onClick={() => useTool(`请使用「${row.name}」帮我：`, { skillId: row.id })}>去使用</Button> : <Button type="primary" disabled={!!busySkill} loading={busySkill === row.id} onClick={() => void enableSkill(row, true)}>+ 启用技能</Button>}</footer></article>)}
      </div>
      {!loading && !sources.some(q => q.error) && count === 0 && <Empty className="tool-empty" description={search ? "没有找到匹配的工具" : filter === "mine" ? "还没有安装或启用工具" : "管理员尚未发布可用内容"}><Button onClick={() => { setSearch(""); setFilter("all"); }}>浏览全部</Button></Empty>}
      <p className="tool-footnote"><Icon name="shield" size={15} />{tab === "mcp" ? "个人凭据由工作区加密保存。涉及下单、兑换等写操作，执行前仍需你的确认。" : "启用的技能作为默认偏好，每轮最多使用 3 个；“去使用”会为新对话选择该技能，不自动发送消息。"}</p>
    </section>
    {manager.dialog}
    <Modal className="tool-dialog" title={displayedSkill?.name || "技能暂不可用"} open={!!skillDetail} onCancel={() => setSkillDetail(undefined)} footer={displayedSkill ? <Space><Button disabled={!!busySkill} loading={busySkill === displayedSkill.id} onClick={() => void enableSkill(displayedSkill, !displayedSkill.personal_enabled)}>{displayedSkill.personal_enabled ? "停用技能" : "启用技能"}</Button>{displayedSkill.personal_enabled && <Button type="primary" onClick={() => useTool(`请使用「${displayedSkill.name}」帮我：`, { skillId: displayedSkill.id })}>去使用</Button>}</Space> : null}>
      {actionError && <Alert type="error" message={actionError} />}
      {displayedSkill && <><p>{displayedSkill.description}</p><div className="tool-notice">技能提供任务方法与输出规范，不会自动授权账户或工具。</div>{displayedSkill.dependencies?.length ? <div className="tool-dependencies"><h4>需要的能力</h4>{displayedSkill.dependencies.map(dep => { const connector = personal.data?.items.find(c => c.connector_id === dep.capability_id); return <div className="tool-fact-row" key={`${dep.kind}:${dep.capability_id}`}><span>{connector?.name || dep.capability_id} · {dep.required ? "必需" : "可选"}</span>{dep.kind === "connector" ? connector?.status === "ready" ? <Tag color="green">已安装</Tag> : connector ? <Button size="small" onClick={() => { setSkillDetail(undefined); manager.open(connector); }}>安装 / 授权</Button> : <span className="muted">未发布或不可用</span> : <span className="muted">发送时检查</span>}</div>; })}</div> : null}<details className="tool-details"><summary>查看技能正文</summary><pre className="safe-text">{displayedSkill.content}</pre></details></>}
    </Modal>
    <Modal className="tool-dialog" title={displayedPlatform?.name || "服务暂不可用"} open={!!platformDetail} onCancel={() => setPlatformDetail(undefined)} footer={<Button onClick={() => setPlatformDetail(undefined)}>关闭</Button>}>
      {displayedPlatform && <><div className="tool-notice">平台提供并维护凭据，无需个人 Token。配置可用不代表远端服务实时在线。</div>{displayedPlatform.reason && <Alert type="warning" message={displayedPlatform.reason} />}<h4>已开放的工具</h4>{displayedPlatform.tools.map(tool => <div className="tool-platform-detail" key={tool.name}><strong>{tool.name}</strong><Tag color={tool.requires_approval ? "orange" : "green"}>{tool.requires_approval ? "执行前确认" : "只读"}</Tag><p>{tool.description}</p></div>)}</>}
    </Modal>
    <Modal className="tool-dialog" title="技能与 MCP" open={help} onCancel={() => setHelp(false)} footer={<Button type="primary" onClick={() => setHelp(false)}>知道了</Button>}><div className="tool-notice"><strong>技能 Skill：告诉助手怎么做好一件事。</strong><br />例如按固定结构写周报、提取观点后总结文档。</div><div className="tool-notice"><strong>MCP：让助手连接外部服务。</strong><br />例如查询麦当劳活动，或使用你授权的个人账户能力。</div><p>技能可以配合 MCP 使用。安装 MCP 后，直接提问即可，无需额外启用同名技能。</p></Modal>
  </section>;
}
