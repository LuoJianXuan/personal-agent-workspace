# S01：三端工程、认证、双布局与持久化

时间：D1。前置：S00。

## 目标
交付能启动的工程与登录/授权骨架；之后的页面每天接入，不等最后一天建前端。

## 实施任务
- React/TypeScript/Vite + pnpm，选一套现成组件库；实现 /login、/app、/admin 双布局、路由和公共错误组件。
- Go/Gin/GORM Backend，建立身份中间件、成熟密码哈希、带有效期 token、每请求 enabled 核对和 owner 查询方法。
- 演示管理员/用户 A/用户 B 由本项目环境配置 seed，幂等且不重置已有密码；普通用户管理 API 403。
- Python/FastAPI Runtime，集中 lifespan 创建连接；注册服务令牌认证，开放内部 health/ready。
- 一个 PG 实例分 Backend/Runtime schema 与独立角色；业务迁移由各服务负责，LangGraph checkpointer setup 独立入口。
- 建立 Compose 五服务与受控文件卷，demo-mcp 未完成时明确 profile/未就绪；不要健康检查假通过。
- 提供 Makefile 和等价 scripts/dev.ps1、migrate.ps1、seed.ps1；验证库配置独立；配置缺失有明确错误。
- 锁定可安装的前端、Go、Python、LangGraph checkpointer/MCP 兼容版本；提交真实锁文件，不伪造生成结果。

## 完成与验收条件
- 登录后普通用户进入工作区，管理员可进入后台；后端权限独立生效。
- 独立服务进程与 schema 写权限清楚；不直接共享 ORM 内部模型。
- health=进程，ready=依赖/迁移；依赖失败不标已就绪。
- 安装、迁移、启动与未执行项分别记录；默认不执行应用测试。

## 交付记录
更新 TASKS.md、docs/evidence/S01.md；列出真实文件、接口、迁移、已执行动作、未执行验证、下一任务接入点。所有代码由 AI 编写。

## 随实现讲解
解释一次登录身份如何进入 Backend；Runtime 为什么不接浏览器 token；schema 分开如何阻止跨层改表。

## 可直接下发
阅读共同规则、架构、契约和 UI_SPEC，核对前置后只完成本 S01。保持独立三端与冻结首版范围，不主动启动子代理。默认不执行测试或真实模型，准备验收入口并标明状态；已明确授权的动作按原范围继续。不要要求用户手写，不以讲解阻塞下一阶段。
