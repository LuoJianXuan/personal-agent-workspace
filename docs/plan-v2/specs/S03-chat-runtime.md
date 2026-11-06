# S03：通用聊天、独立 Runtime 与真实工具入口

时间：D3。前置：S02。

## 目标
打通 Web → Backend → Runtime → 模型/只读 MCP → canonical events → Web；固定工单不是唯一入口。

## 实施任务
- Backend 创建 thread/message/submission 和派发命令，事务保证幂等与单 thread 活跃约束；轮询器按原 run_id 重试。
- Runtime 幂等接受 start，CAS 驱动、运行查询、持久事件与最终回答；单实例并发协调，不声称分布式调度。
- LangGraph 最小图：模型→工具判断→ToolGatewayService→模型，限制步骤/超时/结果大小；同一模型批次工具串行处理。
- 按 [决策 005](../../decisions/005-model-access.md) 实现公共 openai_chat_completions 协议适配器；注册表仅以 protocol 选择，provider 不参与分派，protocol_options 仅作受校验的兼容参数。以 DeepSeek 非思考配置完成首次接入。先打通 DeepSeek 的正文流、完整工具请求/回传和错误归一化，再复用兼容接口；不宣称其他平台已经验证。MockAdapter 仅产生确定性模型响应，走同图/同工具/同事件。
- 准备适配器传输 fixture 与真实 chat/stream/tool_loop 分项验收入口，后者独立授权并按配置 revision 记录结果。首版不启用思考模式，不开放任意供应商参数透传。
- ModelAdapter 消费真实增量；MockAdapter 提供可控分块输出与中途失败。Runtime 按 CONTRACTS 合并/持久化正文块，Backend 即时转发，Web 按 message_id 增量渲染并用 completed 全文收敛；不以全文打字动画代替流式。
- 接 Postgres checkpointer，graph_thread_id=run_id；历史由 Backend 装配，排除不完整 tool_calls。
- 逻辑 Tool Gateway 统一验证工具名、schema、owner、快照 revision，MCP 调用无旁路；写工具此阶段明确 APPROVAL_FLOW_NOT_READY。
- Web 对话布局：会话列表/改名/多轮消息、模型与 Skill 选择、工具状态卡、错误、最终 Markdown。
- Backend 代理 SSE与事件查询，前端 after_seq/event_id 补读去重；驱动不依赖订阅连接。
- 落实 ARCHITECTURE 的独立 RPC/SSE 连接池、超时、心跳、慢订阅断开、订阅配额与 Runtime 有界并发/排队；等待审批释放执行槽，恢复重新排队。共享进程不宣称完全隔离。
- Backend 后台同步终态与最终消息投影，原子释放 thread；Runtime 不可达显示未知/待派发，不擅自标完成。
- 前后台具备按 run_id 查询的脱敏运行详情。

## 完成与验收条件
- 可演示普通聊天、第二轮引用与只读 MCP 查询三种请求，Mock/真实状态分别标识。
- 双重提交、派发回执丢失使用同 run_id；另一个用户看不到 Run。
- SSE 刷新不 POST，不因断线终止 Agent，不重复最终消息。
- 在模型完成前能看到多个正文块；最终全文不重复追加。生成中断线/刷新可补读持久化块，失败/取消保留未完成标识，工具参数与隐藏推理不混入正文。
- 达到订阅上限返回 429，慢订阅不阻塞 Run；订阅保持时管理 API 可响应。Runtime 入场超限重试同 run_id，等待审批不耗尽执行槽。
- 模型失败有终态，未配 key 不静默换 Mock。
- 准备 A07–A10/A18 入口；获得授权才执行。

## 交付记录
更新 TASKS.md、docs/evidence/S03.md；列出真实文件、接口、迁移、已执行动作、未执行验证、下一任务接入点。所有代码由 AI 编写。

## 随实现讲解
追踪一次通用请求，指出哪里创建 thread/run、哪里调用模型、谁最终准入工具、最终消息来自什么事件。

## 可直接下发
阅读共同规则、架构、契约和 UI_SPEC，核对前置后只完成本 S03。保持独立三端与冻结首版范围，不主动启动子代理。默认不执行测试或真实模型，准备验收入口并标明状态；已明确授权的动作按原范围继续。不要要求用户手写，不以讲解阻塞下一阶段。
