# Day 1 验证入口（部分已执行）
默认禁止自动运行测试。下列行为由用户授权后执行，结果单独记录。

1. `scripts/dev.ps1` 初始化独立 Compose 栈；四个基础服务 ready，mcp profile 未启用。数据库角色 bootstrap 只在首次空卷执行；改环境密码不会自动重置已有数据库角色。
2. `scripts/verify-day1.ps1 -Authorized`：真实 API 登录、身份读取、管理员列表、普通用户 403。不得输出 token/password。
3. 浏览器：错误密码、正确登录、刷新、退出、过期 token、普通用户直接进入 /admin、窄屏菜单和网络错误保留输入。管理员进入 /admin/users 查看真实 seed。
4. 重复 `scripts/seed.ps1`，用户数和已有密码 hash 不变；先更改本地 seed 环境密码后重复 seed，旧账号密码仍不重置。
5. 独立验证库中禁用用户，旧 token 调用 /auth/me 返回 401；再启用。D1 暂无禁用 UI（S02 实现）。
6. 分别以 workspace_backend/workspace_runtime 连接验证 PG：各自 schema 可写；访问另一 schema 应 permission denied；两角色都不是超级用户。owner 查询用 A/B thread 验证跨用户与不存在均 not found。
7. 新数据库迁移前 ready=503；迁移后 200；Runtime checkpoint setup 未完成 ready=503；断开数据库后 health 保持进程语义、ready 503。错误服务令牌 401，浏览器 JWT 不能用于内部端点。公开 Nginx /internal 返回 404。
8. 共享样例按 JSON Schema 在 Go/Python/TS 校验；增加任意顶层字段均失败。canonical fixture 在后续 JCS 实现接入后做三端已知答案验证。

隔离验证：复制 `.env.test.example` 为忽略的 `.env.test`，独立设置所有秘密，`docker compose --env-file .env.test -p agent-workspace-verification ...`。它使用不同的命名卷。不要接入灵机 AI 或其他现有数据库。脚本默认针对本项目开发栈；验证环境需显式使用对应配置。

2026-11-02：用户要求启动后，已完成 Docker 启动、认证 API 脚本、重复迁移/seed、实际跨 schema 拒绝检查；详细结果见 evidence/S01.md。其余案例仍未执行。

2026-11-03：Day 1 验收矩阵已执行，结果与边界见 evidence/DAY1-ACCEPTANCE.md。
