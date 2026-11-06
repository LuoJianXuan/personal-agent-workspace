# V2 共同契约：三端必须共同消费

S00 将本文件落实到 schemas/openapi.yaml、schemas/jsonschema/ 与 schemas/examples/。首次只建最小模型与样例，不能为未来功能预设大量抽象。契约层不得依赖具体服务实现。

## 1. ID、身份与请求
ID 为 UUID/ULID 字符串，UTC 带时区时间。业务 thread_id 由 Backend 创建；run_id 由 Backend 创建提交意图时分配；graph_thread_id = run_id。
RequestContext = tenant_id/project_id/user_id/request_id。首版 tenant/project 为服务端固定 demo 值；用户来自认证，不能由请求体覆盖。
所有用户资源按 owner 校验；跨用户返回 404，管理权限不足返回 403，无效登录 401。管理员没有任意审批他人私有任务的旁路。
User token 不转发到模型/MCP；内部服务使用各方向独立令牌，禁止浏览器访问 /internal。

## 2. Backend 配置模型
ModelConfig（S02 已同步 schema）：id/name/provider/protocol/protocol_options/provider_model_name/base_url/credential_ref/context_limit/max_output_tokens/capabilities/enabled/is_default/revision。
字段约束与支持范围见 [决策 005](../decisions/005-model-access.md)。S02 已更新 JSON Schema、OpenAPI、共享样例与三端生成类型。provider 仅用于展示，可填写空字符串；配置写入 DTO 以完整字段提交，PATCH 携带当前 revision。首版 protocol 仅 openai_chat_completions，protocol_options 按协议严格校验，provider 只作可选展示元数据；首版仅准入非思考模式。
Skill = id/name/description/category/content/enabled/revision；UserSkillPreference = user_id/skill_id/enabled。
McpConnection = id/name/endpoint/credential_ref/enabled/revision/last_probe_at/probe_status。
McpTool = connection_id/remote_name/namespaced_tool_id/input_schema/schema_hash/enabled/revision；schema 变化后默认禁用并要求重新启用。
namespaced_tool_id 带连接 ID，避免两个 Server 同名工具冲突；截断/转码规则必须稳定并校验碰撞。
AdminAudit = id/actor/action/object_id/request_id/time/safe_changes/result。
所有变更使用期望 revision 防止覆盖并发更新；失败返回 CONFIG_CONFLICT。

EffectiveCapabilities = snapshot_id/created_at/context/model 的非敏感配置/选中 Skill 内容与 revision/启用工具 schema 与 revision/MCP 非敏感配置/file_refs。
模型快照按决策 005 冻结 protocol/protocol_options、可选平台元数据、非敏感连接参数及能力；普通用户 catalog 不返回连接与凭据别名。能力声明不等于真实验证结果。快照不能包含密钥。每次工具执行前调用 Backend validate，检查用户有效、提交归属、相关模型/技能/工具/MCP revision 与 enabled，失败关闭执行。Backend 不可达时不放行。
模型调用前也复核模型仍可用；已开始的外部请求不能追溯取消。相关配置变化后的旧 Run 不自动迁移，明确 CAPABILITY_CHANGED 并结束；新 Run 用新配置。

## 3. 用户 API（Backend /api）
| 方法与路径 | 作用与限制 |
| --- | --- |
| POST /auth/login；GET /auth/me | 登录与身份；成熟密码哈希、有效期 token；每次核对用户 enabled |
| GET /catalog/models；GET /catalog/skills | 当前身份可用配置，无密钥 |
| POST /capabilities/resolve | S02 配置预览；仅返回 snapshot_id/model_id/skill_ids/tool_ids，不暴露内部连接信息 |
| PUT /me/skills/{id}/enablement | 仅个人偏好 |
| POST/GET /threads；PATCH /threads/{id} | 创建、列表、改名 |
| GET /threads/{id}/messages | 用户消息与 canonical 最终结果投影，含 run_id |
| POST /threads/{id}/runs | input/model_id/skill_ids/file_ids/scenario?；Idempotency-Key；立即返回 202 |
| GET /runs/{id} | 提交状态 + Runtime 状态；不可达明确 runtime_unavailable |
| GET /runs/{id}/events?after_seq=N | 分页 canonical 事件历史，含正文块；响应含 next_seq/has_more，不跳过 message.delta |
| GET /runs/{id}/stream?after_seq=N | Backend 代理 Runtime SSE，登录与归属校验 |
| POST /runs/{id}/cancel | 持久取消请求，再幂等通知 Runtime |
| GET /runs/{id}/approvals | 当前提案与决定状态 |
| POST /approvals/{id}/decision | approve/reject；不得传 approved=true、工具结果或修改参数 |
| POST /runs/{id}/resume | 无客户端图状态；读取已保存决定，恢复原等待点 |
| POST/GET /files | multipart 上传、分页搜索；不接受磁盘路径 |
| GET /files/{id}；GET /files/{id}/content；GET /files/{id}/download | 元数据、受限预览、下载 |
| POST /runs/{id}/artifacts | 用户显式生成完成 Run 的 Markdown 报告，幂等 |
| GET /runs/{id}/artifacts | 本轮产物 |
| GET /scenes | 固定 CSV 场景定义，无场景编辑器 |

管理 API：
- GET/POST /admin/models；PATCH /admin/models/{id}，配置校验 endpoint /validate；无真实请求的检查不叫连通测试。
- GET/POST /admin/skills；PATCH /admin/skills/{id}。
- GET/POST /admin/mcp-connections；PATCH /admin/mcp-connections/{id}。
- POST /admin/mcp-connections/{id}/discover；GET /admin/mcp-connections/{id}/tools；PATCH /admin/mcp-connections/{id}/tools/{tool_id}。
- GET/POST /admin/users；PATCH /admin/users/{id}（仅 enabled，新增仅普通用户）。
- GET /admin/runs；GET /admin/audits（脱敏元数据，分页）。
删除能力首版统一禁用，不实现级联硬删除。管理操作必须记录审计。

## 4. Backend → Runtime（内部）
- POST /internal/runs：run_id/thread_id/context/input/history/effective_capabilities/file_refs/mode/request_hash。相同 run_id+hash 返回原接受结果，不同 hash 409。
- GET /internal/runs/{id}；GET /internal/runs/{id}/events；GET /internal/runs/{id}/stream。
- GET /internal/runs/{id}/approvals。
- POST /internal/runs/{id}/resume：decision_id；Runtime 从 Backend 读取决定并验证绑定。
- POST /internal/runs/{id}/cancel：稳定 command_id。
- POST /internal/runs/{id}/artifacts：Backend 已校验 owner；Runtime 读取已完成的持久结果生成 Markdown，经 Backend 文件接口确认 READY 后补 artifact.ready；不再次调用模型。
- POST /internal/mcp/discover：已授权 endpoint/credential_ref，限制只初始化和发现，不执行工具；工作进程总时限 6 秒、并发上限 4。
- GET /internal/configuration/status：返回部署允许目标及凭据是否存在，不返回密钥。
单实例 Runtime 为不同 thread 并发驱动；同 run 仅一个活动驱动句柄，数据库 CAS 状态防重复。

## 5. Runtime → Backend（内部）
- POST /internal/capabilities/validate：接收 snapshot_id/context 和可选 run_id。S02 预览可省略 run_id；S03 Runtime 每次模型/工具准入必须携带 run_id，Backend 复核提交绑定、owner、active/cancel_requested，以及用户和所有相关配置 revision。返回 allow/reason；预览结果不能作为执行许可。
- GET /internal/submissions/{run_id}：归属、取消标志与有效状态。
- GET /internal/approval-decisions/{decision_id}：只读已确认决定，检查 run_id 绑定。
- POST /internal/demo-tickets：run_id/execution_id/canonical_args/args_hash/decision_id。事务内检查归属、配置、取消、审批绑定，写工单和业务结果。
- GET /internal/demo-tickets/by-execution/{execution_id}：核查提交结果，不以未知响应认定没写入。
- GET /internal/files/{id}/content：检查该 file_id 属于 run 已授权引用且仍 READY。
- POST /internal/artifacts：run_id、稳定 artifact_key、类型、受限内容；只允许生成结果格式 MD/CSV/chart-json。禁止路径、任意 MIME、HTML/JS 执行。
内部接口属于工具 provider 的落点，不允许 Agent 绕过 ToolGatewayService 直接调用。

## 6. 数据表与唯一约束
Backend：
users；models；skills；user_skill_preferences；mcp_connections；mcp_tools；capability_snapshots；threads；
messages（最终助手消息唯一 run_id+message_kind）；
run_submissions（run_id 唯一、user_id+idempotency_key 唯一、active thread 部分唯一索引）；
dispatch_commands（command_id 唯一）；
approval_decisions（approval_id 唯一，包含用户/提案/参数/revision/期限/decision）；
demo_tickets（run_id 唯一、execution_id 唯一）；
demo_write_results（execution_id 唯一，含 request_hash 与原始业务结果）；
files/artifacts（artifact_key 唯一）；admin_audits。
Runtime：
runs（run_id 唯一）；tool_executions（execution_id 唯一）；
approvals（approval_id 唯一、execution_id 唯一）；
run_events（event_id 唯一、run_id+seq 唯一）；
LangGraph 自有 checkpoint 表；可选 run_event_outbox 仅在实际需要时引入。
两侧迁移分别负责自己的表；checkpoint setup 在明确的迁移入口，不在每个请求调用。

## 7. 创建与会话并发
Backend 在事务里锁 thread，先核对 user_id+idempotency_key，再检查 thread 活跃占用。
请求摘要含 thread_id、input、选定 model/skills/files/scenario；同键同请求返回原 run_id，异参 409。已接受请求重试不得因当前配置变更改写原摘要。
保存 submission、用户消息、启动命令后返回 202。dispatch 采用同 run_id 重试，不能自动创建第二个 Run。
请求历史只装配此前完成轮次的 user/assistant；不把不完整 tool_call 消息序列直接拼入新图。恢复原 Run 从原 checkpoint，不重新注入全量历史。
Backend 读到 Runtime 终态，幂等同步最终消息并释放活跃占用；两步同 Backend 事务。轮询同步不依赖浏览器连接。

## 8. 状态、审批与取消
Runtime Run：QUEUED/RUNNING/WAITING_APPROVAL/SUCCEEDED/FAILED/CANCELLED/INTERRUPTED。
工具：REQUESTED/WAITING_APPROVAL/RUNNING/SUCCEEDED/FAILED/DENIED/CANCELLED/UNKNOWN。
提案：PENDING/APPROVED/REJECTED/EXPIRED/CANCELLED。Backend 决定记录不可被前端编辑；Runtime 状态为其消费投影，不另造批准来源。
approval_id/execution_id 从稳定 run_id+tool_call_id 派生；参数采用排序键、固定数值与 Unicode 规则的 JSON 规范化，三端共享样例。首版不允许原提案改参。
每轮同时只允许一个待审批提案；模型一次返回多个工具调用按序执行，每个结果准确对应 tool_call_id，停在首个需要审批的操作。
每 Run 最多一张模拟工单。不同 tool_call_id 请求同一写参数可返回原业务结果；异参数冲突，不复用不匹配审批。
Backend 决策先拉取并验证当前提案/状态/归属/期限，条件插入决定；重复相同决定返回同记录，冲突决定 409。若取消竞态，Runtime 和业务提交再次裁决，已批准不等于已执行。
Runtime resume CAS 获取驱动权，读 Backend 决定、验证参数/revision，原图继续。
执行槽忙时，resume 幂等登记原 Run 的恢复排队意图，保留原 checkpoint/decision_id；队列也满则返回 429，Backend 以同一决定退避重试，等待态与审批记录不丢失。重启时先按 §9 核对可恢复等待点，再处理其他遗留状态；不能把审批恢复当新 start。
批准后写入节点与 interrupt 节点分开；恢复不得吞掉 GraphInterrupt 或随机换 ID。
拒绝：CANCELLED + APPROVAL_REJECTED；到期：FAILED + APPROVAL_EXPIRED；配置变化：FAILED + CAPABILITY_CHANGED；均释放 thread 占用，无业务写入。
等待审批时定期/查询时校验过期，收敛状态；不无限占用 thread。
取消先在 Backend 持久 cancel_requested，再通知 Runtime。未派发命令标取消，已存在 Runtime 的竞争由原 run_id 取消请求及执行前复核收敛。Runtime 节点边界检查；本地业务事务再次检查。
已发生写入不能宣称回滚；取消后的 Run 仍展示已成功工具结果。最终状态采用数据库条件更新，防止 CANCELLED 被迟到的 SUCCEEDED 覆盖。

## 9. 跨提交边界故障裁决
| 故障窗口 | 明确行为 |
| --- | --- |
| Backend 保存启动意图后、Runtime 接收前崩溃 | 重启重试原命令；不丢用户消息、不换 run_id |
| Runtime 已接收，回执丢失 | 重复 start 读回同 Run；Backend 不宣称未执行 |
| 图等待 checkpoint 已落库、Run 仍 RUNNING | 重启核对 checkpoint 的 interrupt 与持久提案 ID；能匹配则补成 WAITING_APPROVAL 并幂等补事件；不能确认则 INTERRUPTED |
| WAITING_APPROVAL 已发布 | 必须已确认存在对应持久 checkpoint；否则不发布可恢复状态 |
| 批准已保存、Runtime 尚未 resume | Backend 命令重试或用户显式 resume；读取原决定 |
| Runtime 已切 RUNNING 后崩溃 | 仅当前 checkpoint 明确是同提案等待点且无后续执行证据时恢复为等待；否则 INTERRUPTED；不承诺任意时刻续跑 |
| 工单提交成功，网络响应丢失 | 用 execution_id 查 Backend 原结果；查询不可达则 UNKNOWN，不能盲写或报明确失败未执行 |
| 工单成功，Runtime 成功记录/事件未写 | 核查原业务结果，恢复工具可确认结果；Run 不必自动续推理，可保持 INTERRUPTED 并展示已建单事实 |
| 文件写成功，元数据失败 | 无 READY，不发布成功产物；清理无引用临时文件；按稳定 artifact_key 重试 |
| 事件接收/浏览器断线 | 历史按 seq 补读并去重，不重新执行工具 |

Runtime 启动恢复先核对持久等待点，再把剩余孤立 QUEUED/RUNNING 收敛 INTERRUPTED，不能先粗暴清空所有等待机会。
自动修复只针对可证明的边界；不宣称跨框架/跨服务 exactly-once。

## 10. 事件与 SSE
Envelope：event_id/run_id/thread_id/seq/type/created_at/payload。seq 由 Runtime 数据库按 Run 原子分配，禁止裸 MAX+1。
类型：run.started/tool.requested/tool.started/tool.completed/tool.failed/approval.required/approval.resolved/message.started/message.delta/message.completed/run.completed/run.failed/run.cancelled/run.interrupted/artifact.ready。
message.started 携带稳定 message_id；message.delta 携带 message_id、从 0 连续递增的 chunk_index、text。只接收 provider 面向用户的正文内容，不暴露隐藏推理、原始工具参数增量或 SDK 对象。同一 Run 的不同模型轮次使用不同 message_id。
Runtime 将正文增量按最多 100 毫秒或 1 KiB 文本阈值（先到者）合并，沿完整 Unicode 边界切块；周期 flush 不等待下一个 token。结束前 flush 剩余内容。每块先持久化为 canonical event 再发送，共用 seq/event_id/after_seq，不另建临时 token 游标；阈值是应用缓冲目标，不是端到端延迟承诺。
message.completed 携带 message_id、完整 text 和 is_final；以完整内容替换同 ID 的增量草稿，不能再次追加全文。模型调用工具前的可见文字标 is_final=false；只有最终回答 is_final=true 才投影为本轮最终历史回答，工具卡与中间消息仍可从事件回放。run.completed 必须晚于最终 message.completed；增量不表示运行已成功。
前端按 event_id/seq 去重、按 message_id 拼接；刷新后若没有本地已应用草稿，必须从 seq=0 重建该 Run，而不能只保存游标跳过正文。有草稿时游标仅推进到已应用的事件；缺块则补读，不盲目拼接。失败、取消、INTERRUPTED 时将未完成草稿标为未完成，不投影成成功历史；已输出正文的模型调用首版不自动重试，避免同一消息混入两次生成。
最终回答与 message.completed/run.completed 在可解释的事务中存储，不能 UI 成功而 DB 无结果。
Backend 只转发并投影 canonical 事件；审批决定落库不自行伪造 Runtime 已恢复事件。
fetch SSE 携带 Authorization，不在 URL 放 token；after_seq 非负整数；SSE id=seq，前端按 event_id 去重。心跳与有界读取；断线只关闭订阅。
终态 Run 补完历史关闭流；报告可能在终态后产生，用户点击导出后由报告 API 刷新产物列表，不依赖已关闭的旧 SSE。
文件事实在 Backend；artifact.ready 由 Runtime 在确认文件 READY 后记录，重复导出/事件使用稳定键。
代理关闭缓冲并逐批 flush，连接断开不会取消后台运行。首版要求真实正文增量与已持久化文本块补读；不要求重现 provider 原始 token 边界或打字节奏。进程崩溃时尚未持久化的微小缓冲不承诺恢复，Run 按既定 INTERRUPTED 规则处理，不为续字重新执行模型或工具。
容量/超时采用 ARCHITECTURE 的单机默认值；订阅超限或 Runtime 入场超限为 HTTP 429/RESOURCE_EXHAUSTED + Retry-After。Runtime 入场拒绝不创建新 Run；Backend 保留同一待派发命令并退避重试，不能把 429 当成已开始执行；仅在确认未被接收时才可结束派发并释放占用，网络结果不明仍按原有保守规则处理。已接收但回执丢失的同 run_id 重试必须返回已有 Run，不受新入场配额影响。

## 11. 错误与模型预算
错误体 code/message/request_id/details?；无堆栈、凭据、原始 SDK 对象。
至少：UNAUTHENTICATED/FORBIDDEN/NOT_FOUND/INVALID_ARGUMENT/CONFIG_CONFLICT/THREAD_BUSY/IDEMPOTENCY_CONFLICT/RUNTIME_UNAVAILABLE/RESOURCE_EXHAUSTED/CAPABILITY_CHANGED/MODEL_UNAVAILABLE/MODEL_TIMEOUT/MCP_UNAVAILABLE/TOOL_DENIED/TOOL_TIMEOUT/APPROVAL_EXPIRED/APPROVAL_CONFLICT/RUN_NOT_RESUMABLE/OUTCOME_UNKNOWN/FILE_TOO_LARGE/UNSUPPORTED_FILE。
模型最大步骤 12、每次调用超时 60 秒、工具超时默认 20 秒、总体运行时限可配置；真实调用次数/预算需单独授权。
供应商与模型错误不能静默切换 Mock。mode 是服务端字段，页面与报告始终显示。
