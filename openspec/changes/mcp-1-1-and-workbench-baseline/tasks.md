# Tasks

- [x] 更新共享契约：MCP access mode、approval requirement、server hint、连接速率。
- [x] 扩展部署准入：本地合成 MCP 与麦当劳 MCP 精确工具清单。
- [x] 控制面支持 read/write/blocked 发现、启用、快照与撤权校验。
- [x] Runtime 将通用 MCP 写工具接入 DeepAgents HITL 和现有参数绑定审批。
- [x] MCP worker 增加双重分类校验；生命周期增加持久速率限制。
- [x] 新增本地合成写工具，只用于无外部副作用的审批验收。
- [x] 增加能力设置入口、管理端分类展示、通用审批卡和工具事件聚合卡。
- [x] 通过 Web/Go/Runtime 静态与单元检查。
- [x] 通过隔离完整 Mock 业务回归，真实模型调用 0。
- [x] 通过麦当劳 MCP 真实发现与 `now-time-info` 只读调用，真实写调用 0。
- [x] 切换日常 5173 并通过正式控制面发现，仅启用已验收只读工具。
- [x] 完成密钥与 Git 跟踪检查并记录证据。
- [x] 从 Agent 对话入口调用麦当劳 `now-time-info`，验证 Tool Gateway、canonical events、审计与 Langfuse Tool Span。
- [x] 真实验证错误 Token 的安全失败，并验证 worker 超时与 MCP 下线恢复，不泄露上游响应或凭据。
- [x] 增加计划卡、结构化追问卡和按错误类型给出下一步的失败恢复卡。
- [x] 浏览器验收管理端 MCP 页、普通用户能力页和 390×844 工作台布局；未发送消息或调用模型。
- [x] 完成最终 Mock 回归、正式 5173 健康检查和阶段 2 前置准入报告。
