# 详细设计

## 1. 现状与修改落点

### 实现差异

- 迁移 008 为个人连接使用独立表，平台连接与旧 API 保持原表。有效授权以逐工具指纹集合及授权版本保存在个人连接行，授权变更由审计记录保留。迁移 009 增加管理员发布状态。
- 管理员通过管理页发布、隐藏部署准入清单中的定义。个人入口使用已知连接器 slug，由服务端绑定当前登录用户。地址、认证及风险策略来自部署清单。
- 发现接口在既有 15 秒上游期限内返回，使用短期发现操作和独立凭据读取边界。浏览器无需轮询。重复提交依赖连接唯一性和 revision 检查，响应丢失时应先 GET 当前状态。
- 密钥轮换支持密钥环和逐连接重新封装。新连接和刷新后重新授权的连接使用当前 active key。

| 当前代码 | 当前行为 | 本次改动 |
| --- | --- | --- |
| `services/backend/internal/control/mcp.go` | `enabledTools(tx)` 读取全局连接，普通目录不传用户身份 | 改成按身份、连接作用域、授权版本筛选；普通目录与快照共用解析器 |
| `control/capabilities.go` | 所有全局启用工具进入 Snapshot | 增加用户连接绑定、授权摘要和 Skill 依赖；快照不含秘密 |
| `control/execution.go` | 校验配置 revision、部署准入、Run 状态 | 校验连接 owner、grant、凭据版本与撤销；内部秘密解析复用同一权威校验 |
| `services/runtime/app/access.py` | endpoint 与 `credential_ref` 配对，凭据从环境变量读取 | 分离目标准入与凭据来源；增加受控个人连接传输入口 |
| `runtime/app/tool_execution.py`、`tool_worker.py` | Gateway 审批后调用受限子进程 | 复用生命周期；只在执行阶段取个人秘密、最小环境启动 worker、清洗返回 |
| `runtime/app/harness.py`、`approvals.py` | DeepAgents、HITL、快照撤权检查 | 沿用；审批绑定增加连接/授权/凭据版本，不向模型传秘密 |
| `apps/web/src/control.tsx`、`chat.tsx` | 管理员工具开关、用户能力目录 | 连接卡、授权弹窗、连接状态、缺失依赖提示、友好工具名称 |
| `schemas/` 与生成器 | Go/Python/TS 共享契约 | 先改契约及样例，再生成消费类型 |

当前基线迁移为 007。实施前再次检查迁移编号和本地已有改动，下一迁移暂称 008，不覆盖用户工作树。正式 5173 的真实 DeepSeek + 麦当劳时间查询已通过，但 Langfuse 重建后未持续配置、模型调用窗口仅余有限次数；不能把历史通过当作本轮新代码验收。

## 2. 概念与职责

### 2.1 两类连接与三种凭据来源

- 平台连接：管理员配置，按平台发布范围提供；可使用部署凭据或无凭据。
- 个人连接：由当前用户授权，凭据、工具目录、授权记录属于该用户。
- `credential_source`：`deployment_ref / user_secret / none`。不开放通过普通 PATCH 直接修改 owner/scope/source。

麦当劳连接器由平台预置，但麦当劳账户属于用户。DeepSeek/Tavily 继续使用平台配置。内置文档/沙箱不是 MCP，不为了统一页面而伪造 MCP 连接。

Skill 是方法和模板，Tool 是执行能力，Connection 是凭据与授权绑定。Skill 的发布者不决定其工具身份：平台 Skill 可以同时依赖平台搜索和个人麦当劳连接。

### 2.2 模块职责

| 模块 | 权威职责 |
| --- | --- |
| Backend connectors | 定义、连接所有权、用户授权、有效工具、版本、断开与审计 |
| Backend credentials | 加解密与凭据版本；仅 Backend 持有个人凭据主密钥 |
| Runtime Tool Gateway | 审批、参数/目标复核、执行记录、即时取凭据、短期传输、清洗和 canonical events |
| MCP worker | 只持有本次连接需要的凭据与参数，完成协议调用后退出 |
| DeepAgents | 消费安全工具定义，规划与调用；不读取凭据库 |
| Web | 输入 Token、授权与操作确认；不在 localStorage/sessionStorage 保存 Token |

不增加独立服务。Go 包和 Python 模块可按职责拆分，不能形成另一个控制面或另一个 Agent loop。

## 3. 用户流程

### 3.1 连接麦当劳

1. “能力设置”中的麦当劳卡片显示“需要连接”，说明用途及 Token 获取入口。
2. 用户输入 Token 并点击“验证并发现能力”。界面提前说明 Token 将保存在当前部署并用于访问固定麦当劳服务；此步只执行 initialize/tools/list，不执行业务工具。
3. Backend 创建用户私有 pending 连接，加密保存候选 Token；Runtime 完成发现，返回有效工具、需确认工具、不支持工具的分类摘要。发现按用户进行，不能拿管理员 Token 的目录替代用户目录。
4. 弹窗默认选择“授权当前兼容能力”：列出公共查询、个人数据查询、操作执行范围；工具明细可展开。用户可选“仅查询”。不强制操作 36 个开关。
5. 用户点击“连接并授权”，提交期望的连接 revision、发现清单 hash 和授权模式；Backend 事务生成 grant、更新有效工具投影。
6. 连接变为 ready，工具在下一次 Run 的快照中生效。取消弹窗会撤销 pending 凭据；未确认 pending 连接 30 分钟失效，由已有进程内清理机制处理。

个人数据查询的权限可以在首次连接弹窗集中说明并确认，不默认增加“每类再弹一次”的重复流程。仅查询模式不代表匿名查询，仍须说明会读取个人账户数据。

### 3.2 对话与能力选择

- 只有一个已连接麦当劳账户时，“查麦当劳活动”直接使用它。
- 用户没有连接且明确选择该卡片/依赖该连接的 Skill 时，提交前提示“连接麦当劳”；连接完成保留草稿，用户点击发送，不自动产生额外模型调用。
- 自由聊天提到未连接服务时，系统可向模型提供安全的连接状态摘要，最终回答展示连接入口；不能假装有工具。模型不负责授权。
- 默认包含平台可用工具及用户启用的个人连接；提供每轮连接选择以限制上下文。第一版不引入工具搜索 Agent；超出上下文预算要提示缩小连接选择，不能默默丢掉工具后声称全部可用。
- 连接授权不受“允许公开网页/搜索”开关替代；公开联网开关继续仅控制 fetch/search。

### 3.3 写操作

可用意味着模型能发起提议。订单、地址、领券、积分兑换等写操作沿用 HITL；卡片展示应用名、操作名、具体参数和必要的账户标识摘要。涉及金额/积分应突出数值，不能靠截断参数隐去关键信息。批准绑定确定参数；模型修改参数必须重新批准。

未知风险工具默认每次确认，不自动按 `query-` 等名称降为只读。平台明确禁止或 schema 不支持的工具不发给模型，页面解释原因。工具返回“已创建订单”不证明支付成功；不把付款链接当作授权自动支付。

## 4. 数据模型

字段方案先进入 JSON Schema/OpenAPI；涉及唯一性、所有权和版本的字段使用实际列和约束，不能只靠 JSONB 中的可编辑字段。

| 数据结构 | 关键内容与约束 |
| --- | --- |
| 新 `backend.connector_definitions` | 稳定 `id/slug`，名称、说明、固定 target_id、transport、auth_type、允许 scope、enabled、policy_revision、工具风险策略；无 Token；仅管理员修改。首个 `mcd-cn` 为 user scope |
| 扩展 `backend.mcp_connections` | 保留现有 ID/data；增加 definition_id（legacy 可空）、scope、owner_id、credential_source、credential_id、revision、credential_version、grant_revision、status。CHECK：user 必须 owner，platform 不得用 user_secret；同用户/definition 最多一个非撤销实例 |
| 新 `backend.connection_credentials` | credential_id、connection_id、密文、nonce、key_id、version、candidate/active、created_at；唯一约束防重复 active 版本，允许短期 candidate；关联连接 owner；对外不提供解密读取 API |
| 新 `backend.connection_grants` | connection_id、owner_id、grant_revision、权限模式、catalog_hash、逐工具 fingerprint/许可、consented_at、revoked_at；grant 是用户同意的事实 |
| 新 `backend.connection_access_operations` | 有界 discovery operation 与 execution 凭据发放绑定；包含 owner、run/snapshot 或 discovery 目的、连接/版本、execution、参数 hash、过期时间；只记录授权发放事实，不复制 Runtime 执行结果 |
| 扩展 `backend.mcp_tools` | 保留 namespaced ID、connection_id、remote_name；增加 tool_fingerprint、risk_source、invocation_policy、catalog_revision、变化状态；每个连接有自己的发现数据 |
| 扩展 Skill 契约 | dependencies：`kind`、稳定 capability/connector ID、必需/可选、允许的 capability groups；旧 Skill 缺省为空 |
| 审计 | 扩展既有安全审计记录支持用户连接动作；仅记录 actor、连接/版本、操作和稳定原因码，不记录 Token、密文或私有工具响应 |

连接状态：`pending / ready / auth_required / unavailable / disabled / revoked`。增量变化另用 `pending_changes` 表示，避免新增一个工具就让整个连接失效。ready 只代表最近发现/认证成功，不保证下一次业务调用必然成功。

`grant` 与管理员禁用共同决定有效权限；旧 `enabled` 可作为兼容投影，不作为新的第二份用户授权真相。个人模式不能通过旧 admin tool PATCH 绕过 grant。

两个版本独立变化：修改凭据递增 credential_version；用户授权变化递增 grant_revision；会影响执行的配置递增 connection revision。乐观锁冲突返回 409，禁止后写覆盖。

## 5. 凭据与执行链

### 5.1 静态保护

- 使用 Go 标准库 AES-256-GCM 加密个人 Token，nonce 随机且每次加密更新。
- AAD 绑定 connection_id、owner_id、definition_id、credential version；移动密文到另一账户会解密失败。
- 主密钥仅注入 Backend，配置 `CONNECTION_SECRET_ACTIVE_KEY_ID` 和密钥环；实际值保存在被忽略的部署 secret 配置中，不放业务库或镜像。启动不可临时生成主密钥，否则重启无法解密。
- 支持旧 key_id 解密、新 key_id 写入的轮换入口；迁移完全部密文且确认可恢复后才退役旧 Key。丢失主密钥会需要用户重新连接，不能承诺从密文恢复。
- 缺主密钥时，只禁用新个人连接及个人凭据调用，平台模型/搜索继续按已有配置工作；页面给出部署未配置原因。
- 公网部署使用 HTTPS；本地仅 loopback 的 HTTP 可以作为开发模式。Token 不在 URL、进程命令行、浏览器持久存储或通用请求日志中出现。

### 5.2 一条请求：查麦当劳活动

1. Web POST Run，身份来自登录态，客户端不能自报 owner。
2. Backend 解析平台能力与当前用户个人连接，冻结 connection/grant/credential/catalog 版本；快照只含引用、安全元数据和工具定义。
3. Runtime/DeepAgents 得到 `campaign-calendar` 等已授权工具，生成调用参数。
4. Gateway 校验工具、参数、Run 状态；需要审批则先暂停，恢复后重新校验所有版本。
5. 创建 execution 记录，在开始外部请求前向 Backend 请求该 execution 的凭据材料。
6. Backend 以自己持有的 Run submission、快照和审批记录作为权威，验证当前 owner、连接状态、授权版本、工具 fingerprint、参数 hash、execution ID 和必要审批；事务登记该 execution 的授权发放绑定，通过后只在受保护的内部响应返回凭据。不可只凭传入 `user_id/credential_id` 读取，不直接跨 schema 查询 Runtime 的 execution 表。同 execution 的不同参数或连接请求必须拒绝，授权发放记录不承担工具是否已执行的事实。
7. Runtime executor 在调用局部变量中接收凭据，经 stdin/匿名管道交给本次 worker；子进程只得到单个 Token 与最小系统环境，不继承 DeepSeek/Tavily/Langfuse 等其他秘密。worker 不获得主密钥。
8. worker 向固定 MCP endpoint 发起请求；禁止凭据跨重定向发送。凭据清洗后才返回工具结果，再生成 canonical event、checkpoint、模型上下文和 Langfuse 观测。
9. DeepSeek 基于真实工具结果生成最终回答，前端聚合展示。

新增内部凭据接口属于秘密传输例外：仅 Runtime 服务认证可访问、`Cache-Control: no-store`、关闭请求/响应 body 日志、限制大小/超时。外部 Nginx 不暴露 `/internal`。单机继续使用现有私有 Docker 网络与服务认证；跨主机部署需要 TLS。不能声称“所有 API 都永远不传秘密”，应准确限定“公开 API 不回显，内部执行边界按需短暂传输”。

凭据不得放进 LangChain tool args、RunnableConfig、callback metadata、Start/Snapshot 或状态对象。Python 无法保证内存安全擦除，采用最小生命周期、无持久缓存、无异常值输出与子进程退出降低暴露面。

### 5.3 发现专用通路

没有 Run 的连接测试不能调用 execution 凭据接口。Backend 先为当前用户建立短期 discovery_operation，绑定 pending/现有连接、credential version、目标和到期时间；Runtime 仅可为该 operation 获取凭据并执行 initialize/tools/list。业务 tools/call 明确禁止。重复 operation 不增加权限，过期/取消均不可获取凭据。

### 5.4 脱敏不再只依赖环境变量

当前 `safe_text` 主要从进程环境提取秘密，新增个人 Token 不在环境中，因此必须增加执行局部清洗：已知秘密字面值、Authorization/Bearer、敏感结构字段及错误响应统一处理。清洗在 worker 输出、异常映射之前执行；授权目录 description/schema 中若含 Token 也在持久化之前清洗或拒绝。Langfuse 不包裹凭据获取过程，不采集原始 Token 输入。错误 Token 上游 401 映射 `CONNECTION_AUTH_REQUIRED`，服务原文不直接透传。

## 6. 工具授权与服务更新

| 工具状态 | 批量连接后的策略 |
| --- | --- |
| 经过平台维护策略确认的普通/个人查询 | 用户连接时同意相关数据范围后直接执行 |
| 已确认写操作 | 全能力模式可见，逐次审批；仅查询模式不开放 |
| 兼容但未知风险 | 全能力模式中按每次确认执行，提示风险未核实；仅查询模式不开放 |
| 明确禁用、不兼容 schema、重复名称、超限响应 | 保持不可执行，展示具体原因 |
| 连接后新增/参数或说明显著变化 | 等待增量授权，旧的未变化工具仍可用 |

风险策略存于 Backend 版本化 connector policy；`deploy/targets.json` 保留精确网络目标约束及 legacy 平台工具规则。新个人连接不同时让 JSON 清单和数据库各自维护两套有效授权。Runtime 使用 Backend 下发的受信策略及实时校验，再独立核验固定目标；远端 annotations 只是参考信息。

fingerprint 至少覆盖 remote name、输入/输出 schema、description、annotations 和平台策略版本（规范化编码后 hash）。同名不同连接用 namespaced ID 隔离，同连接重复名字拒绝本次目录，保留上次有效目录并标记发现失败。

刷新目录不自动批准新增项；用户一次确认变化集合。移除工具立即停止执行，改参数的旧审批作废。远端在发现与调用之间静默变更语义无法完全侦测，不能承诺“全部工具零风险”；未知写结果维持 UNKNOWN，不自动重试。

换 Token：验证候选凭据期间旧连接可保持可用；候选成功后以明确确认事务切换，递增凭据/授权相关版本，重新对照发现范围。失败保留旧有效配置，不把失败候选 Token 变成当前凭据。

断开：原子撤销 grant、停用连接、删除数据库中的有效密文，后续取凭据失败；尽力取消已启动调用但不声称能撤销已经提交到远端的动作。清除本地凭据不会吊销麦当劳服务器的 Token，界面提供去服务方撤销的说明。保留无秘密的历史审计；已有数据库备份中的密文不保证立即物理消失。

## 7. 契约与接口草案

公开 DTO 与秘密写入 DTO 分开，`token` 标为 writeOnly，不回显也不提供“查看完整 Token”。所有 /me 请求取登录用户，越权统一 404。mutation 带 `expected_revision`，连接创建/确认支持 Idempotency-Key。安全样例只用明显虚构值。

| 接口 | 用途 |
| --- | --- |
| GET `/api/catalog/connectors` | 平台定义 + 当前用户连接摘要，安全字段 |
| GET `/api/me/connections`、`/:id`、`/:id/tools` | 个人状态、授权范围和工具原因 |
| POST `/api/me/connections` | definition_id + Token，创建 pending；不接受任意 endpoint/Header |
| POST `/api/me/connections/:id/probe` | 发现/刷新；返回 operation 和状态；长任务前端轮询，无额外队列服务 |
| GET `/api/me/connections/:id/operations/:operation_id` | 有界连接操作结果，严格 owner 检查 |
| PUT `/api/me/connections/:id/grant` | 当前清单 hash + 模式 + 版本，一次授权或增量授权 |
| PUT `/api/me/connections/:id/credential` | 候选 Token 验证入口，不立即覆盖当前凭据；grant 确认激活候选版本 |
| PATCH `/api/me/connections/:id` | 用户标签/启停；owner/source/endpoint 不可写 |
| DELETE `/api/me/connections/:id` | 撤销连接与有效秘密，幂等；保留历史安全元数据 |
| GET/POST/PATCH `/api/admin/connector-definitions` | 管理名称、固定准入目标绑定、发布与策略；不能新增部署未允许的目标 |
| 既有 `/api/admin/mcp-connections` | 管理平台连接；禁止由此读取个人 Token 或把个人连接变成共享连接 |
| 既有 `/api/catalog/tools`、`/api/capabilities/resolve` | 用户可见工具与缺失依赖结果，统一 resolver |
| POST `/internal/connection-execution-material` | execution 绑定的即时秘密读取，仅 Gateway 内部消费 |
| POST `/internal/connection-discovery-material` | operation 绑定的发现凭据，仅 initialize/tools/list |

新增契约：ConnectorDefinition、PersonalConnection、ConnectionOperation、ConnectionGrant、ConnectionWrite、CredentialReplace、ToolAvailability、SkillDependency、CapabilityRequirement、ExecutionMaterialRequest/Response、DiscoveryMaterialRequest/Response。

扩展 Snapshot/Start：schema_version、可见 connection 引用/版本、grant revision、tool fingerprint/invocation_policy；保留旧字段解码兼容。不把密文、Key ID 详情或内部秘密接口响应混入 Snapshot。

错误码至少包括：`CONNECTION_REQUIRED`、`CONNECTION_AUTH_REQUIRED`、`CONNECTION_UNAVAILABLE`、`CONNECTION_REVOKED`、`CONNECTION_SECRET_UNAVAILABLE`、`CONNECTION_GRANT_REQUIRED`、`CONNECTION_CATALOG_CHANGED`、`CONNECTION_REVISION_CONFLICT`、`TOOL_UNSUPPORTED`、`SKILL_DEPENDENCY_MISSING`。继续复用 `APPROVAL_REQUIRED/CONFLICT`、`TOOL_TIMEOUT`、`OUTCOME_UNKNOWN`。前端把稳定码映射为连接、更换 Token、查看变化、稍后重试等动作。

## 8. Skill 依赖与体验

- 管理员发布 Skill 时声明必需/可选能力，不填写任何个人连接 ID 或 Token。
- 平台依赖指向稳定 builtin/capability ID；个人依赖指向 connector definition 和能力组，执行时解析当前用户连接。
- 所有必需依赖在创建 Run 之前检查；可选依赖缺失进入安全元数据，指导模型明确不包含该部分，不能捏造完成。
- 第一版只做依赖解析，不自动安装新 Skill/连接器，不引入子 Agent 或通用流程引擎。
- “麦当劳助手 Skill”可选；不安装该 Skill 仍能通过普通对话使用已连接 MCP。
- 平台 Skill 更新涉及新增个人依赖时，用户需要连接/授权后才能使用相关部分；发布者不能替用户授权。

Web 保留能力设置入口，内部用“平台提供”“我的连接”“技能”组织内容；管理员保留配置入口。个人连接卡显示连接状态、工具数量、需确认数量和不可用原因；工具执行卡显示“麦当劳 · 查询活动日历”，技术 ID 放详情。用户草稿和连接弹窗不因普通状态刷新丢失。

## 9. 迁移、部署与撤回

1. 先冻结契约；运行中的旧 Run 排空后再切换权限语义，不能在线重写旧 Snapshot/检查点。
2. 采用扩展迁移，为既有 MCP 填 `scope=platform`，保留 ID、历史工具/运行/文件关系。
3. **例外处理已有麦当劳共享 Token**：根据预置 personal definition 识别并从普通用户目录/新快照移除，标记 legacy 仅供管理员迁移查看；不能把该 Token 自动复制给每个用户，也不猜测它属于 user-a。用户亲自连接后才恢复个人能力。
4. 增加独立 personal-connections feature flag；关闭时隐藏个人入口并拒绝个人执行，不能回退为共享麦当劳。平台模型、搜索和公共 MCP 保持运行。
5. 配置持久主密钥后启动 Backend，Runtime 支持新契约再切前端；不得因容器重建丢失解密能力。
6. 部署检查区分“配置存在”“实际调用成功”“观测入库成功”。修复 Langfuse Key 持久注入问题属于发布任务；不能临时注入后宣称重建安全。
7. 正式验收后才处理旧环境中的 MCD_MCP_TOKEN。旧值是否撤销由账户所有者决定，不自动撤销他人服务方凭据。
8. 撤回优先关闭个人连接功能并回滚到兼容扩展 schema 的代码；更早、不识别 scope 的二进制不能直接恢复，否则会把个人连接当全局连接。个人连接移到隔离/不可见状态并完成兼容检查后才允许旧版回退。不新增备份/回滚脚本、不删库或数据卷。

## 10. 边界与运维默认值

- Token 长度上限、格式检查与请求大小限制先在 Backend 执行；不把 Token 放在错误信息。
- 发现保留现有分页、100 工具/200KB 上限、12 秒 worker 与匹配的外层超时；如需调整必须带真实证据。
- 发现请求限流按用户和连接；业务限流按连接，平台共享连接计数共享、个人连接分别计数。重连不能借重复连接无界绕过用户总限额。
- 用户有多个连接时只注入被选中的完整授权工具集合；预算不足明确提示，后续再做按需工具发现。
- 已撤权但已发送到远端的调用可能完成；UI 可标记结果在撤销前已发出，不能保证远端撤销。
- 模型/搜索费用窗口沿用明确部署配置；本变更不默认提高额度，不把付费密钥有效性等同于授权无限调用。
- 资料、报告、查询结果仍按当前用户隔离；管理员提供平台 Key 不代表管理员可以在普通 UI 中读取用户私有连接的数据。
