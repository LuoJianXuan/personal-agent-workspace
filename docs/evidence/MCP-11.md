# MCP 1.1 与工作台基线验收

日期：2026-11-16。结论：阶段 2 前置准入范围通过。

## 代码、构建与完整回归

- 共享契约重新生成，Web TypeScript 与生产构建通过（3951 modules，仅有既存 chunk-size 提示）。
- Runtime Python 编译、portable contract/source 检查和 `git diff --check` 通过。
- 完整 Mock 业务回归通过。Mock 只替换模型输出；DeepAgents、PostgreSQL checkpoint、Backend、Tool Gateway、MCP SDK、审批、文件、沙箱、产物与 canonical events 均为真实模块。
- 最终 timeout 修正后再次执行完整 Day 2 回归及 Runtime access 单元测试，全部通过。
- 本轮真实 DeepSeek 调用 0，真实搜索调用 0。

## 麦当劳 MCP：Agent 入口真实链路

- endpoint：`https://mcp.mcd.cn`，Streamable HTTP。
- 正式控制面发现 36 个工具：read 16、write 4、blocked 16。
- 只启用 `now-time-info`；启用写工具数 0。
- Agent 对话入口由 Mock 模型发起一次真实只读调用，经 Tool Gateway 产生同一 execution ID 的 `tool.requested`、`tool.started`、`tool.completed`。
- Backend 审计存在，Langfuse 同一 trace 中存在 `AGENT`、`CHAIN`、`GENERATION` 和精确 namespaced MCP `TOOL` observation。
- 四个已知写工具保持禁用且未调用：`delivery-create-address`、`create-order`、`auto-bind-coupons`、`mall-create-order`。
- 真实 MCP 只读调用 1，真实 MCP 写调用 0；凭据未进入事件、日志、Langfuse、checkpoint、模型上下文或证据。

## 安全失败

- 真实错误 Token 经独立 MCP worker 返回稳定的 `MCP_UNAVAILABLE`，未透传上游正文或凭据。
- 卡住的 worker 在 deadline 后返回稳定的 `TOOL_TIMEOUT`，父进程完成回收。
- MCP 下线、恢复和能力撤权由完整 Day 2 回归覆盖；失败不拖垮会话或 Backend/Runtime 健康状态。
- 验收中发现 worker 已获得完整 JSON 后仍等待 transport 清理会造成假超时，已改为单行结果协议、父进程限长读取和显式子进程回收。真实冷启动目录发现使用 12 秒内层 deadline，Backend 仅对 discover 路径使用 15 秒外层 deadline。

## 正式 5173 与浏览器

- PostgreSQL、Backend、Runtime、Demo MCP 均 healthy；Web 在 `127.0.0.1:5173` 返回 200。
- 管理端 `/admin/mcp` 显示麦当劳连接发现成功；工具抽屉同时显示只读许可、写入/每次审批、未许可三种部署准入，`now-time-info` 为唯一启用项。
- 普通用户 `/app/capabilities` 显示已授权工具，并明确解释网页读取、搜索和隔离计算为何不可用。
- 390×844 下能力页与对话工作台 `scrollWidth == clientWidth == 390`；浏览器 console error 为 0。
- 浏览器验收没有发送消息、没有执行配置变更、没有调用模型或工具。

## 脱敏与边界

- Git 跟踪文件与当前 Runtime 部署秘密逐值比对为 0 命中；通用 secret pattern 唯一命中是单元测试中的假值。
- 本次证明的是部署清单准入的 Streamable HTTP MCP、只读调用、通用写审批和当前工作台闭环，不代表 16 个未知工具已获准使用，也不证明 OAuth、stdio、legacy SSE 或任意第三方 MCP 均已兼容。
- 2026-11-16 从正式网页完成了 `DeepSeek → 麦当劳 now-time-info → 最终回答` 联合验收：成功 Run 使用 2 次真实模型请求、1 次只读 MCP、0 次写工具。
- 本次联合验收发现 Langfuse Key 没有随 Runtime 重建持久注入，因此这次成功 Run 没有 trace URL；Agent 按设计旁路观测并成功完成。之前的 Mock 麦当劳链路仍有 Langfuse Tool Span，但不能替代本次真实联合链路的观测证据。恢复 Langfuse 需要部署环境重新注入专用 Key，不能把 Key 写入仓库。
- 正式环境已在本机被 Git 忽略的 `.env` 中启用公开网页读取和 Tavily，并设置 1000 次本地搜索窗口；Runtime 重建后的 `/api/capabilities/network` 返回 `fetch_available=true`、`search_available=true`。本次部署配置恢复没有新增真实搜索调用。隔离计算代理仍未配置，能力页按事实显示不可用，不静默回退。
