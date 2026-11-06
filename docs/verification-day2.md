# Day 2 验收入口

本轮用户已明确授权“开发完毕后自行验收测试”。以下脚本仅操作独立 agent-workspace-verification 项目，Web 端口 5174，PostgreSQL 验收端口 55434；不使用开发数据库做破坏性/故障测试。

```powershell
# 在 agent-workspace 根目录；提前准备独立 .env.test
.\scripts\verify-day2.ps1 -Authorized
# 需要继续浏览器验收时保留服务
.\scripts\verify-day2.ps1 -Authorized -KeepRunning
```

脚本构建三端及 demo-mcp，应用版本迁移和幂等 seed，运行 API/MCP 集成与 Runtime 边界测试。默认结束后停止验收服务并保留卷；不会删除已有数据。可重复执行，合成资源使用随机名称。报告在 docs/evidence/day2-api-results.json。

`tests/compose/isolated-stack.yaml` 仅为隔离验收注入显式占位凭据，以验证凭据存在性和快照解析；它不是有效模型密钥。测试不向 DeepSeek 或其他模型服务发起请求。开发环境不能使用该覆盖文件。

额外已执行的代码/契约检查：
- services/backend 下：`go test ./...`。
- 根目录：`pnpm --filter web build`。
- apps/web 下：`node accept-contracts.mjs`。
- Python 消费者使用 contracts.validate 校验同十二份 schemas/examples 样例，并拒绝额外字段。

浏览器验收：模型/技能/MCP 创建与保存、技能搜索及安全正文展示、MCP 发现/授权/schema、个人技能偏好、能力检查、普通用户权限拦截、390px 导航。用户创建/禁用通过 API 验证，浏览器核对列表和管理员保护。

Day 1 的 accept-day1.py 需要全新、尚未迁移的独立数据库，不可直接对已有验收卷重跑；日常认证回归可使用 verify-day1.ps1 -Authorized。
