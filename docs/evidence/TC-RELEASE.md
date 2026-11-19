# 工具栏目与 MCP 安装体验

实现状态：代码齐备，已部署本地 5173。验证状态：2026-11-16 用户授权后的浏览器核心业务、真实 DeepSeek/MCP 与回归通过。发现的问题及修复见 [验收报告](TC-VERIFY.md)。以下构建记录保留实施阶段历史。

## 改动

- 按用户确认的 HTML 原型实现 `/app/tools`，Skill/MCP 目录、搜索、筛选、真实状态、详情与去使用。原型的虚构服务与演示状态没有进入正式实现。
- 共用 connection-manager 接入原 probe/grant/discard/revoke：填写 Token → 发现 → 明确确认 → 已安装；管理、换 Token、检查更新、卸载；原地对话安装保留草稿。
- 管理端编辑个人 MCP 展示信息，默认数据来自部署准入定义。保持地址与风险策略的部署边界。
- 旧 `/app/skills`、`/app/capabilities` 跳转工具栏目；模型和环境状态在 `/app/settings`，高级能力组合检查折叠。

## 契约和部署

先修改 schemas/openapi.yaml 和 JSON Schema，再使用 generate-contracts.py 生成 Go/TS/Python 副本。增加 ConnectorPresentation、PlatformMcpServiceList 及安全摘要；Backend schema 10 添加展示 JSONB 列。不修改个人 Token、授权或工具指纹，不新增服务。

## 成功与失败边界

安装必须得到 grant 成功响应才显示成功。错误 Token、发现超时、清单过期或 revision 冲突显示明确失败；授权更新取消调用 discard；卸载确认调用原撤销接口。安装不会发送模型请求。平台服务使用已有权限，无需个人 Token。读/写裁决仍在既有工具边界。

## 已执行

- 阅读并静态核对现有目录、个人授权、审批和运行入口。
- JSON Schema 及 SDK 生成；Go 格式化；静态差异检查。
- 本地依赖最初缺少已锁定的 remark-gfm；按锁文件补齐，未升级依赖。
- `docker compose build backend web` 完成：Go 编译、TypeScript 编译、Vite 打包通过。前端保留现有大 bundle 警告，本轮未引入新的依赖。
- `docker compose run --rm --no-deps backend migrate` 退出 0，执行 schema 10 展示字段增量迁移。
- `docker compose up -d --no-deps --no-build --wait backend web` 退出 0，Backend/Web 就绪；未重建 Runtime、数据库或 MCP 服务。
- `/app/tools?tab=mcp` 返回 HTTP 200，提供新构建资源 `index-Bvtbw9SQ.js` / `index-CLmALYBn.css`。这只是部署静态资源核对，不是登录或业务链路验收。

## 使用入口

- 用户：`http://localhost:5173/app/tools?tab=mcp` / `?tab=skills`。
- 管理员：`/admin/mcp` → 个人 MCP 目录 → 编辑展示信息或发布开关。
- 设置：`/app/settings`。旧路由继续兼容。
- 原型页面保持独立，正式目录不使用原型里的示例服务。

## 未执行与下一步

后续授权验收已完成，详见 [验收报告](TC-VERIFY.md) 与 [任务清单](../../openspec/changes/tool-directory-and-installation/tasks.md)。真实写操作、付费公网搜索和独立计算/对象存储专项未新增执行，不纳入本轮通过范围。
