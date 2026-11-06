# 架构与技术决策

## 三个应用角色

Web：React + TypeScript + Vite，pnpm；React Router、TanStack Query、现成组件库，ECharts 只用于固定图表。/app 与 /admin 同工程、不同布局。
Backend：Go + Gin + GORM/PostgreSQL；显式版本迁移，不使用启动自动改表。保留用户熟悉的 Go 控制面职责。
Runtime：Python 3.13 + FastAPI + LangGraph + Postgres checkpointer + MCP 官方 Python SDK，uv 管理。先用最小图，不引入完整 DeepAgents harness。
版本在 S01 依据实际可安装兼容组合锁定：pnpm-lock.yaml、go.sum、uv.lock；不得凭空宣称 latest 或伪造锁文件。

    浏览器 → Web/Nginx → Backend /api
                            ├─ PostgreSQL backend schema
                            ├─ 受控文件卷
                            └─ Runtime /internal
                                  ├─ PostgreSQL runtime/checkpoint schema
                                  ├─ ModelAdapter → 模型 provider
                                  └─ ToolGatewayService
                                       ├─ MCP provider → demo MCP
                                       ├─ 固定读文件/CSV 工具 → Backend 文件 API
                                       └─ demo 工单 provider → Backend 内部写接口

Compose 服务：web、backend、runtime、postgres、demo-mcp。只有 web 对用户暴露；开发环境可绑定 localhost 调试端口。Runtime 和内部写接口不得经公网代理暴露。
HTTP/SSE 由 Backend 接收并代理 Runtime 的持久事件流；浏览器不持有服务凭据、不直接连接 Runtime。
Backend 不调用模型或运行 Agent loop。MCP 发现由 Runtime 执行，Backend 保存发现结果与启用决策。
模型边界按 [决策 005](../decisions/005-model-access.md) 在 S02/S03 扩充：Backend 保存协议/协议选项/能力配置，Runtime 仅按冻结的 protocol 选择适配器；平台标识不参与选择。首个目标为 DeepSeek 非思考模式；兼容协议复用适配器，真正不同的协议后续单独实现。当前尚无真实模型适配实现。

## Backend 内部分层与未来拆分
首版仍是一个 Go Backend 进程，内部固定为三个模块，不增加部署服务：
- `internal/control`：用户、权限、模型、Skill、MCP 配置与 revision；对外提供授权与能力快照接口。
- `internal/workspace`：会话、用户消息、submission/派发命令、文件、审批决定与最终历史投影；维护业务事务。
- `internal/agententry`：运行入口编排、RuntimeClient、SSE 代理、查询/取消/审批恢复转发；通过前两者的应用接口取得数据，不直接访问它们的表或复制业务判断。
模块的 handler 不互相调用；共享身份上下文、契约类型和基础设施不反向依赖业务模块。agententry 不调用模型、不执行工具、不维护第二份 Run 状态。后台轮询器调用 workspace 命令接口和 RuntimeClient，不能把跨服务 HTTP 包在数据库长事务中。
Web 只调用 Backend 是本项目首版拓扑选择，不是所有 Agent 产品的必然要求。选择合并入口是为减少 5–7 天内的部署、认证和联调成本；代价是入口与配置 API 共用进程、资源及发布时间，Backend 故障也会影响用户访问运行流。
仅在聊天连接需要独立扩容、多个客户端共用复杂入口、或入口需要独立发布时，评估将 agententry 抽成 Business Gateway。抽出后通过 Backend API 获取业务数据，Runtime 协议及数据所有权保持不变；同步依赖 Backend 时仍受其可用性影响。首版不实施此拆分，不承诺仅移动目录即可完成迁移。

## 连接、超时与容量边界
以下是单机开发默认值，环境变量可覆盖，不是压测能力承诺：
- 普通业务 API 总超时 15 秒；文件传输、MCP 探测等长操作使用显式独立超时。Runtime 普通 RPC 连接超时 3 秒、响应超时 10 秒；模型调用沿用 CONTRACTS 的 60 秒上限。
- SSE 使用独立 HTTP client/连接池，不套普通 RPC 总超时；每 15 秒发送注释心跳，45 秒无字节由订阅方断开并带游标重连。Nginx 上游读取超时 60 秒，关闭流式响应缓冲；写入设 10 秒期限，逐次刷新，避免慢客户端永久占用连接。
- 每用户最多 4 条 SSE 订阅、Backend 总计 32 条；超额返回 429/RESOURCE_EXHAUSTED 和 Retry-After。订阅不持有数据库事务或独占数据库连接；每订阅发送缓冲最多 64 个事件，满后关闭该订阅，由客户端按游标补读，不能阻塞 Agent。
- Runtime 同时执行最多 4 个 Run，持久 QUEUED 上限 32；同 run 幂等查询先于容量判断，新 Run 超额在接收前返回 429，由已有派发命令退避重试。等待审批不占执行槽，批准恢复重新排队且不新建 Run。具体抢占/CAS 在 S03 落实；不新增 Redis。
- 配置 API、Runtime 普通 RPC 与 SSE 分别设置并发门限/连接池；保证长连接不能耗尽普通 RPC 池。共享进程仍可能争用 CPU/内存，这些限制不等于完全隔离。

## 数据所有权：禁止第二套运行事实

| 数据 | 权威写入者 | 消费方式 |
| --- | --- | --- |
| 用户、角色、模型/Skill/MCP 配置、授权 | Backend | Runtime 收请求级快照，执行前通过内部接口复核 |
| thread、用户消息、运行提交意图 | Backend | 内部 start 请求，历史由 Backend 装配 |
| Run 状态、工具记录、canonical events | Runtime | Backend 代理查询/事件；缓存仅是投影 |
| 审批提案与等待点 | Runtime | Backend 读取并显示 |
| 用户审批决定与管理审计 | Backend | 决定 ID 交给 Runtime，再从内部 API读取验证 |
| 模拟工单与幂等业务结果 | Backend | 仅逻辑工具网关的内部写接口 |
| 图 checkpoint、待发运行事件 | Runtime 外置存储 | LangGraph 官方 checkpointer/运行仓储 |
| 文件、生成报告与索引 | Backend | Runtime 通过带作用域的内部接口读写 |
| 助手历史消息 | canonical 最终事件 | Backend 幂等投影，不重新生成内容 |

两服务可共用 PG 实例，但数据库用户只拥有各自 schema；不跨 schema JOIN 或直接修改另一服务表。
Runtime 进程内只有连接、缓存、驱动句柄；持久状态在外部 PG。单实例首版不等于长期状态存在内存。

## 最小服务认证
开发/Compose 使用两个不同的服务令牌，分别限定 B→R 与 R→B；用 Authorization header，环境注入，不写日志。公开用户 API 拒绝服务令牌冒充用户。
内部请求必须带服务端构造的 tenant/project/user/run 关联；接收方验证关联到已存在的提交记录和资源，不只相信 payload.user_id。
模型/MCP 凭据别名由后端配置，真实 secret 由 Runtime 环境解析，仅在 adapter 调用时使用，不进入快照正文、图状态、事件或浏览器。

## 派发可靠性
Backend 在同一事务保存用户消息、submission 与启动命令。一个简单后台轮询器重试 Runtime start；不另装消息中间件。Runtime 根据 run_id + 请求摘要幂等接收，回执丢失不能生成第二个 Run。
Backend submission 只表示 PENDING_DISPATCH/ACCEPTED/DISPATCH_FAILED，不是 Run 状态。Runtime 不可达时 UI 显示待派发/失败，不冒充运行中。
每个 thread 同时最多一个活跃 submission；唯一约束加事务锁。Backend 查询 Runtime 终态后释放占用；查不到或不可达时保守保留，不凭超时认定未执行。
Backend 重启重试未确认命令；Runtime 重启只承诺可确认审批等待点恢复，其余遗留在途状态按 CONTRACTS 处理。

## 执行与写入边界
所有业务工具都调用 Runtime 内的 ToolGatewayService，集中完成白名单、schema、归属、配置 revision、审批绑定和审计。
它是个人版逻辑 Tool Gateway，不是普通函数随意调用集合；不另起一个服务降低部署成本。
create_demo_ticket 通过 Backend 内部接口在一个事务中检查批准/取消标志与能力 revision，写入工单和稳定业务结果，唯一 execution_id/run_id。Runtime 随后记录工具终态；两者之间断线时通过 execution_id 查原结果，不盲目重写。
取消或禁用在动作提交之后到达不能撤回已有写入；界面如实展示已完成工具结果。

## 文件与事件
Runtime 不直接读 Backend 磁盘；文件引用必须在提交时验证 owner，并在工具读取时再次验证。文件内容按需注入，默认不把所有文件全文塞入每轮 prompt。
Runtime Run 状态、工具本地记录与对应关键事件尽可能同库事务提交；与 checkpointer、Backend 业务提交分开，不能声称跨服务原子提交。
Backend 拉取事件投影历史，以 event_id 唯一去重；无需单独实现事件回调总线。
SSE 首版同时传关键进度、面向用户的回答正文增量和完整消息。ModelAdapter 必须读取 provider 的真实流式输出，经 Runtime → Backend → Web 连续传递，不能等待全文后用动画模拟流式。允许按短时间窗口合并 token 为文本块，具体持久化、重连和完成语义见 CONTRACTS §10；不要求一个汉字对应一个 SSE 事件。模型隐藏推理、工具参数碎片和内部调试数据不作为回答正文输出。

## 官方依据
- LangGraph interrupts：https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph persistence：https://docs.langchain.com/oss/python/langgraph/persistence
- MCP Python SDK：https://github.com/modelcontextprotocol/python-sdk
恢复中断会重新执行所在节点的前部；选定版本的 import/stream 细节由 S01 核对，不能照搬当前在线文档的新 API 到不兼容锁版本。
