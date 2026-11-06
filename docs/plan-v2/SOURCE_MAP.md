# 灵机 AI 阅读地图

用途：定向参考，禁止把读完源码作为 5–7 天开发前置。每模块最多追踪一条相关请求，再回到个人实现。以下路径基于当前 C:/MyWorkSpace/lingji-ai；不代表可无条件复制内部代码。

| 学习点 | 当前仓库入口 | V2 提取内容 |
| --- | --- | --- |
| 控制面能力目录 | services/backend/internal/modules/assets/application/mcp_service.go | 配置与发现、启用状态的区别 |
| 用户启停/授权 | services/backend/internal/modules/assets/application/user_asset_enablement_service.go | 平台发布和个人启用两层 |
| 请求装配 | services/business-gateway/internal/runtime/assembly.go | 快照装配；不照搬固定配额值 |
| 模型装配 | services/runtime/src/deepagent/model/resolver.py | 请求级模型选择与 adapter |
| Agent 装配 | services/runtime/src/deepagent/assembly/factory.py | 模型/工具/checkpointer 注入，跳过完整 harness |
| 图存储 | services/runtime/src/api/deps.py | AsyncPostgresSaver 装配与生命周期 |
| 业务恢复边界 | services/runtime/src/services/orchestration/checkpoint_service.py | checkpoint 引用与工具 ID，区别于图状态 |
| 审批恢复 | services/runtime/src/services/orchestration/run_resume_service/approval.py | 校验绑定、恢复、事件关系 |
| 工具唯一入口 | services/tool_gateway/src/domain/execution/service.py | admission、执行、记录与审批 |
| 重试与结果未知 | services/tool_gateway/src/domain/execution/retries.py | 请求一致性与有限重试 |
| 事件脱敏 | services/runtime/src/services/orchestration/event_appender.py | canonical 写入前集中脱敏 |
| 前端工程 | apps/web-console/package.json 与 src/features | React 管理界面组织；不整套搬入复杂依赖 |
| 原客户端 UI | apps/desktop/ui/ | 仅参考聊天交互；不引入 Tauri、本地 bridge、sidecar |

参考网站未验证自动学习、图表实际运行、管理员页面。网页上看到某个开关不构成 V2 必须复刻其全部后台的理由。
本包保留 Go 是为了延续已有 Backend 经验；Python Runtime 独立保留。去掉独立 BFF/网关进程是个人版部署取舍，不是公司项目重构建议。
