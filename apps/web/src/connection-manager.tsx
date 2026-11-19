import { useState } from "react";
import { Alert, Button, Empty, Input, Modal, Radio, Space, Spin, Steps, Tag } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { PersonalConnection, PersonalConnectionList } from "./contracts/models";
import { validate } from "./contracts/validate";
import { Icon } from "./workspace-ui";

export const connectionStatuses: Record<PersonalConnection["status"], string> = {
  unconfigured: "部署未就绪", disconnected: "个人授权", pending: "待确认授权", ready: "已安装", auth_required: "授权失效",
};
const policyLabels = { read: "可直接查询", confirm: "执行前确认", unknown: "风险待核实 · 每次确认", blocked: "暂不开放" };
export const installedConnection = (row: PersonalConnection) => row.status === "ready" || row.status === "auth_required";
export function ConnectorLogo({ row }: { row: PersonalConnection }) {
  const icon = row.presentation?.icon;
  return <span className={`tool-logo ${icon === "mcd" ? "tool-logo-mcd" : "tool-logo-sage"}`}>
    {icon === "mcd" ? "m" : <Icon name={icon === "library" ? "library" : icon === "search" ? "search" : icon === "map" ? "map" : "plug"} size={23} />}
  </span>;
}
export function usePersonalConnections() {
  return useQuery({ queryKey: ["personal-connections"], queryFn: async () => validate<PersonalConnectionList>("PersonalConnectionList", await api("/catalog/connectors")) });
}
type Screen = "detail" | "token" | "grant" | "manage" | "success" | "remove";
export function useConnectionManager(onUse?: (row: PersonalConnection) => void) {
  const catalog = usePersonalConnections();
  const cache = useQueryClient();
  const [activeId, setActiveId] = useState<string>();
  const [screen, setScreen] = useState<Screen>("detail");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"full" | "query">("full");
  const current = catalog.data?.items.find(row => row.connector_id === activeId);
  function open(row: PersonalConnection, detail = false) {
    setActiveId(row.connector_id); setToken(""); setError(""); setMode("full");
    setScreen(detail ? "detail" : installedConnection(row) ? "manage" : row.pending ? "grant" : "token");
  }
  async function change(row: PersonalConnection, path: string, method: string, fields: object = {}) {
    if (busy) return;
    setBusy(true); setAction(path || method); setError(""); setToken("");
    try {
      const result = validate<PersonalConnection>("PersonalConnection", await api("/me/connections/" + encodeURIComponent(row.connector_id) + path,
        { method, body: JSON.stringify({ revision: row.revision, ...fields }) }));
      cache.setQueryData<PersonalConnectionList>(["personal-connections"], previous => ({ items: (previous?.items ?? []).map(item => item.connector_id === row.connector_id ? result : item) }));
      void cache.invalidateQueries({ queryKey: ["catalog-tools"] });
      void cache.invalidateQueries({ queryKey: ["catalog-skills"] });
      return result;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "连接操作失败，请重试");
      await catalog.refetch();
      return undefined;
    } finally { setBusy(false); setAction(""); }
  }
  async function close() {
    if (busy) return;
    if (current?.pending && screen !== "detail" && screen !== "manage" && !await change(current, "/discard", "POST")) return;
    setActiveId(undefined); setToken(""); setError("");
  }
  async function discover() {
    if (!current) return;
    if (await change(current, "/probe", "POST", screen === "token" ? { token: token.trim() } : {})) setScreen("grant");
  }
  function use() {
    if (!current || current.status !== "ready") return;
    setActiveId(undefined); setToken(""); onUse?.(current);
  }
  const counts = current?.tools.reduce((result, tool) => ({ ...result, [tool.policy]: (result[tool.policy] ?? 0) + 1 }), {} as Partial<Record<keyof typeof policyLabels, number>>) ?? {};
  const helpUrl = current?.presentation?.token_help_url;
  const safeHelp = helpUrl && /^https:\/\//i.test(helpUrl) ? helpUrl : undefined;
  const title = { detail: current?.name, token: current && installedConnection(current) ? "更新账户授权" : "安装 MCP", grant: "确认授权范围", manage: "管理连接", success: "已安装，可以使用了", remove: "卸载这个 MCP？" }[screen];
  const dialog = <Modal open={!!activeId} title={null} footer={null} className="tool-dialog" width={560}
    closable={!busy} keyboard={!busy} maskClosable={!busy} onCancel={() => void close()}>
    {!current ? <Alert type="warning" showIcon message="此 MCP 暂时无法读取或已下架" description="已有对话会保留。请刷新目录，或联系管理员确认发布状态。" action={<Button onClick={() => void catalog.refetch()}>刷新</Button>} /> : <>
      <header className="tool-dialog-heading"><ConnectorLogo row={current} /><div><h2>{title}</h2><p>{current.name} · 个人账户</p></div></header>
      {error && <Alert type="error" showIcon message={error} description="未成功的操作不会显示为已完成。可刷新状态后重试；已有对话会保留。" />}
      {(["token", "grant", "success"] as Screen[]).includes(screen) && <Steps size="small" current={screen === "token" ? 0 : screen === "grant" ? 1 : 2} items={[{ title: "填写 Token" }, { title: "确认授权" }, { title: "安装完成" }]} />}
      {screen === "detail" && <>
        <p className="tool-dialog-description">{current.presentation?.description || "通过个人账户授权，让助手使用这个外部服务。"}</p>
        <dl className="tool-facts"><div><dt>服务分类</dt><dd>{current.presentation?.category || "外部服务"}</dd></div><div><dt>连接方式</dt><dd>个人 MCP Token</dd></div><div><dt>管理员负责</dt><dd>预置服务、安全策略与发布</dd></div><div><dt>由你决定</dt><dd>自己的账户与授权范围</dd></div></dl>
        <div className="tool-notice">一次授权当前兼容工具。涉及写入的操作仍需执行前确认；新工具或权限变化需要重新授权。</div>
        <div className="tool-dialog-footer"><Button onClick={() => void close()}>返回</Button><Button type="primary" disabled={current.status === "unconfigured"} onClick={() => open(current)}>{installedConnection(current) ? "管理连接" : current.pending ? "继续授权" : "安装"}</Button></div>
      </>}
      {screen === "token" && <>
        <p className="tool-dialog-description">连接你自己的账户，助手只使用你确认授权的能力。</p>
        <div className="tool-field-label"><label htmlFor="personal-mcp-token">你的 MCP Token</label>{safeHelp && <a href={safeHelp} target="_blank" rel="noopener noreferrer">前往官方获取 ↗</a>}</div>
        <Input.Password id="personal-mcp-token" aria-label="MCP Token" value={token} autoComplete="off" maxLength={2048} disabled={busy} placeholder="粘贴你的个人 Token" onChange={event => setToken(event.target.value)} />
        <div className="tool-notice"><Icon name="shield" size={17} /><span>Token 由工作区加密保存，仅用于连接 {current.name}。验证只进行初始化与工具发现，不执行查询、领券或下单。</span></div>
        <div className="tool-dialog-footer"><Button disabled={busy} onClick={() => void close()}>取消</Button><Button type="primary" loading={busy} disabled={token.trim().length < 12 || current.status === "unconfigured"} onClick={() => void discover()}>验证并继续</Button></div>
      </>}
      {screen === "grant" && <>
        {!current.pending ? <Alert type="warning" message="待确认清单已失效" description="可能已在其他页面确认或取消。请重新验证连接或检查工具更新。" action={<Button onClick={() => setScreen(installedConnection(current) ? "manage" : "token")}>返回连接</Button>} /> : <>
          <p className="tool-dialog-description">已发现 {current.tools.length} 项能力。查询可能涉及你的个人信息，请确认授权范围。</p>
          <Space wrap><Tag color="green">{counts.read ?? 0} 项查询</Tag><Tag color="orange">{(counts.confirm ?? 0) + (counts.unknown ?? 0)} 项执行前确认</Tag><Tag>{counts.blocked ?? 0} 项暂不开放</Tag></Space>
          <Radio.Group value={mode} disabled={busy} onChange={event => setMode(event.target.value)} className="tool-permissions">
            <Radio value="full"><strong>授权当前兼容能力</strong><small>查询直接使用；写操作和风险未核实的操作每次执行前确认。</small></Radio>
            <Radio value="query"><strong>仅授权查询</strong><small>仅允许查询信息，不授权更改账户、创建订单等操作。</small></Radio>
          </Radio.Group>
          <details className="tool-details"><summary>查看工具明细</summary>{current.tools.map(tool => <div className="tool-fact-row" key={tool.name}><span>{tool.name}</span><small>{tool.reason === "UNSUPPORTED_SCHEMA" ? "参数格式暂不支持" : policyLabels[tool.policy]}</small></div>)}</details>
          <p className="tool-help">新增工具和权限变化不会自动扩大授权。暂不开放的工具将保留明确原因。</p>
          <div className="tool-dialog-footer"><Button disabled={busy} loading={action === "/discard"} onClick={() => void close()}>取消授权</Button><Button type="primary" disabled={busy} loading={action === "/grant"} onClick={async () => { if (await change(current, "/grant", "PUT", { mode, catalog_hash: current.catalog_hash })) setScreen("success"); }}>确认授权</Button></div>
        </>}
      </>}
      {screen === "manage" && <>
        <div className="tool-status-box"><span>{current.status === "ready" ? "已安装，当前授权有效" : connectionStatuses[current.status]}</span><Tag color={current.status === "ready" ? "green" : "orange"}>{current.tools.filter(t => t.granted).length} 项已授权</Tag></div>
        {current.status === "auth_required" && <Alert type="warning" message="服务拒绝了当前 Token，请重新授权" />}
        {current.pending && <Alert type="info" message="有待确认的工具清单" action={<Button disabled={busy} onClick={() => setScreen("grant")}>查看并确认</Button>} />}
        <div className="tool-manage-actions"><Button disabled={busy} onClick={() => { setError(""); setScreen("token"); }}>更换 Token / 重新授权</Button><Button loading={busy} disabled={current.status !== "ready"} onClick={() => void discover()}>检查工具与更新授权</Button></div>
        <details className="tool-details"><summary>查看当前工具授权</summary>{current.tools.map(tool => <div className="tool-fact-row" key={tool.name}><span>{tool.name}</span><small>{tool.granted ? policyLabels[tool.policy] : "未授权"}</small></div>)}</details>
        <p className="tool-help">连接状态代表配置与授权情况，不保证远端服务一直在线。遇到超时可稍后重试；写操作重试前请核对外部结果。</p>
        <div className="tool-dialog-footer"><Button danger disabled={busy} onClick={() => { setError(""); setScreen("remove"); }}>卸载 MCP</Button>{onUse && current.status === "ready" ? <Button type="primary" disabled={busy} onClick={use}>去对话</Button> : <Button disabled={busy} onClick={() => void close()}>完成</Button>}</div>
      </>}
      {screen === "success" && <><div className="tool-success"><span><Icon name="check" size={30} /></span><h3>账户已连接</h3><p>授权已保存，可用工具将进入后续对话。随时可以管理或撤销授权。</p></div><div className="tool-dialog-footer"><Button onClick={() => void close()}>完成</Button>{onUse && <Button type="primary" onClick={use}>去对话</Button>}</div></>}
      {screen === "remove" && <><p>将移除工作区保存的 Token 和授权，阻止后续使用此个人连接。已有对话记录保留，以后可以重新安装。</p><div className="tool-notice">这不会撤销服务方 Token，也无法撤回已经发出的操作。要撤销服务方 Token，请前往其官方控制台。</div><div className="tool-dialog-footer"><Button disabled={busy} onClick={() => setScreen("manage")}>保留连接</Button><Button danger loading={busy} onClick={async () => { if (await change(current, "", "DELETE")) { setActiveId(undefined); setToken(""); } }}>确认卸载</Button></div></>}
    </>}
  </Modal>;
  return { open, dialog };
}

// Chat keeps its draft mounted while using the same installation and authorization flow.
export function PersonalConnections() {
  const catalog = usePersonalConnections();
  const manager = useConnectionManager();
  return <section className="personal-connections-compact"><h3>安装与授权</h3><p className="tool-help">配置个人 MCP 后即可在对话中使用。安装不会自动发送消息。</p>
    {catalog.isPending && <Spin />}
    {catalog.error && <Alert type="error" message="暂时无法读取 MCP" action={<Button onClick={() => void catalog.refetch()}>重试</Button>} />}
    {!catalog.isPending && !catalog.error && !catalog.data?.items.length && <Empty description="暂无已发布的个人 MCP" />}
    {catalog.data?.items.map(row => <div className="connection-compact-row" key={row.connector_id}><ConnectorLogo row={row} /><div><strong>{row.name}</strong><small>{connectionStatuses[row.status]}{row.pending ? " · 待确认更新" : ""}</small></div><Button size="small" disabled={row.status === "unconfigured"} onClick={() => manager.open(row)}>{installedConnection(row) ? "管理" : row.pending ? "继续授权" : "安装"}</Button></div>)}
    {manager.dialog}
  </section>;
}
