# 阶段 2 前置收口最终准入

日期：2026-11-16。结论：通过，可以进入阶段 2；MCP 1.1 与工作台基线不再继续扩张范围。

## 五项收口结果

1. **真实只读 Agent 链路：通过。** 麦当劳 `now-time-info` 从 Agent 对话入口经过 Tool Gateway，产生完整 canonical events、Backend 审计和 Langfuse Tool Span。真实 MCP 只读 1 次、写入 0 次、真实模型 0 次。
2. **真实失败场景：通过。** 错误 Token 收敛为 `MCP_UNAVAILABLE`，worker deadline 收敛为 `TOOL_TIMEOUT`；MCP 下线与恢复在完整回归中通过，凭据和上游正文未泄露。
3. **工作台交互：通过。** 计划卡、结构化追问卡和错误类型恢复卡已接入；追问选项不会自动发送。
4. **浏览器验收：通过。** 管理端 MCP、普通用户能力页、390×844 能力页与聊天页均通过；无横向溢出，console error 为 0，未触发外部调用。
5. **发布准入：通过。** 完整 Mock 回归、目标 timeout 回归、生产构建、portable artifacts 回归、正式控制面发现和 5173 健康检查均通过。

## 运行态

- `agent-workspace-postgres-1`：healthy
- `agent-workspace-backend-1`：healthy
- `agent-workspace-runtime-1`：healthy
- `agent-workspace-demo-mcp-1`：healthy
- `agent-workspace-web-1`：运行中，`127.0.0.1:5173` 返回 200

## 不阻塞阶段 2 的部署事实

- 正式环境已通过本机被 Git 忽略的 `.env` 启用 Tavily 与公开网页读取；Runtime 重建后正式 API 返回 fetch/search 均可用。恢复配置时没有新增真实 Tavily 调用。隔离计算代理仍未配置，UI 不发生隐式回退。
- 正式网页的 DeepSeek + 麦当劳只读 MCP 联合链路已通过，使用 2 次真实模型请求和 1 次真实只读 MCP。
- Langfuse Key 未进入 Git，但没有随正式 Runtime 重建持久注入；本次联合 Run 按设计旁路观测并成功，因此当前仍需补一次“重新注入专用 Key 后的真实联合 trace”才能恢复完整观测准入。
- 未开放 OAuth、stdio、legacy SSE、MCP 商城、任意 Header 输入或未知工具自动准入。

详见 [MCP-11](MCP-11.md) 和 [UI-01](UI-01.md)。
