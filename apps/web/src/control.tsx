import { Icon } from "./workspace-ui";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import type {
  ModelConfig,
  ModelCatalog,
  SkillConfig,
  McpConfig,
  McpToolConfig,
  DeploymentCatalog,
  User,
  Audit,
  CapabilityPreview,
} from "./contracts/models";
import { api, ApiError } from "./api";
import { validate } from "./contracts/validate";
import schema from "./contracts/schema.json";

type Row = Record<string, unknown>;
const labels: Record<string, string> = {
  disabled: "已禁用",
  runtime_unavailable: "运行服务不可用",
  credential_missing: "缺少部署凭据",
  target_denied: "目标未获部署准入",
  ready_unverified: "配置可用 · 调用未验证",
  unverified: "未验证",
  success: "发现成功",
  failed: "发现失败",
};
export function Failure({ error }: { error: unknown }) {
  return (
    <Alert
      showIcon
      type="error"
      message={error instanceof Error ? error.message : "请求失败"}
      description={
        error instanceof ApiError && error.requestId
          ? `请求编号：${error.requestId}`
          : undefined
      }
    />
  );
}
function useList<T>(key: string, path: string, name: string) {
  return useQuery({
    queryKey: [key],
    queryFn: async () =>
      validate<{ items: T[] }>(name + "List", await api(path)),
  });
}
function writeFields(name: string, value: object): Row {
  const defs = schema.$defs as unknown as Record<string, { properties: Row }>;
  const source = value as Row;
  return Object.fromEntries(
    Object.keys(defs[name].properties).map((key) => [key, source[key]]),
  );
}
async function save<T>(
  path: string,
  method: string,
  data?: unknown,
): Promise<T> {
  return api<T>(path, {
    method,
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  });
}
function useAction() {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  return {
    busy,
    error,
    clear: () => setError(undefined),
    run: async (action: () => Promise<unknown>) => {
      setBusy(true);
      setError(undefined);
      try {
        await action();
        await client.invalidateQueries();
        return true;
      } catch (e) {
        setError(e);
        return false;
      } finally {
        setBusy(false);
      }
    },
  };
}
const title = (name: string, description: string) => (
  <div className="page-heading">
    <span className="eyebrow">CONTROL PLANE</span>
    <h1>{name}</h1>
    <p>{description}</p>
  </div>
);
const required = [{ required: true, message: "请填写此项" }];

export function Models() {
  const q = useList<ModelConfig>("models", "/admin/models", "ModelConfig");
  const deployment = useQuery({
    queryKey: ["deployment"],
    queryFn: async () =>
      validate<DeploymentCatalog>(
        "DeploymentCatalog",
        await api("/admin/deployment"),
      ),
  });
  const action = useAction();
  const [edit, setEdit] = useState<ModelConfig | null | undefined>();
  const [form] = Form.useForm();
  const endpoint = Form.useWatch("base_url", form);
  const targets = deployment.data?.models ?? [];
  function open(row?: ModelConfig) {
    action.clear();
    setEdit(row ?? null);
    form.resetFields();
    form.setFieldsValue(
      row
        ? {
            ...row,
            disable_thinking:
              row.protocol_options.thinking?.type === "disabled",
          }
        : {
            name: "",
            provider: "",
            protocol: "openai_chat_completions",
            base_url: targets[0]?.endpoint,
            credential_ref: targets[0]?.credential_ref,
            provider_model_name: "",
            context_limit: 32000,
            max_output_tokens: 4096,
            capabilities: { streaming: true, tool_calling: true },
            disable_thinking: false,
            enabled: true,
            is_default: false,
            revision: 0,
          },
    );
  }
  async function submit(values: Row) {
    const data = writeFields("ModelWrite", {
      ...values,
      provider: values.provider ?? "",
      revision: edit?.revision ?? 0,
      protocol_options: values.disable_thinking
        ? { thinking: { type: "disabled" } }
        : {},
    });
    if (
      await action.run(() =>
        save(
          "/admin/models" + (edit ? "/" + edit.id : ""),
          edit ? "PATCH" : "POST",
          data,
        ),
      )
    )
      setEdit(undefined);
  }
  return (
    <>
      {title("模型管理", "按协议配置模型。保存和配置检查不会发起模型调用。")}
      {q.error && <Failure error={q.error} />}
      <Card
        extra={
          <Space>
            <Button onClick={() => q.refetch()}>刷新</Button>
            <Button type="primary" onClick={() => open()}>
              新增模型
            </Button>
          </Space>
        }
        title="模型配置"
      >
        {action.error !== undefined && <Failure error={action.error} />}
        <Table
          rowKey="id"
          loading={q.isPending}
          dataSource={q.data?.items}
          scroll={{ x: 1000 }}
          columns={[
            {
              title: "名称",
              dataIndex: "name",
              render: (v, row) => (
                <Space>
                  {v}
                  {row.is_default && <Tag color="cyan">默认</Tag>}
                </Space>
              ),
            },
            {
              title: "协议 / 模型",
              render: (_, r) => (
                <>
                  <Tag>{r.protocol}</Tag>
                  <div>{r.provider_model_name}</div>
                </>
              ),
            },
            {
              title: "状态",
              render: (_, r) => (
                <>
                  <Tag color={r.enabled ? "green" : "default"}>
                    {r.enabled ? "已启用" : "已禁用"}
                  </Tag>
                  <div>{labels[r.availability]}</div>
                </>
              ),
            },
            {
              title: "真实验证",
              render: () => (
                <span className="muted">聊天 / 流式 / 工具：未验证</span>
              ),
            },
            { title: "版本", dataIndex: "revision" },
            {
              title: "操作",
              render: (_, r) => (
                <Space wrap>
                  <Button onClick={() => open(r)}>编辑</Button>
                  <Button
                    disabled={action.busy}
                    onClick={() =>
                      action.run(() =>
                        save(
                          "/admin/models/" + r.id,
                          "PATCH",
                          writeFields("ModelWrite", {
                            ...r,
                            enabled: !r.enabled,
                            is_default: r.enabled ? false : r.is_default,
                          }),
                        ),
                      )
                    }
                  >
                    {r.enabled ? "禁用" : "启用"}
                  </Button>
                  <Button
                    disabled={action.busy}
                    onClick={() =>
                      action.run(() =>
                        save("/admin/models/" + r.id + "/validate", "POST"),
                      )
                    }
                  >
                    配置检查
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Modal
        title={edit ? "编辑模型" : "新增模型"}
        open={edit !== undefined}
        onCancel={() => {
          if (!action.busy) setEdit(undefined);
        }}
        onOk={() => form.submit()}
        confirmLoading={action.busy}
        width={720}
        okText="保存"
        cancelText="取消"
      >
        {action.error !== undefined && <Failure error={action.error} />}{" "}
        {deployment.error && <Failure error={deployment.error} />}
        <Form form={form} layout="vertical" onFinish={submit}>
          <Button
            className="spaced"
            onClick={() =>
              form.setFieldsValue({
                name: "DeepSeek",
                provider: "deepseek",
                provider_model_name: "deepseek-flash",
                base_url: "https://api.deepseek.com",
                credential_ref: "deepseek_primary",
                protocol: "openai_chat_completions",
                disable_thinking: true,
              })
            }
          >
            填入 DeepSeek 连接预设
          </Button>
          <div className="form-grid">
            <Form.Item name="name" label="显示名称" rules={required}>
              <Input maxLength={100} />
            </Form.Item>
            <Form.Item name="provider" label="平台标签（可选）">
              <Input maxLength={100} />
            </Form.Item>
            <Form.Item name="protocol" label="协议" rules={required}>
              <Select
                options={[
                  {
                    value: "openai_chat_completions",
                    label: "OpenAI Chat Completions 兼容",
                  },
                ]}
              />
            </Form.Item>
            <Form.Item
              name="provider_model_name"
              label="供应商模型 ID"
              rules={required}
            >
              <Input maxLength={200} />
            </Form.Item>
          </div>
          <Form.Item
            name="base_url"
            label="部署允许的服务地址"
            rules={required}
          >
            <Select
              options={targets.map((t) => ({
                value: t.endpoint,
                label: t.endpoint,
              }))}
              onChange={(v) =>
                form.setFieldValue(
                  "credential_ref",
                  targets.find((t) => t.endpoint === v)?.credential_ref,
                )
              }
            />
          </Form.Item>
          <Form.Item name="credential_ref" label="凭据别名" rules={required}>
            <Select
              options={targets
                .filter((t) => t.endpoint === endpoint)
                .map((t) => ({
                  value: t.credential_ref,
                  label: `${t.credential_ref}（${t.credential_configured ? "已配置" : "未配置"}）`,
                }))}
            />
          </Form.Item>
          <div className="form-grid">
            <Form.Item name="context_limit" label="上下文上限" rules={required}>
              <InputNumber min={1} max={10000000} />
            </Form.Item>
            <Form.Item
              name="max_output_tokens"
              label="输出上限"
              rules={required}
            >
              <InputNumber min={1} max={1000000} />
            </Form.Item>
            <Form.Item
              name={["capabilities", "streaming"]}
              label="支持流式"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
            <Form.Item
              name={["capabilities", "tool_calling"]}
              label="支持工具调用"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </div>
          <Form.Item name="disable_thinking" valuePropName="checked">
            <Checkbox>
              发送 thinking.type=disabled（仅适用于支持该参数的接口）
            </Checkbox>
          </Form.Item>
          <Space>
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item
              name="is_default"
              label="设为默认"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </Space>
          <Alert
            type="info"
            message="密钥从部署环境读取；能力声明不代表已通过真实调用验证。首版仅接入非思考模式。"
          />
        </Form>
      </Modal>
    </>
  );
}

export function Skills({ personal = false }: { personal?: boolean }) {
  const q = useList<SkillConfig>(
    personal ? "catalog-skills" : "skills",
    personal ? "/catalog/skills" : "/admin/skills",
    "SkillConfig",
  );
  const action = useAction();
  const [edit, setEdit] = useState<SkillConfig | null | undefined>();
  const [detail, setDetail] = useState<SkillConfig>();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>();
  const [form] = Form.useForm();
  const items = q.data?.items ?? [];
  const visible = items.filter(
    (s) =>
      (!category || s.category === category) &&
      (s.name + " " + s.description)
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  function open(row?: SkillConfig) {
    action.clear();
    setEdit(row ?? null);
    form.resetFields();
    form.setFieldsValue(
      row ?? {
        name: "",
        description: "",
        category: "通用",
        content: "",
        enabled: true,
        revision: 0,
      },
    );
  }
  if (personal) return <section className="skills-page">
    <div className="workspace-page-heading"><div><span className="page-kicker">工作区资源</span><h1>技能</h1><span className="section-pill">平台技能</span></div></div>
    <p className="page-description">浏览可用技能，自行启用或关闭。启用的技能将作为对话的默认偏好，每轮最多使用 3 个。</p>
    <div className="skills-toolbar"><Input.Search aria-label="搜索技能" placeholder="搜索技能…" value={search} onChange={e => setSearch(e.target.value)} allowClear /><span className="muted">{visible.length} 项</span><Button onClick={() => q.refetch()} loading={q.isFetching}>刷新</Button></div>
    <div className="category-tabs" aria-label="技能分类">{[undefined, ...new Set(items.map(s => s.category))].map(c => <button key={c || "all"} className={category === c ? "selected" : ""} onClick={() => setCategory(c)}>{c || "全部分类"}</button>)}</div>
    {q.error && <Failure error={q.error} />}{action.error !== undefined && <Failure error={action.error} />}
    {q.isPending ? <Card loading /> : <div className="skill-cards">{visible.map(r => <Card key={r.id} className="skill-card"><div className="skill-card-top"><span className="file-type-icon"><Icon name="skill" size={22} /></span><Switch aria-label={`启用 ${r.name}`} size="small" checked={r.personal_enabled} disabled={action.busy} onChange={enabled => action.run(() => save(`/me/skills/${r.id}/enablement`, "PUT", { enabled }))} /></div><h3>{r.name}</h3><p>{r.description || "暂无技能说明"}</p><div className="skill-card-footer"><Tag>{r.category}</Tag><Button type="text" size="small" onClick={() => setDetail(r)}>查看正文</Button></div></Card>)}</div>}
    {!q.isPending && !q.error && visible.length === 0 && <div className="artifact-empty"><Icon name="skill" size={44} /><h3>这里还没有匹配的技能</h3><p>可用技能会显示在这里，试试切换分类或搜索词。</p></div>}
    <Modal open={!!detail} title={detail?.name} onCancel={() => setDetail(undefined)} footer={null}><pre className="safe-text">{detail?.content}</pre></Modal>
  </section>;
  return (
    <>
      {title(
        personal ? "平台技能" : "技能管理",
        personal
          ? "浏览技能内容，选择个人默认启用项。每轮最多使用 3 个技能。"
          : "维护技能正文与版本；技能内容不会授予工具权限。",
      )}
      <Card
        title="技能目录"
        extra={
          !personal && (
            <Button type="primary" onClick={() => open()}>
              新增技能
            </Button>
          )
        }
      >
        <Space wrap className="toolbar">
          <Input.Search
            placeholder="搜索名称或描述"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
          />
          <Select
            placeholder="全部分类"
            allowClear
            value={category}
            onChange={setCategory}
            style={{ minWidth: 150 }}
            options={[...new Set(items.map((s) => s.category))].map(
              (value) => ({ value, label: value }),
            )}
          />
          <Button onClick={() => q.refetch()}>刷新</Button>
        </Space>
        {q.error && <Failure error={q.error} />}{" "}
        {action.error !== undefined && <Failure error={action.error} />}
        <Table
          rowKey="id"
          loading={q.isPending}
          dataSource={visible}
          scroll={{ x: 650 }}
          columns={[
            { title: "名称", dataIndex: "name" },
            { title: "分类", dataIndex: "category" },
            { title: "描述", dataIndex: "description" },
            { title: "版本", dataIndex: "revision" },
            {
              title: personal ? "个人启用" : "平台启用",
              render: (_, r) => (
                <Switch
                  checked={personal ? r.personal_enabled : r.enabled}
                  disabled={action.busy}
                  onChange={(enabled) =>
                    action.run(() =>
                      save(
                        personal
                          ? `/me/skills/${r.id}/enablement`
                          : `/admin/skills/${r.id}`,
                        personal ? "PUT" : "PATCH",
                        personal
                          ? { enabled }
                          : writeFields("SkillWrite", { ...r, enabled }),
                      ),
                    )
                  }
                />
              ),
            },
            {
              title: "操作",
              render: (_, r) => (
                <Space>
                  <Button onClick={() => setDetail(r)}>查看正文</Button>
                  {!personal && <Button onClick={() => open(r)}>编辑</Button>}
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Modal
        open={!!detail}
        title={detail?.name}
        onCancel={() => setDetail(undefined)}
        footer={null}
      >
        <pre className="safe-text">{detail?.content}</pre>
      </Modal>
      <Modal
        title={edit ? "编辑技能" : "新增技能"}
        open={edit !== undefined}
        onCancel={() => {
          if (!action.busy) setEdit(undefined);
        }}
        confirmLoading={action.busy}
        onOk={() => form.submit()}
        okText="保存"
        cancelText="取消"
        width={700}
      >
        {action.error !== undefined && <Failure error={action.error} />}
        <Form
          form={form}
          layout="vertical"
          onFinish={async (values) => {
            if (
              await action.run(() =>
                save(
                  "/admin/skills" + (edit ? "/" + edit.id : ""),
                  edit ? "PATCH" : "POST",
                  writeFields("SkillWrite", {
                    ...values,
                    description: values.description ?? "",
                    revision: edit?.revision ?? 0,
                  }),
                ),
              )
            )
              setEdit(undefined);
          }}
        >
          <Form.Item name="name" label="名称" rules={required}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={required}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea maxLength={1000} />
          </Form.Item>
          <Form.Item name="content" label="Markdown 正文" rules={required}>
            <Input.TextArea rows={9} maxLength={30000} />
          </Form.Item>
          <Form.Item name="enabled" label="平台启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

export function Mcp() {
  const q = useList<McpConfig>("mcp", "/admin/mcp-connections", "McpConfig");
  const dep = useQuery({
    queryKey: ["deployment"],
    queryFn: async () =>
      validate<DeploymentCatalog>(
        "DeploymentCatalog",
        await api("/admin/deployment"),
      ),
  });
  const action = useAction();
  const [edit, setEdit] = useState<McpConfig | null | undefined>();
  const [tools, setTools] = useState<McpConfig>();
  const [form] = Form.useForm();
  function open(row?: McpConfig) {
    action.clear();
    setEdit(row ?? null);
    form.resetFields();
    form.setFieldsValue(
      row ?? {
        name: "",
        endpoint: dep.data?.mcp[0]?.endpoint,
        credential_ref: dep.data?.mcp[0]?.credential_ref ?? "",
        enabled: true,
        revision: 0,
      },
    );
  }
  return (
    <>
      {title(
        "MCP 连接",
        "发现工具与授权使用分开管理。此处只执行协议初始化与工具发现。",
      )}
      <Card
        title="连接配置"
        extra={
          <Space>
            <Button onClick={() => q.refetch()}>刷新</Button>
            <Button type="primary" onClick={() => open()}>
              新增连接
            </Button>
          </Space>
        }
      >
        {q.error && <Failure error={q.error} />}{" "}
        {action.error !== undefined && <Failure error={action.error} />}
        <Table
          rowKey="id"
          loading={q.isPending}
          dataSource={q.data?.items}
          scroll={{ x: 950 }}
          columns={[
            { title: "名称", dataIndex: "name" },
            { title: "地址", dataIndex: "endpoint" },
            {
              title: "配置状态",
              render: (_, r) => (
                <Tag color={r.enabled ? "green" : "default"}>
                  {r.enabled ? "已保存 · 启用" : "已保存 · 禁用"}
                </Tag>
              ),
            },
            {
              title: "协议探测",
              render: (_, r) => (
                <>
                  <Tag
                    color={
                      r.probe_status === "success"
                        ? "green"
                        : r.probe_status === "failed"
                          ? "red"
                          : "default"
                    }
                  >
                    {labels[r.probe_status]}
                  </Tag>
                  <div className="muted">
                    {r.last_probe_at
                      ? new Date(r.last_probe_at).toLocaleString()
                      : "尚未探测"}
                  </div>
                  {r.probe_error && <span>连接失败或超时，请检查部署</span>}
                </>
              ),
            },
            { title: "版本", dataIndex: "revision" },
            {
              title: "操作",
              render: (_, r) => (
                <Space wrap>
                  <Button onClick={() => open(r)}>编辑</Button>
                  <Button
                    disabled={action.busy || !r.enabled}
                    onClick={() =>
                      action.run(() =>
                        save(
                          "/admin/mcp-connections/" + r.id + "/discover",
                          "POST",
                          { revision: r.revision },
                        ),
                      )
                    }
                  >
                    发现工具
                  </Button>
                  <Button onClick={() => setTools(r)}>工具列表</Button>
                  <Button
                    disabled={action.busy}
                    onClick={() =>
                      action.run(() =>
                        save(
                          "/admin/mcp-connections/" + r.id,
                          "PATCH",
                          writeFields("McpWrite", {
                            ...r,
                            enabled: !r.enabled,
                          }),
                        ),
                      )
                    }
                  >
                    {r.enabled ? "禁用" : "启用"}
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Modal
        open={edit !== undefined}
        title={edit ? "编辑 MCP 连接" : "新增 MCP 连接"}
        onCancel={() => {
          if (!action.busy) setEdit(undefined);
        }}
        onOk={() => form.submit()}
        confirmLoading={action.busy}
        okText="保存"
        cancelText="取消"
      >
        {action.error !== undefined && <Failure error={action.error} />}{" "}
        {dep.error && <Failure error={dep.error} />}
        <Form
          layout="vertical"
          form={form}
          onFinish={async (values) => {
            if (
              await action.run(() =>
                save(
                  "/admin/mcp-connections" + (edit ? "/" + edit.id : ""),
                  edit ? "PATCH" : "POST",
                  writeFields("McpWrite", {
                    ...values,
                    revision: edit?.revision ?? 0,
                  }),
                ),
              )
            )
              setEdit(undefined);
          }}
        >
          <Form.Item name="name" label="连接名称" rules={required}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="endpoint" label="部署允许的地址" rules={required}>
            <Select
              options={dep.data?.mcp.map((v) => ({
                value: v.endpoint,
                label: v.endpoint,
              }))}
              onChange={(v) =>
                form.setFieldValue(
                  "credential_ref",
                  dep.data?.mcp.find((t) => t.endpoint === v)?.credential_ref ??
                    "",
                )
              }
            />
          </Form.Item>
          <Form.Item name="credential_ref" label="部署凭据别名">
            <Input readOnly placeholder="此连接不需要凭据" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Alert
            showIcon
            type="warning"
            message="修改连接会撤回已发现工具的启用状态，需要重新发现并授权。"
          />
        </Form>
      </Modal>
      <Modal
        open={!!tools}
        title={`${tools?.name ?? ""} · 工具`}
        onCancel={() => setTools(undefined)}
        footer={null}
        width={950}
      >
        {tools && <ToolList connection={tools} />}
      </Modal>
    </>
  );
}
function ToolList({ connection }: { connection: McpConfig }) {
  const q = useList<McpToolConfig>(
    "tools-" + connection.id,
    `/admin/mcp-connections/${connection.id}/tools`,
    "McpToolConfig",
  );
  const action = useAction();
  return (
    <>
      {q.error && <Failure error={q.error} />}{" "}
      {action.error !== undefined && <Failure error={action.error} />}
      <Alert
        type="info"
        message="发现的工具默认禁用。只有部署清单确认的只读工具可以启用。"
      />
      <Table
        rowKey="namespaced_tool_id"
        dataSource={q.data?.items}
        loading={q.isPending}
        scroll={{ x: 650 }}
        expandable={{
          expandedRowRender: (r) => (
            <>
              <Typography.Text copyable>{r.namespaced_tool_id}</Typography.Text>
              <pre className="safe-text">
                {JSON.stringify(r.input_schema, null, 2)}
              </pre>
            </>
          ),
        }}
        columns={[
          { title: "远端工具名", dataIndex: "remote_name" },
          {
            title: "部署准入",
            render: (_, r) => (
              <Tag color={r.trusted_read_only ? "green" : "red"}>
                {r.trusted_read_only ? "只读许可" : "未许可"}
              </Tag>
            ),
          },
          {
            title: "发现状态",
            render: (_, r) => (r.available ? "存在" : "已移除"),
          },
          { title: "版本", dataIndex: "revision" },
          {
            title: "启用",
            render: (_, r) => (
              <Switch
                checked={r.enabled}
                disabled={
                  action.busy ||
                  (!r.enabled && (!r.available || !r.trusted_read_only))
                }
                onChange={(enabled) =>
                  action.run(() =>
                    save(
                      `/admin/mcp-connections/${connection.id}/tools/${r.namespaced_tool_id}`,
                      "PATCH",
                      { enabled, revision: r.revision },
                    ),
                  )
                }
              />
            ),
          },
        ]}
      />
    </>
  );
}

export function Users() {
  const q = useList<User>("users", "/admin/users", "User");
  const action = useAction();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  return (
    <>
      {title("用户管理", "创建普通账号，管理账号启用状态。管理员账号受保护。")}
      <Card
        title="用户"
        extra={
          <Button
            type="primary"
            onClick={() => {
              action.clear();
              form.resetFields();
              setOpen(true);
            }}
          >
            新增用户
          </Button>
        }
      >
        {q.error && <Failure error={q.error} />}{" "}
        {action.error !== undefined && <Failure error={action.error} />}
        <Table
          rowKey="id"
          loading={q.isPending}
          dataSource={q.data?.items}
          columns={[
            { title: "账号", dataIndex: "username" },
            {
              title: "角色",
              render: (_, r) => (r.role === "admin" ? "管理员" : "普通用户"),
            },
            { title: "版本", dataIndex: "revision" },
            {
              title: "启用",
              render: (_, r) => (
                <Switch
                  checked={r.enabled}
                  disabled={r.role === "admin" || action.busy}
                  onChange={(enabled) =>
                    action.run(() =>
                      save("/admin/users/" + r.id, "PATCH", {
                        enabled,
                        revision: r.revision,
                      }),
                    )
                  }
                />
              ),
            },
          ]}
        />
      </Card>
      <Modal
        title="新增普通用户"
        open={open}
        onCancel={() => {
          if (!action.busy) setOpen(false);
        }}
        onOk={() => form.submit()}
        confirmLoading={action.busy}
        okText="创建"
        cancelText="取消"
      >
        {action.error !== undefined && <Failure error={action.error} />}
        <Form
          form={form}
          layout="vertical"
          onFinish={async (values) => {
            if (await action.run(() => save("/admin/users", "POST", values)))
              setOpen(false);
          }}
        >
          <Form.Item
            name="username"
            label="账号"
            rules={[
              {
                required: true,
                pattern: /^[A-Za-z0-9_.-]{3,100}$/,
                message: "3–100 位字母、数字、点、短横线或下划线",
              },
            ]}
          >
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="password"
            label="初始密码"
            rules={[
              {
                required: true,
                min: 12,
                max: 72,
                message: "密码长度为 12–72 字符，且最多 72 字节",
              },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Alert
            type="info"
            message="账号创建后不会回显密码，请通过适当方式交给使用者。"
          />
        </Form>
      </Modal>
    </>
  );
}
export function Audits() {
  const [filter, setFilter] = useState("");
  const q = useList<Audit>(
    "audits-" + filter,
    "/admin/audits" +
      (filter ? "?object_id=" + encodeURIComponent(filter) : ""),
    "Audit",
  );
  return (
    <>
      {title("管理审计", "记录配置和权限操作；不包含密钥、密码或技能正文。")}
      <Card>
        <Space className="toolbar">
          <Input.Search
            placeholder="按对象 ID 查询"
            onSearch={setFilter}
            allowClear
          />
          <Button onClick={() => q.refetch()}>刷新</Button>
        </Space>
        {q.error && <Failure error={q.error} />}
        <Table
          rowKey="id"
          dataSource={q.data?.items}
          loading={q.isPending}
          scroll={{ x: 1100 }}
          columns={[
            {
              title: "时间",
              dataIndex: "created_at",
              render: (v) => new Date(v).toLocaleString(),
            },
            { title: "操作", dataIndex: "action" },
            { title: "对象", dataIndex: "object_id" },
            { title: "操作者", dataIndex: "actor_id" },
            {
              title: "变更摘要",
              dataIndex: "safe_changes",
              render: (v) => JSON.stringify(v),
            },
          ]}
        />
      </Card>
    </>
  );
}
export function CapabilityCatalog() {
  const models = useList<ModelCatalog>(
    "catalog-models",
    "/catalog/models",
    "ModelCatalog",
  );
  const skills = useList<SkillConfig>(
    "catalog-skills",
    "/catalog/skills",
    "SkillConfig",
  );
  const tools = useList<McpToolConfig>(
    "catalog-tools",
    "/catalog/tools",
    "McpToolConfig",
  );
  const action = useAction();
  const [model, setModel] = useState<string>();
  const [selected, setSelected] = useState<string[] | undefined>();
  const [preview, setPreview] = useState<CapabilityPreview>();
  return (
    <>
      <div className="page-heading">
        <span className="eyebrow">YOUR WORKSPACE</span>
        <h1>工作台</h1>
        <p>查看管理员开放的模型、技能与只读工具。</p>
      </div>
      <div className="workspace-grid">
        <Card title="本轮能力选择">
          <Space direction="vertical" style={{ width: "100%" }}>
            {models.error && <Failure error={models.error} />}
            <Select
              aria-label="选择模型"
              style={{ width: "100%" }}
              placeholder="使用默认模型"
              allowClear
              value={model}
              onChange={(v) => {
                setModel(v);
                setPreview(undefined);
              }}
              options={models.data?.items.map((m) => ({
                value: m.id,
                label: `${m.name}${m.is_default ? " · 默认" : ""} · ${labels[m.availability]}`,
              }))}
            />
            {skills.error && <Failure error={skills.error} />}
            <Select
              aria-label="选择技能"
              mode="multiple"
              style={{ width: "100%" }}
              placeholder="未显式选择时使用个人启用技能，最多 3 个"
              value={selected}
              onChange={(v) => {
                setSelected(v);
                setPreview(undefined);
              }}
              options={skills.data?.items.map((s) => ({
                value: s.id,
                label: s.name,
              }))}
            />
            <Button
              loading={action.busy}
              onClick={() =>
                action.run(async () => {
                  setPreview(undefined);
                  const value = await save("/capabilities/resolve", "POST", {
                    ...(model ? { model_id: model } : {}),
                    ...(selected === undefined ? {} : { skill_ids: selected }),
                    require_tools: false,
                    require_streaming: true,
                  });
                  setPreview(
                    validate<CapabilityPreview>("CapabilityPreview", value),
                  );
                })
              }
            >
              检查本轮配置
            </Button>
            {action.error !== undefined && <Failure error={action.error} />}{" "}
            {preview && (
              <Alert
                type="success"
                message="本轮配置检查通过（未调用模型）"
                description={`技能 ${preview.skill_ids.length} 个 · 工具 ${preview.tool_ids.length} 个`}
              />
            )}
            <Alert
              type="info"
              message="对话发送将在 Day 3 接入"
              description="当前配置检查不会调用模型，也不会执行业务工具。"
            />
          </Space>
        </Card>
        <Card title="已授权只读工具">
          {tools.error ? (
            <Failure error={tools.error} />
          ) : tools.data?.items.length ? (
            <Space direction="vertical">
              {tools.data.items.map((t) => (
                <div key={t.namespaced_tool_id}>
                  <Tag color="cyan">{t.remote_name}</Tag>
                  <p>{t.description}</p>
                </div>
              ))}
            </Space>
          ) : (
            <Empty description="暂无已授权工具" />
          )}
          <Button href="/app/skills">管理个人技能</Button>
        </Card>
      </div>
    </>
  );
}
export function AdminHome() {
  return (
    <>
      {title("管理控制台", "配置模型、技能与 MCP，管理用户和审计记录。")}
      <div className="admin-grid">
        {[
          ["models", "模型", "配置协议、连接、能力与默认项"],
          ["skills", "技能", "维护技能正文、版本和启停"],
          ["mcp", "MCP", "发现远端工具并逐项授权"],
          ["users", "用户", "创建普通账号、启用或禁用"],
          ["audit", "审计", "查看配置与权限变更记录"],
        ].map(([path, name, desc]) => (
          <Card key={path} title={name}>
            <p>{desc}</p>
            <Button href={"/admin/" + path}>进入{name}</Button>
          </Card>
        ))}
      </div>
    </>
  );
}
