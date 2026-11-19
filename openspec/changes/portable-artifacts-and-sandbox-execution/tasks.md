# Tasks：可移植产物存储、受治理工具执行与可替换沙箱

本清单按可独立交付任务组织，不绑定 Day、工期或人员。实现时按依赖关系推进；每个任务的实现状态和验证状态分开维护。

## Status Legend

- 实现状态：`未开始 / 实现中 / 代码齐备 / 需修复`
- 验证状态：`未执行 / 静态核对 / 运行通过 / 运行失败`
- 当前状态（2026-11-07）：全部任务为 `代码齐备 / 运行验收通过`。LocalFS、临时专用桶中的真实 MinIO、迁移 007、完整 Mock 业务回归与真实 Docker 沙箱已验证；正式 5173 当前使用 LocalFS。浏览器视觉与新增真实模型/搜索调用按边界未执行。
- 勾选表示该实现或验证入口已准备；不代表运行验收通过。证据见 `docs/evidence/<task-id>.md`。

## Dependency Graph

```text
CON-01
├─ ART-01 ─► ART-02 ─► DLV-01 ─┐
├─ TGW-01 ─► SBX-01 ───────────┼─► MIG-01 ─► UI-01 ─► ACC-01
└─ OPS-01 ──────────────────────┘
```

`ART-01` 与 `TGW-01` 在契约冻结后可以独立实现，但本仓库默认不主动启用子代理并行。

## CON-01：冻结共享契约与迁移边界

**依赖**：无。\
**输入**：现有 File、ArtifactWrite、BinaryArtifactMetadata、ToolResult、WorkFile 和 OpenAPI。\
**改动范围**：`schemas/openapi.yaml`、`schemas/jsonschema/contracts.json`、共享样例、Go/Python/TS 消费类型、数据库迁移草案。

任务：

- [x] 定义 Artifact、ArtifactRevision、ArtifactRevisionList、DownloadLocation 和 CandidateArtifact。
- [x] 明确 File 兼容字段与新增 `artifact_id/revision_id` 公开投影及仅内部使用的 `storage_provider`。
- [x] 定义内部发布请求的 execution/source/checksum/idempotency 字段。
- [x] 定义错误码：`STORAGE_UNAVAILABLE`、`ARTIFACT_NOT_READY`、`FILE_INTEGRITY_ERROR`、`ARTIFACT_CONFLICT`。
- [x] 增加产物、revision、候选输出、存储失败和下载定位样例；重试与冲突在验收入口中表达。
- [x] 列出所有现有调用方，确认接口变更顺序为 schema → Backend/Runtime → Web。

**完成结果**：跨语言字段、状态和错误语义唯一，后续任务不再各自发明模型。\
**失败边界**：不能删除旧 File 字段；不能把 URL、凭据或宿主路径放进共享事件。\
**验收**：schema 校验入口准备完毕；生成副本无手工漂移。\
**证据文件**：`docs/evidence/CON-01.md`。

## ART-01：实现 BlobStore 与 MinIO 驱动

**依赖**：CON-01。\
**输入**：当前 `fileRoot()` 本地存储、本机 MinIO Endpoint/Bucket/专用凭据。\
**改动范围**：Go Backend storage 内部包、配置、启动检查、`.env.example` 和部署文档。

任务：

- [x] 提取 `LocalFilesystemBlobStore`，保持现有原子写入和 hash 校验。
- [x] 使用 Go S3 SDK 实现 Put/Get/Head/Delete/PresignGet 公共子集。
- [x] 分离 internal endpoint 与 public endpoint；MinIO 开启 path-style。
- [x] 支持独立 Bucket 和最小权限凭据配置，不自动创建管理员资源（本机实例尚待配置）。
- [x] 限制 key、大小、媒体类型、超时和并发；日志去除签名查询参数。
- [x] 配置缺失或 MinIO 不可达时返回明确错误，不静默切换 provider。

**完成结果**：Backend 可以按配置把新对象写到 LocalFS 或 MinIO，并从行级 provider 读取。\
**失败边界**：MinIO 故障不能影响旧 local 对象读取；不能把 AccessKey 提交到仓库。\
**验收**：准备同一字节在两种 provider 上的写入、Head、读取、删除和完整性验证入口。\
**证据文件**：`docs/evidence/ART-01.md`。

## ART-02：建立产物与不可变 revision

**依赖**：CON-01、ART-01。\
**输入**：现有 `backend.files`、`parent_file_id/version`、run/thread/execution 来源。\
**改动范围**：Backend migration、agententry/workspace 文件逻辑、内部 artifact publish API。

任务：

- [x] 增加 files 存储 provider/status/完整性查询字段或等价规范化结构。
- [x] 增加 artifacts 和 artifact_revisions，建立唯一约束和来源关系。
- [x] 实现 PENDING → READY，失败事务回滚不可见并保留独立清理意图；不发布虚假 READY。
- [x] 使用不可变 object key，禁止覆盖已有 revision。
- [x] 实现同一 execution/artifact key 的幂等发布和冲突检查。
- [x] 保留 File API 兼容投影，并让已有报告版本可映射到新 lineage。

**完成结果**：逻辑产物和字节版本分离，指定版本可定位、下载和继续加工。\
**失败边界**：任何对象/元数据一侧失败都不能产生虚假 READY；不能删除旧版本字节。\
**验收**：准备首版、派生版、并发冲突、对象失败、数据库失败和幂等重试入口。\
**证据文件**：`docs/evidence/ART-02.md`。

## DLV-01：实现私有下载与临时地址

**依赖**：ART-01、ART-02。\
**输入**：现有 `/api/files/{id}/download` 与 Web 下载行为。\
**改动范围**：Backend 下载 handler、OpenAPI、Web 下载适配和安全响应头。

任务：

- [x] 保持原下载入口先做 owner/status 鉴权。
- [x] LocalFS 模式继续安全流式返回。
- [x] MinIO 模式生成短期预签名 GET，并支持浏览器可访问的 public endpoint。
- [x] 清洗下载文件名并设置受控 Content-Disposition/Content-Type。
- [x] 禁止签名 URL 持久化、进入事件、Langfuse 或普通日志。
- [x] 每次下载重新鉴权签名，为对象缺失和存储错误提供 UI 提示；跨域直链的过期/连接错误由浏览器显示，用户可重新点击下载。

**完成结果**：本地和 MinIO 使用同一产品下载入口；MinIO 文件不经过 Backend 整体搬运。\
**失败边界**：未授权用户不能获得 URL；签名 URL 过期后必须重新鉴权生成。\
**验收**：准备授权、越权、过期、中文文件名、internal hostname 泄漏和 local 回退验证入口。\
**证据文件**：`docs/evidence/DLV-01.md`。

## TGW-01：重构进程内 Tool Gateway

**依赖**：CON-01。\
**输入**：现有 `ToolGatewayService`、builtin/MCP/compute 分支、审批与 canonical events。\
**改动范围**：Python Runtime 内部模块，不新增部署服务。

任务：

- [x] 提取 ToolRegistry、PolicyEngine、ExecutionLifecycle、ExecutionRouter、executors 和 ArtifactCollector。
- [x] 保留统一 façade，DeepAgent 不感知具体 executor。
- [x] 将 schema、作用域、审批、预算、幂等检查固定在 dispatch 之前。
- [x] 统一 executor result，候选文件不能直接成为正式 File。
- [x] 保留取消、故障注入、UNKNOWN 和 canonical event 顺序。
- [x] 确认 Langfuse 仍展示一个真实工具调用节点，不因内部模块拆分制造虚假 Agent 步骤。

**完成结果**：builtin、MCP 和 sandbox 工具共享同一治理主干，内部职责可独立替换。\
**失败边界**：不能在重构中改变审批、幂等或事件外部语义；不能增加第二个 Agent loop。\
**验收**：准备原有成功、审批恢复、取消、重复提交、MCP 故障和 UNKNOWN 回归入口。\
**证据文件**：`docs/evidence/TGW-01.md`。

## SBX-01：适配 Local Docker SandboxExecutor

**依赖**：TGW-01、ART-02。\
**输入**：现有 Compute Broker API、Docker runner、授权输入和 compute 输出。\
**改动范围**：Runtime sandbox adapter、Compute Broker 契约兼容、输出 manifest。

任务：

- [x] 定义 SandboxExecutor、SandboxTask、SandboxResult 和 SandboxOutput。
- [x] 将现有 Compute Broker 包装为 LocalDockerExecutor，不重写容器实现。
- [x] 显式传递资源限制、超时、取消和输出清单。
- [x] 输入只来自当前 run 授权文件；沙箱不挂载 Backend/MinIO 数据目录。
- [x] 环境变量使用白名单，检查模型、搜索、数据库、存储和观测密钥均不可见。
- [x] 校验输出路径、符号链接、类型、大小和 hash 后交给 Artifact Collector。

**完成结果**：当前 Docker 执行通过统一 executor 使用，未来增加云 adapter 不改变 Tool Gateway 和产物模型。\
**失败边界**：容器终态不明返回 UNKNOWN；取消后的候选输出不得发布。\
**验收**：准备成功执行、禁网、超时、取消、路径逃逸、超限输出、密钥缺失和 broker 离线入口。\
**证据文件**：`docs/evidence/SBX-01.md`。

## OPS-01：配置、安全与运行文档

**依赖**：CON-01。\
**输入**：现有 Compose、环境变量样例和本机 MinIO。\
**改动范围**：`.env.example`、README/ARCHITECTURE、Compose 配置透传和运维说明。

任务：

- [x] 记录 LocalFS/MinIO 两种部署方式和切换边界。
- [x] 提供独立 Bucket、最小权限用户、CORS、HTTPS 和生命周期建议。
- [x] 说明 internal/public endpoint 以及浏览器签名主机要求。
- [x] 说明 MinIO 单节点不等于备份，正式个人资料需另行设计备份/复制。
- [x] 不把 MinIO 添加为默认常驻服务；需要可复现 fixture 时使用可选 profile。
- [x] 增加秘密扫描清单，确保凭据不进入代码、Git、事件或 evidence。

**完成结果**：开发者能连接已有 MinIO，默认部署没有隐藏的新常驻依赖。\
**失败边界**：文档不能声称 MinIO 免费等于零成本或单节点等于高可用。\
**验收**：静态核对配置样例、秘密占位符和默认 Compose 服务清单。\
**证据文件**：`docs/evidence/OPS-01.md`。

## MIG-01：非破坏性迁移与兼容读取

**依赖**：ART-02、DLV-01、TGW-01、SBX-01、OPS-01。\
**输入**：当前 local 文件、已有版本链和既有 API 消费方。\
**改动范围**：数据库 migration/backfill、兼容读取、迁移脚本和回退说明。

任务：

- [x] 旧 files 行回填 `storage_provider=local`，不移动字节。
- [x] 对明确的 parent/version 链做幂等 artifact backfill。
- [x] 无法确定 lineage 的文件保留为独立 artifact，不猜测合并。
- [x] 新旧 API 在迁移窗口并存，旧 Web 不因新增字段失效。
- [x] 提供 orphan/PENDING 检查和清理入口，但不自动删除当前演示数据。
- [x] 回退保留新表/字段，并确保行级 provider 仍可读取。

**完成结果**：升级不要求备份虚假演示数据，也不通过破坏性操作换取简单实现。\
**失败边界**：不能批量修改 provider 而不复制对象；不能 DROP 旧列/表。\
**验收**：准备空库、当前演示库、重复 migration、部分失败和回退读取入口。\
**证据文件**：`docs/evidence/MIG-01.md`。

## UI-01：产物版本与下载状态界面

**依赖**：MIG-01。\
**输入**：资料库、聊天产物卡片、版本列表和下载入口。\
**改动范围**：Web，不改变视觉主框架。

任务：

- [x] 展示逻辑产物、当前版本、版本号、来源会话和生成时间。
- [x] 允许选择历史 revision 下载或继续加工。
- [x] 下载统一请求 Backend，不在前端缓存长期 URL。
- [x] 显示产物状态、对象缺失和存储不可用提示，每次下载获取新地址。
- [x] 不向用户暴露 provider、bucket、object key、内部 endpoint 或执行容器路径。

**完成结果**：用户看到的是产物及版本，而不是底层文件系统或对象存储实现。\
**失败边界**：失败版本不能显示为可下载 READY；版本选择不能静默切换到最新版本。\
**验收**：准备桌面宽屏和窄屏的正常/失败静态状态；浏览器操作需用户另行授权。\
**证据文件**：`docs/evidence/UI-01.md`。

## ACC-01：整体验收与问题修复

**依赖**：所有前置任务代码齐备。\
**输入**：本变更三个 delta specs 和各任务验证入口。\
**改动范围**：验收脚本、证据、发现问题的局部修复；不扩展新功能。

任务：

- [x] 静态检查 schema、调用方、秘密、Compose 服务和迁移顺序。
- [x] 经用户授权后验证 LocalFS 与真实 MinIO 上传、版本、下载和失败恢复。
- [x] 经用户授权后验证真实 Docker 沙箱成功、取消、超时、禁网和输出发布。
- [x] 回归 builtin、MCP、审批、幂等、事件回放、资料库和旧文件下载。
- [x] 浏览器视觉与新增真实模型/搜索调用未纳入本轮，未执行状态已记录，真实调用均为 0。
- [x] 修复 S3 不可达连接缺少超时及验收客户端跨源转发 Bearer 的问题，并逐项更新状态。

**完成结果**：三个 capability 的每个 Scenario 都有对应证据或明确未执行原因。\
**失败边界**：静态核对不能写成运行通过；Mock 不能冒充真实 MinIO/Docker/模型验收。\
**验收**：形成 `docs/evidence/ACC-01.md` 汇总并链接各任务证据。\
**证据文件**：`docs/evidence/ACC-01.md`。

## Completion Gate

变更只有在以下条件全部满足时才能从 `PROPOSED` 改为完成：

- [x] 三个 capability 的 requirement 均已实现。
- [x] 所有任务实现状态为代码齐备，或明确从范围移除并更新 proposal/spec。
- [x] 数据迁移无破坏性删除，旧 local 文件仍可读取。
- [x] MinIO、Docker、审批、MCP 和下载的实际验证状态如实记录。
- [x] Git 中不存在真实 AccessKey、签名 URL、模型 Key 或搜索 Key。
- [x] 默认部署未新增独立 Tool Gateway、Artifact Service 或常驻 MinIO。
