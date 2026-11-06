# 006 — 第一阶段采用框架优先的 Harness 重构

日期：2026-11-05；验收更新：2026-11-06。已采纳并写入S08–S15，本地隔离业务/浏览器/真实Docker验收通过；真实供应商和日常发布待验证。见 [本次验收](../phase1-acceptance-2026-11-06.md) 与 [交付说明](../phase1-refactor-delivery.md)。

用户提出：框架已经提供的能力应优先采用，减少重复自研和层层包装。本文修订 plan-v3 中“模型桥接”“审批适配”等措辞的含义；以更少的自有运行机制为目标，不保留两套 Agent loop。

## 重构前审批基线（历史说明）

当前不是没有审批。engine.py 对 builtin_create_demo_ticket 创建提案并通过 LangGraph interrupt 等待；approvals.py 保存提案、校验参数摘要/权限版本/到期时间并恢复；Go Backend 保存用户决定、做归属验证与工单幂等写入；Web delivery.tsx 展示完整参数和批准/拒绝。

只读 MCP、资料读取和固定 CSV 计算不弹审批。审批围绕合成工单，不是任意工具或多级组织审批平台。旧版本验证依据是 2026-11-04 的隔离回归；本次已将等待/恢复替换为官方 HITL，仍保留参数/归属/有效期/幂等校验，新链路已通过本次隔离Mock审批/恢复/故障回归，真实模型尚未验证。

## 三个决策

1. **通用执行机制交给框架。** DeepAgents 负责 Agent loop、工具调用编排、计划/上下文机制；LangChain 提供模型集成、工具 schema 与限次中间件；LangGraph 提供 checkpoint、中断恢复和执行基础。删去对应自研机制，不在新 Agent 外继续包旧 StateGraph。
2. **只保留应用规则与集成。** 身份/授权、文件作用域、凭据目的地址、审批决定审计、有效期/参数绑定、写入幂等与对账、跨运行授权额度、产品事件持久化与下载权限属于本项目。以 middleware、工具 provider、文件 backend 和薄事件转换接入，不重新实现一个框架。
3. **以行为兼容和代码减少为结果。** 优先标准模型客户端和标准 HITL；遇到确认的缺口才加最小补丁。验收包括旧机制删除清单、没有双重状态机/计数/审批，且原有权限、恢复和业务结果不退化。不能仅凭行数变少宣布成功。

## 能力采用表

| 能力 | 框架可用机制 | 本项目保留的部分 |
| --- | --- | --- |
| 模型接入 | 接受支持工具调用的 LangChain ChatModel；使用维护中的标准集成 | protocol→客户端构建、允许地址/选项、凭据解析、已确认的供应商兼容缺口 |
| 工具执行 | 标准 tool/args_schema、模型→工具循环、中间件钩子 | 授权快照、owner/revision、真实执行路由、业务幂等/审计；逻辑网关不另起一套调度 |
| 审批 | HumanInTheLoopMiddleware / interrupt_on、checkpoint 与 Command(resume) | 决定入口鉴权、业务参数绑定/过期/撤权、审计和副作用幂等；不再手写 approval 图节点 |
| 流式 | 正文、工具、状态等框架流事件 | 归一化/过滤、产品事件落库、SSE 补读/去重、历史投影；不自行拼模型供应商 SSE |
| 取消 | 底层异步任务/运行机制与框架执行集成 | 取消请求鉴权与持久化、传递到工具/worker、终态收敛及已发生副作用的核查 |
| 限额 | ModelCallLimitMiddleware、ToolCallLimitMiddleware 等可配置机制 | 验证其计数范围；按实际请求统计重试/摘要、部署授权总额度及后续费用上限 |
| 上下文 | 官方结果外置/摘要能力 | 文件作用域、阈值与任务约束、凭据过滤、摘要调用预算、来源引用；不再自建并行摘要算法 |

“可用”不等于默认开启。LangChain 的限次是模型/工具调用控制，不是现成的跨用户财务账本，也不能未经核对就认定覆盖 SDK 内部 HTTP 重试或独立摘要调用。DeepAgents 的内建文件权限仅覆盖其文件工具，不能替代 MCP、自定义工具或 execute 的业务授权与隔离。

## 对 S08–S13 的执行要求

- S08 先做采用/删除矩阵，核对标准 ChatModel、HITL、限次和流接口是否覆盖现有行为，再决定确需保留的补丁；不把旧 models.py 整体包成新的自定义模型作为默认方案。
- 协议优先保持不变：例如 openai_chat_completions 可构建经验证的标准兼容 ChatModel，provider 标签只用于展示。客户端选用和受控参数须按选定版本验证，不宣称一套客户端天然兼容所有平台。
- S09 删除旧 model/prepare/approval/execute/merge 通用图循环，使用实际 create_deep_agent。Engine 缩为任务接收、执行调度、终态与运行存储集成，不负责第二次编排。
- 旧 ApprovalService 的图节点识别、interrupt 重写与重放流程，由框架 HITL/checkpointer 替代。Backend 决定记录和执行前规则保留；同一批准只驱动一次规范化恢复。
- ToolGatewayService 收敛为治理钩子和 provider 调用。标准参数类型处理复用框架；跨服务协议入口仍按共享 schema 校验，业务归属/参数摘要与执行幂等仍独立校验。
- 使用官方模型客户端读取/合并供应商增量。自有代码只转换已标准化消息和事件、过滤私密内容、保存可重放的产品事件。
- 在入口鉴权后向活动执行传播取消。先证明实际 SDK/HTTP/工具的取消行为，再保留最小外层协调；断开 SSE 订阅不等于取消业务运行。
- 调用限制优先采用官方中间件，硬性真实请求额度在实际传输/执行边界统一守护。确保一个业务 Run 经审批恢复不重置限额，也不把框架 thread 与业务 conversation 的含义混淆。
- S13 使用官方摘要/外置机制，加作用域与预算适配，不另起第二套压缩循环。启用时须确认内部摘要请求同样受到预算限制。

## 删除候选与保留项

| 文件/模块 | 重构方向 |
| --- | --- |
| runtime/app/engine.py | 移除手写通用 StateGraph 和模型/工具轮转，保留薄运行协调 |
| runtime/app/models.py | 标准客户端优先；移除可被替代的 SSE 解析、tool 参数拼接、消息封装；保留经验证必要的配置/过滤规则 |
| runtime/app/approvals.py | 移除重复的框架等待/恢复机制；保留或迁移有效期、参数绑定与业务决定核验 |
| runtime/app/tool_gateway.py | 不建第二个 ToolNode/工具循环；保留治理、provider、审计与幂等 |
| Backend / Web | 保留产品身份、文件、历史、审批 UI 与下载等实际功能；按精简后的契约更新集成 |

迁移处理和验收授权继续沿用第一阶段方案。旧完成历史保留可读，旧在途任务按旧引擎收敛/显式结束，新图不盲读旧 checkpoint。上线后不长期维护两套自研编排。

## 官方依据

- [Models](https://docs.langchain.com/oss/python/deepagents/models)
- [Human-in-the-loop](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)
- [Streaming](https://docs.langchain.com/oss/python/deepagents/streaming)
- [LangChain prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- [Permissions](https://docs.langchain.com/oss/python/deepagents/permissions)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

区分自托管 SDK 与托管/Agent Server 产品：不把托管服务的 REST、账户权限、运行管理或计费能力当作安装 DeepAgents SDK 后自动获得的功能。具体版本 API 与可删代码以 S08 核对和授权后的兼容验证为准。

## 灵机 AI 只读核对后的补充

公司当前锁定 deepagents 0.7.13，实际通过 create_deep_agent 装配模型、工具、中间件、文件 backend、子代理、interrupt_on 与 checkpointer；轻聊天另有无工具 create_agent 路径。其整体方式是框架执行加自有治理，不能据此推导所有自研中间件都该移除。

具体核对：模型使用继承 ChatOpenAI 的兼容客户端，经 NewApi 模型网关调用；工具经独立 Tool Gateway，包括文件 backend；额度有自定义 TokenQuotaMiddleware/RunUsageLedger；取消等待网关确认执行收敛；流事件转换为持久规范事件再投影到 UI。这些是代码事实，不代表当前部署全部实测通过。

审批还明确区分来源：框架 HITL 与工具网关审批。标记 approvalOwner=tool_gateway 的工具不会再进入框架 interrupt_on，避免同一动作先被框架批准一次、再被网关批准一次。网关的审批结果由薄中间件转换为 LangGraph interrupt，继续复用同一暂停/恢复基础。

对本 Demo 的约束：每个工具只有一个审批裁决来源；简单已知工具优先用官方 HITL，业务校验在最终执行边界完成。如后续实际需要网关裁决或异步执行等待，再接入相应中断适配，不能为参考公司实现而预先复制两条复杂路径。官方条件审批能覆盖的规则也先复用官方能力。保留治理模块边界，不立即复制独立网关和企业级配额系统。

源码定位（只读，未复制实现）：

- C:/MyWorkSpace/lingji-ai/services/runtime/src/deepagent/assembly/assembler.py：670、723。
- C:/MyWorkSpace/lingji-ai/services/runtime/src/deepagent/model/resolver.py：200。
- C:/MyWorkSpace/lingji-ai/services/runtime/src/deepagent/model/openai_compat.py：30。
- C:/MyWorkSpace/lingji-ai/services/runtime/src/deepagent/policy/tool_visibility.py：91。
- C:/MyWorkSpace/lingji-ai/services/runtime/src/deepagent/middleware/tool_execution.py：80。
- C:/MyWorkSpace/lingji-ai/services/runtime/src/deepagent/middleware/token_quota.py：70、304。
- C:/MyWorkSpace/lingji-ai/services/runtime/src/services/orchestration/run_service/cancellation.py：165。
- C:/MyWorkSpace/lingji-ai/docs/runtime-core/runtime-architecture.md：7。
