# Day 1 完整验收报告

日期：2026-11-03。范围：S00/S01；结论：本次验收矩阵通过，发现的问题已修复并复验。不是整个 D1–D7 产品验收，也不代表穷尽所有浏览器或负载场景。

## 环境
独立 Compose project `agent-workspace-verification`，独立 PG/文件卷，Web localhost:5174，Go 归属集成测试临时使用 localhost:55434。开发环境 localhost:5173 和 Langfuse 数据未参与故障注入。验收账号禁用已恢复；归属测试事务已回滚。结束时停止验收容器、保留数据卷；开发环境运行最终修复版。

## 实际执行矩阵
| 项目 | 结果与证据 |
|---|---|
| 首次迁移前 health/ready | Backend 与 Runtime health=200、ready=503 |
| checkpoint 未初始化 | 仅业务版本表存在时 Runtime ready=503；setup 后 ready=200 |
| 三角色登录 | admin/user-a/user-b 实际登录、me 成功 |
| 认证失败 | 无 token、坏 token、错误密码 401；普通用户 admin/users 403 |
| 身份注入 | login 增加 user_id 返回 400 |
| 账号禁用 | 禁用 user-a 后既有 JWT 401；恢复后相同 JWT 200；浏览器刷新自动回到登录 |
| JWT 到期 | 用验证环境签名密钥生成已过期合法签名 token，me 返回 401 |
| seed 幂等 | 改变 seed 密码重跑，用户 ID/password hash 指纹不变，原密码仍能登录 |
| 迁移幂等 | Backend migrate 与 Runtime setup 重跑成功 |
| schema 隔离 | 两角色非超级用户/无 createdb/createrole；自身 schema 可写，跨 schema 实际查询拒绝 |
| owner 查询 | Go 集成测试：owner 可读；另一用户、另一租户、另一项目及不存在 ID 均 ErrRecordNotFound；事务回滚 |
| 内部边界 | 无服务令牌及错误方向令牌拒绝；公开 Nginx /internal 404 |
| 数据库故障 | stop 验收 PG：两服务 health=200、ready=503；恢复 PG 后 ready=200 且登录成功 |
| 桌面浏览器 | 错误密码提示、登录、刷新保持身份、普通用户直接 /admin 被阻挡、管理员查看真实三用户列表、退出 |
| 移动布局 | 390×844：工作区排版、可见抽屉菜单、菜单跳转个人信息、个人信息可读、退出；管理表格可横向滚动 |
| 断连恢复 | stop 验收 Backend：保留表单输入、显示友好错误；恢复后不重填即可登录 |
| 三语言契约 | Go jsonschema、Python jsonschema、TS 消费的 AJV：各 8 个共享样例成功、8 个未知字段拒绝 |
| 编译与最终交付 | 修复版 TypeScript/Vite 容器构建成功；开发环境再次运行 verify-day1.ps1；入口 no-cache header 核验 |

## 发现并修复
1. Backend 断连时 Nginx HTML 错误页被直接解析成 JSON，UI 暴露 Unexpected token。api.ts 增加响应类型检查与 JSON/超时/网络错误映射。实际停止服务复验显示“服务暂不可用，请稍后重试”，输入不丢失，恢复后重试成功。
2. 浏览器复用旧入口页，加载旧 hash JS。Nginx 对入口加 Cache-Control: no-cache，使入口重新校验；并将上游连接超时限制为 3 秒。最后用 HTTP 检查最终部署头。

浏览器截图：day1-network-error.png、day1-browser-pass.png。接口阶段日志：day1-api-results.json。构建仍有约 1.24 MB JS 包体积提示，属于后续优化项，不影响本轮功能验收。

## 可复用入口与边界
- scripts/accept-day1.py：只针对固定 verification 环境，包含首次迁移检查，要求尚未执行业务迁移的专用空库；不要直接在已有验收卷上重复完整脚本，也不要自动删卷。重做全链路前应显式准备新的隔离环境。
- scripts/verify-day1.ps1 -Authorized：开发环境轻量 API 验收。
- services/backend/internal/contracts/acceptance_test.go、internal/workspace/acceptance_test.go：后者必须显式提供隔离 ACCEPTANCE_DATABASE_URL，否则跳过。
- apps/web/accept-contracts.mjs：共享契约 AJV 样例校验。

S00 的 Run/SSE/审批/文件/图表属于后续实现，这次仅验证其已冻结契约。JCS 规范化算法、真实模型/MCP、聊天流式、审批与文件场景不属于 Day 1 可执行功能，留到对应 Day 验收。本次没有模型调用，不包含压力测试或跨浏览器兼容性承诺。
