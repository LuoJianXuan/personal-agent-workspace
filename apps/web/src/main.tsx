import { Library, DataAnalysis } from "./delivery";
import { Chat, Runs } from "./chat";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  ConfigProvider,
  Descriptions,
  Drawer,
  Dropdown,
  Empty,
  Form,
  Input,
  Layout,
  Menu,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import type { Thread } from "./contracts/models";
import { ApiError, api, login, me, setToken } from "./api";
import { Models, Skills, Mcp, Users, Audits, AdminHome } from "./control";
import { ConversationSidebar, Icon } from "./workspace-ui";
import "./style.css";
const client = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 0, refetchOnWindowFocus: true },
  },
});
function useIdentity() {
  return useQuery({ queryKey: ["identity"], queryFn: me });
}
function Failure({ error }: { error: unknown }) {
  return (
    <Alert
      type="error"
      showIcon
      message={error instanceof Error ? error.message : "请求失败"}
      description={
        error instanceof ApiError && error.requestId
          ? `请求编号：${error.requestId}`
          : undefined
      }
    />
  );
}
function Guard({ admin = false }: { admin?: boolean }) {
  const q = useIdentity();
  if (q.isPending)
    return (
      <div className="loading">
        <Spin tip="正在确认身份" />
      </div>
    );
  if (q.error) {
    if (q.error instanceof ApiError && q.error.status === 401)
      return <Navigate to="/login" replace />;
    return (
      <main className="loading">
        <Failure error={q.error} />
        <Button onClick={() => q.refetch()}>重试</Button>
      </main>
    );
  }
  if (admin && q.data.role !== "admin")
    return (
      <main className="loading">
        <Alert type="warning" message="此页面需要管理员权限" />
        <Button href="/app">返回工作区</Button>
      </main>
    );
  return <Outlet />;
}
function Login() {
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function submit(values: { username: string; password: string }) {
    setBusy(true);
    setError(undefined);
    try {
      const result = await login(values);
      setToken(result.access_token);
      client.setQueryData(["identity"], result.user);
      nav("/app", { replace: true });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <section className="login-story">
        <span className="eyebrow">AGENT WORKSPACE / 01</span>
        <h1>
          让想法，
          <br />
          有序发生。
        </h1>
        <p>
          一个清晰的工作空间。
          <br />
          对话、工具与结果，各有归处。
        </p>
        <span className="release">序光 · 个人 Agent 工作区</span>
      </section>
      <Card className="login-card" bordered={false}>
        <Tag color="cyan">序光 · 工作空间</Tag>
        <Typography.Title level={2}>欢迎回来</Typography.Title>
        <Typography.Paragraph type="secondary">
          使用部署时配置的演示账号登录。
        </Typography.Paragraph>
        {error !== undefined && <Failure error={error} />}
        <Form layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item
            name="username"
            label="账号"
            rules={[{ required: true, message: "请输入账号" }]}
          >
            <Input autoComplete="username" size="large" maxLength={100} />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password autoComplete="current-password" size="large" />
          </Form.Item>
          <Button
            htmlType="submit"
            type="primary"
            size="large"
            block
            loading={busy}
          >
            进入工作区
          </Button>
        </Form>
        <p className="muted">账号由项目管理员配置，不提供公共默认密码。</p>
      </Card>
    </main>
  );
}
const workspaceMenu = [
  { key: "/app/chat", icon: <Icon name="chat" />, label: "对话" },
  { key: "/app/library", icon: <Icon name="library" />, label: "资料库" },
  { key: "/app/scenes/data-analysis", icon: <Icon name="chart" />, label: "数据分析" },
  { key: "/app/skills", icon: <Icon name="skill" />, label: "平台技能" },
  { key: "/app/profile", icon: <Icon name="user" />, label: "个人信息" },
];
function Shell({ admin = false }: { admin?: boolean }) {
  const q = useIdentity();
  const user = q.data!;
  const location = useLocation();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [sidebarTarget, setSidebarTarget] = useState<HTMLDivElement | null>(null);
  const [newConversationTarget, setNewConversationTarget] = useState<HTMLDivElement | null>(null);
  const isChat = !admin && location.pathname === "/app/chat";
  const [recentThreads, setRecentThreads] = useState<Thread[]>([]);
  const [recentError, setRecentError] = useState(false);
  useEffect(() => {
    if (admin || isChat) return;
    let live = true;
    setRecentError(false);
    api<{ items: Thread[] }>("/threads").then(result => { if (live) setRecentThreads(result.items); }).catch(() => { if (live) setRecentError(true); });
    return () => { live = false; };
  }, [admin, isChat, location.pathname]);
  const items = admin
    ? [
        { key: "/admin", label: "控制台概览" },
        { key: "/admin/models", label: "模型" },
        { key: "/admin/skills", label: "技能" },
        { key: "/admin/mcp", label: "MCP 连接" },
        { key: "/admin/users", label: "用户" },
        { key: "/admin/audit", label: "审计" },
        { key: "/admin/runs", label: "运行记录" },
      ]
    : workspaceMenu;
  const menu = (
    <>
      <div className="brand">
        <span className="brand-mark">序</span>序光{" "}
        <small>{admin ? "管理控制台" : "让想法有序发生"}</small>
      </div>
      {!admin && <div className="sidebar-new"><Button block icon={<Icon name="plus" />} onClick={() => { nav("/app/chat"); setOpen(false); }}>新建对话</Button></div>}
      <Menu
        selectedKeys={[location.pathname]}
        items={items}
        onClick={({ key }) => {
          nav(key);
          setOpen(false);
        }}
      />

    </>
  );
  return (
    <ConversationSidebar.Provider value={{ recent: sidebarTarget, action: newConversationTarget }}>
    <Layout className={`shell ${admin ? "admin-shell" : "workspace-shell"} ${isChat ? "chat-shell" : ""}`}>
      <Layout.Sider width={276} className="desktop-sidebar" theme="light">
        {menu}
        {!admin && <div ref={setNewConversationTarget} className="sidebar-new-slot" />}
        {!admin && <div className="sidebar-conversations"><div ref={setSidebarTarget} className="sidebar-chat-slot" />{!isChat && <section className="thread-panel" aria-label="近期对话"><div className="thread-heading"><Icon name="chat" size={15} /><span>近期对话</span><small>{recentThreads.length}</small></div><div className="sidebar-recent-list">{recentError ? <p className="muted">近期会话暂时无法加载</p> : recentThreads.map(thread => <Button type="text" block key={thread.id} title={thread.title} onClick={() => nav(`/app/chat?thread=${thread.id}`)}>{thread.title}</Button>)}</div></section>}</div>}
        <div className="sidebar-account">
          <span className="account-avatar">{user.username.slice(0, 1).toUpperCase()}</span>
          <div><strong>{user.username}</strong><small>{user.role === "admin" ? "管理员" : "个人工作空间"}</small></div>
          <Dropdown trigger={["click"]} placement="topRight" menu={{ items: [
            { key: "profile", label: "个人信息" },
            ...(user.role === "admin" ? [{ key: "console", label: admin ? "返回工作区" : "管理控制台" }] : []),
            { key: "logout", label: "退出登录", danger: true },
          ], onClick: ({ key }) => {
            if (key === "logout") { setToken(null); client.clear(); nav("/login"); }
            else nav(key === "profile" ? "/app/profile" : admin ? "/app" : "/admin");
          } }}><Button type="text" aria-label="账号菜单" icon={<Icon name="menu" size={16} />} /></Dropdown>
        </div>
      </Layout.Sider>
      <Drawer
        title="导航"
        open={open}
        onClose={() => setOpen(false)}
        placement="left"
      >
        {menu}
      </Drawer>
      <Layout>
        <Layout.Header className="header">
          <Space>
            <Button className="mobile-menu" type="text" aria-label="打开导航" icon={<Icon name="menu" />} onClick={() => setOpen(true)} />
            <span>{admin ? "系统管理" : "个人工作区"}</span>
          </Space>
          <Space>
            <Tag color={user.role === "admin" ? "cyan" : "default"}>
              {user.username}
            </Tag>
            {user.role === "admin" && (
              <Button onClick={() => nav(admin ? "/app" : "/admin")}>
                {admin ? "返回工作区" : "管理控制台"}
              </Button>
            )}
            <Button
              type="text"
              onClick={() => {
                setToken(null);
                client.clear();
                nav("/login");
              }}
            >
              退出
            </Button>
          </Space>
        </Layout.Header>
        <Layout.Content className={`content ${isChat ? "chat-content" : ""}`}>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
    </ConversationSidebar.Provider>
  );
}
function Profile() {
  const user = useIdentity().data!;
  return (
    <Card title="个人信息">
      <Descriptions
        column={1}
        items={[
          { key: "name", label: "账号", children: user.username },
          {
            key: "role",
            label: "角色",
            children: user.role === "admin" ? "管理员" : "普通用户",
          },
          { key: "id", label: "用户 ID", children: user.id },
          {
            key: "enabled",
            label: "账号状态",
            children: user.enabled ? "已启用" : "已禁用",
          },
        ]}
      />
    </Card>
  );
}
function App() {
  const nav = useNavigate();
  useEffect(() => {
    const handler = () => {
      client.clear();
      nav("/login", { replace: true });
    };
    window.addEventListener("workspace:unauthorized", handler);
    return () => window.removeEventListener("workspace:unauthorized", handler);
  }, [nav]);
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Guard />}>
        <Route path="/app" element={<Shell />}>
          <Route index element={<Navigate to="chat" replace />} />
          <Route path="chat" element={<Chat />} />
          <Route path="library" element={<Library />} />
          <Route path="scenes/data-analysis" element={<DataAnalysis />} />
          <Route path="skills" element={<Skills personal />} />
          <Route path="profile" element={<Profile />} />
        </Route>
      </Route>
      <Route element={<Guard admin />}>
        <Route path="/admin" element={<Shell admin />}>
          <Route index element={<AdminHome />} />
          <Route path="users" element={<Users />} />
          <Route path="models" element={<Models />} />
          <Route path="library" element={<Library />} />
          <Route path="scenes/data-analysis" element={<DataAnalysis />} />
          <Route path="skills" element={<Skills />} />
          <Route path="mcp" element={<Mcp />} />
          <Route path="audit" element={<Audits />} />
          <Route path="runs" element={<Runs />} />
        </Route>
      </Route>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route
        path="*"
        element={
          <Empty description="页面不存在">
            <Button href="/app">返回工作区</Button>
          </Empty>
        }
      />
    </Routes>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#2e6268",
          borderRadius: 8,
          colorText: "#252b29",
          colorTextSecondary: "#7a817e",
          colorBgLayout: "#f8f9f8",
          colorBorder: "#e4e8e5",
          fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  </React.StrictMode>,
);
