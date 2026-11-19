# 设计

## 分类与信任

`deploy/targets.json` 对每个精确 endpoint + credential_ref 声明：

- `read_only_tools`：可直接进入 Tool Gateway。
- `approval_required_tools`：可以进入能力快照，但 `requires_approval=true`。
- 未列出的工具：发现可见，`access_mode=blocked`，不能启用。
- `max_calls_per_minute`：Runtime 在持久化 execution 前按连接加锁计数。

MCP 返回的 `readOnlyHint` 只保存在控制面供管理员核对，不能覆盖部署分类。

## 执行链

```text
Agent / DeepAgents
  -> ToolGatewayService
  -> schema + scope + snapshot validation
  -> DeepAgents HITL interrupt（仅 write）
  -> argument-bound approval decision
  -> durable execution reservation + rate limit
  -> short-lived MCP worker
  -> canonical tool events + Langfuse tool observation
```

只读与写入共用 Registry、Policy、Lifecycle 和 Router。进程在远端写入后失联时标记 UNKNOWN，不盲目重试。

## 凭据

数据库和契约只保存 `credential_ref`。真实 Token 仅存在被 Git 忽略的 `.env` 并注入 Runtime；控制面、canonical events、工具结果和验收证据均不得包含 Token。

## 工作台

- 增加“能力设置”，展示模型、技能、只读工具和逐次审批工具。
- 管理端展示部署分类与服务端声明。
- 对话端按 `execution_id` 聚合工具事件，避免同一次调用显示为多个模块。
- 审批卡不再绑定“演示工单”文案，展示真实 namespaced tool 与完整参数。
