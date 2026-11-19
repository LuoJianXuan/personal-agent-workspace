# Design：可移植产物存储、受治理工具执行与可替换沙箱

## Context

本设计面向独立 Personal Agent，不复制公司灵机 AI 的企业多租户部署拓扑。它保留 Web、Go Backend、Python Runtime 和可选 Compute Broker 的现有职责，将可变基础设施放到接口之后，并把长期业务真相留在 Backend/PostgreSQL。

本设计只冻结本次变更的目标状态。文件名、函数名和 SQL 可在实现时依据现有代码局部调整，但不能改变 delta specs 中的外部行为和安全边界。

## Goals

- 复用本机 MinIO，移除产物对 Backend 本地卷的强耦合。
- 建立稳定 artifact identity 与不可变 revision，支撑跨会话继续加工。
- 让 Local Docker 和未来云沙箱共享执行契约。
- 让所有工具继续经过同一治理入口。
- 不新增常驻业务微服务，不给个人项目引入企业平台复杂度。

## Non-Goals

- 不把 DeepAgents 替换为自研循环。
- 不实现云沙箱供应商 adapter。
- 不实现永久公开发布、匿名链接或 CDN。
- 不承诺 MinIO 单节点具备云对象存储同等级别的高可用和灾备。
- 不在本次改动中处理复杂 Office 协同编辑。

## Three Key Decisions

### D1：Tool Gateway 保持进程内，但拆清职责

Tool Gateway 是 Runtime 内的唯一工具准入边界。它不是普通工具函数集合，也暂时不独立部署。重构只拆内部模块，避免在一个 `execute()` 内同时处理注册、策略、审批、执行、重试、事件和产物发布。

目标内部结构：

```text
ToolGateway
├─ ToolRegistry          工具定义、schema、版本、风险和 executor 类型
├─ PolicyEngine          作用域、审批、预算、网络和文件授权
├─ ExecutionLifecycle    execution_id、幂等、取消、超时和 UNKNOWN
├─ ExecutionRouter       builtin / MCP / sandbox
├─ Executors
│  ├─ BuiltinExecutor
│  ├─ McpExecutor
│  └─ SandboxToolExecutor
├─ ArtifactCollector     输出校验并交给 Backend 发布
└─ AuditEmitter          canonical events 与 Agent 级追踪
```

拆分后仍由一个 `ToolGatewayService` 或等价 façade 对 Agent 暴露入口，Agent 不直接获得 executor 引用。

### D2：采用 sandbox-as-tool，沙箱状态不作为业务真相

DeepAgent、模型调用、审批状态和 canonical events 留在 Runtime。沙箱只执行明确任务；输入是授权文件副本和规范化参数，输出是候选文件和有界文本。

首个 adapter 是现有 Compute Broker：

```text
SandboxExecutor
├─ create(execution context)
├─ upload(inputs)
├─ execute(command/code, limits)
├─ collect_outputs(manifest)
├─ cancel(execution_id)
└─ destroy()

LocalDockerExecutor -> existing Compute Broker HTTP API
```

本轮按 execution 创建短生命周期容器，不做 thread 级长期沙箱。后续若持续编码工作区产生实际需求，再增加 lease、pause/resume 和 snapshot；正式产物仍必须发布到 Artifact Service。

### D3：Backend 管产物真相，BlobStore 管不可变字节

Backend 管理 owner、artifact、revision、来源、状态和权限。BlobStore 只管理 key 对应的字节与对象元数据。

本轮支持：

```text
BlobStore
├─ LocalFilesystemBlobStore
└─ S3BlobStore -> MinIO
```

阿里云 OSS 是未来可选部署目标，不是本轮依赖。实现只依赖公共 BlobStore 行为，不能把 MinIO 管理 API 或 OSS 专属功能写进业务层。

## Target Architecture

```text
Web / future Desktop / future Mobile
                │
                ▼
Go Backend
├─ Auth / ownership
├─ Artifact metadata and revisions ─────► PostgreSQL
├─ BlobStore
│  ├─ LocalFS
│  └─ S3 client ────────────────────────► existing MinIO
└─ Authenticated download / presign
                ▲
                │ internal artifact publish
Python Runtime
├─ DeepAgents harness
└─ In-process governed Tool Gateway
   ├─ builtin / MCP
   └─ SandboxExecutor ──────────────────► optional Compute Broker
                                              │
                                              ▼
                                    short-lived Docker container
```

只有 Backend 持有 BlobStore 凭据。Runtime 通过现有内部鉴权 API 读取授权输入、发布输出；Compute Broker 和任务容器都不能读取 Backend、模型、Tavily 或 MinIO 长期凭据。

## Storage Design

### BlobStore contract

Go 接口的语义至少覆盖：

```go
type BlobStore interface {
    Put(ctx context.Context, key string, body io.Reader, meta PutMetadata) (StoredObject, error)
    Get(ctx context.Context, key string) (io.ReadCloser, ObjectMetadata, error)
    Head(ctx context.Context, key string) (ObjectMetadata, error)
    Delete(ctx context.Context, key string) error
    PresignGet(ctx context.Context, key string, opts DownloadOptions) (PresignedDownload, error)
}
```

约束：

- `Put` 必须接收预期大小与 SHA-256；驱动返回对象定位和可核对元数据。
- `Get`/`Head` 不包含业务授权，调用前由 Backend 完成 owner/revision 校验。
- `Delete` 只能用于明确的失败清理、回收站到期或孤儿清理，不能被普通版本切换调用。
- LocalFS 的 `PresignGet` 返回“不支持直签”，上层回退到 Backend 流式下载。
- S3 驱动使用内部 Endpoint 完成服务间上传读取，使用外部 Endpoint 生成浏览器可访问的签名。

### Configuration

计划配置项：

```env
BLOB_STORE_PROVIDER=local|s3
BLOB_LOCAL_ROOT=/data/files

S3_INTERNAL_ENDPOINT=http://minio:9000
S3_PUBLIC_ENDPOINT=http://localhost:9000
S3_REGION=us-east-1
S3_BUCKET=personal-agent
S3_ACCESS_KEY_ID=runtime-secret
S3_SECRET_ACCESS_KEY=runtime-secret
S3_FORCE_PATH_STYLE=true
S3_PRESIGN_TTL_SECONDS=600
```

- 示例文件只能出现占位值。
- 本地 Docker DNS 名称不能出现在浏览器下载地址。
- 生产公网 Endpoint 必须使用 HTTPS。
- Backend 启动时只检查配置格式和 Bucket 可访问性，不自动使用管理员凭据创建 Bucket/用户。
- MinIO 应使用独立 Bucket 和仅限该 Bucket 的专用凭据。

### Object keys

正式对象使用不可变 key：

```text
users/{owner_id}/revisions/{revision_id}/content
```

上传原件可继续以 file identity 保存，但 key 同样不可覆盖：

```text
users/{owner_id}/uploads/{file_id}/{safe_filename}
```

对象 key 不含原始完整路径、邮箱、模型提示词或其他敏感信息。物理 key 按不可变 revision 定位，artifact 归属由数据库管理。用户展示名称保存在数据库，下载时通过受控 `Content-Disposition` 返回。

## Artifact Domain Model

### Existing File compatibility

`backend.files` 继续代表一个不可变字节对象及其公开 File 投影。迁移增加或规范化：

- `storage_provider`：`local` 或 `s3`。
- `storage_key`：provider 内的不可变 key。
- `sha256`、`size`、`media_type`：可直接查询的完整性元数据；过渡期可从现有 JSON 投影回填。
- `status`：至少 `PENDING / READY / FAILED`。

旧行默认标记 `storage_provider=local`，继续从当前 `obj-{id}` 路径读取；不得在没有复制和核验的情况下把旧行改成 `s3`。

### New artifact lineage

建议新增：

```text
backend.artifacts
- id UUID PK
- owner_id UUID NOT NULL
- title TEXT NOT NULL
- logical_name TEXT NOT NULL
- current_revision_id UUID NULL
- created_at / updated_at

backend.artifact_revisions
- id UUID PK
- artifact_id UUID NOT NULL
- revision INTEGER NOT NULL
- parent_revision_id UUID NULL
- file_id UUID NOT NULL UNIQUE
- source_thread_id UUID NULL
- source_run_id UUID NULL
- source_execution_id UUID NULL
- note TEXT NULL
- status TEXT NOT NULL
- created_at
- UNIQUE(artifact_id, revision)
```

原则：

- `artifact_id` 是逻辑产物身份。
- `revision_id` 是不可变版本身份。
- `file_id` 指向不可变字节记录。
- 新版本创建新 revision 和新 object key，绝不覆盖旧对象。
- `current_revision_id` 只影响默认展示，不删除历史版本。
- MinIO Bucket Versioning 可以作为误删除保护，但不参与产品 revision 编号和来源关系。

## Publication Protocol

工具输出发布采用以下顺序：

1. Tool Gateway 根据工具声明和执行结果创建候选输出 manifest，包含安全文件名、媒体类型、大小、SHA-256 和来源 execution。Backend 在对象 I/O 前独立提交 key 的清理意图，覆盖进程崩溃窗口。
2. Backend 校验 owner、run、execution、artifact 目标和大小限制，创建 `PENDING` file/revision。
3. Backend 把字节写入临时或最终不可变 key。
4. Backend 使用 `Head` 或写入结果核对大小和 checksum。
5. 数据库事务将 file/revision 改为 `READY`，必要时推进 `current_revision_id`。
6. Backend 返回稳定 file/artifact/revision 标识；Runtime 产生 `artifact.published` 或现有兼容事件。

失败规则：

- 对象写入失败：revision 保持 `FAILED` 或回滚不可见，不能返回 READY。
- 对象成功、数据库提交失败：对象成为 orphan，由预先持久化的清理意图驱动延迟清理；清理前重新确认没有文件引用，不扫描共享 Bucket。
- 数据库 PENDING、对象缺失：读取返回明确 `ARTIFACT_NOT_READY` 或 `FILE_MISSING`，不能降级成空文件。
- 同一 idempotency key 重试：必须返回同一 READY 结果，或继续完成同一个 PENDING 记录，不能创建两个正式 revision。

## Download Design

保持兼容入口：

```text
GET /api/files/{file_id}/download
```

处理方式：

1. Backend 根据浏览器 JWT 校验 owner 和文件状态。
2. LocalFS provider：Backend 流式返回字节。
3. S3 provider：Backend 使用 public endpoint 生成 5–15 分钟 GET 签名，返回 302；如客户端明确请求 JSON，可返回包含 `url` 和 `expires_at` 的结构化定位。
4. 签名包含受控 Content-Disposition 和媒体类型；文件名必须清洗。

不在数据库、事件、日志或聊天上下文中长期保存预签名 URL。再次下载必须重新鉴权和签名。永久分享链接不在本变更范围。

## Tool Gateway Execution Model

统一请求：

```text
ToolExecutionRequest
- run_id / thread_id / owner_id
- tool_call_id / execution_id
- tool_name / tool_version
- canonical_args / args_hash
- authorized_file_refs
- governance snapshot
- approval / budget context
```

统一结果：

```text
ToolExecutionResult
- execution_id
- status: SUCCEEDED / FAILED / CANCELLED / UNKNOWN
- bounded_text
- candidate_artifacts[]
- safe_error
- usage / duration
```

处理顺序固定为：Registry resolve → schema validate → policy decision → approval binding → idempotency check → executor dispatch → cancellation/timeout → artifact collection → canonical event/audit。

未经 Artifact Collector 和 Backend 发布的沙箱路径不能出现在最终 File 列表中。executor 只返回候选输出，不生成业务 file/revision ID。

## Sandbox Security and Lifecycle

### Local Docker baseline

- 非 root 用户。
- 只读 root filesystem；单独临时工作目录。
- 默认禁网；本轮不提供由模型任意开启网络的参数。
- CPU、内存、进程数、磁盘、wall time 和输出大小限制。
- 固定允许的 runner 镜像，不接受模型指定任意 image。
- 输入文件以任务副本放入临时目录；修改副本不会回写原件，禁止挂载 Backend/MinIO 数据目录。
- 收集输出时拒绝绝对路径、父目录跳转、符号链接、设备文件和超限文件。
- 取消或超时必须终止真实容器并等待清理完成；无法确认终止时标记 UNKNOWN。

### Credential boundary

沙箱环境使用显式环境白名单，禁止注入：

- 模型 API Key；
- Tavily/搜索 Key；
- Backend/Runtime service token；
- PostgreSQL 连接信息；
- MinIO/OSS AccessKey；
- Langfuse Secret Key。

需要联网或认证的能力继续作为主服务侧工具，通过 Tool Gateway 单独治理，而不是让沙箱继承宿主环境。

## Migration and Compatibility

1. 先增加 schema 和 BlobStore，不改变旧行读取方式。
2. 将现有 `obj-{id}` 行标记为 `local`；新配置选择 `s3` 后，只有新对象写入 MinIO。
3. 新增 artifact lineage，对现有有 `parent_file_id/version` 的生成文件执行幂等 backfill；无法确定父链的文件保留为独立 artifact，不猜测合并。
4. File API、资料库列表和现有下载入口保持可用；新增 artifact/revision API 后前端逐步切换。
5. 不在本轮删除 `parent_file_id/version` 或旧本地字节；待所有读取方切换且另有变更提案后再清理。

这是一种非破坏性兼容迁移，不要求对当前演示数据制作备份，也不授权删除用户文件。

## Failure Semantics

| 故障 | 对外结果 | 不允许行为 |
| --- | --- | --- |
| MinIO 启动不可达 | 新发布明确 `STORAGE_UNAVAILABLE` | 静默改写 LocalFS |
| 上传中断 | PENDING 转 FAILED，可安全重试 | 返回 READY |
| checksum 不符 | `FILE_INTEGRITY_ERROR` 并隔离对象 | 继续提供下载 |
| public endpoint 配错 | 下载明确失败并记录安全错误 | 把 internal hostname 返回浏览器 |
| 审批缺失 | `APPROVAL_REQUIRED` | executor 先执行后补审批 |
| 工具取消 | 终止 executor，状态 CANCELLED | 继续发布取消后的输出 |
| 容器终态不明 | UNKNOWN，禁止自动重复有副作用动作 | 当作普通 FAILED 重试 |
| artifact metadata 提交失败 | 不产生可见 revision，清理 orphan | 只保留对象不留追踪 |

## Observability

- canonical events 继续记录 tool requested/running/completed/failed/cancelled 和 artifact published。
- Langfuse 继续只观察 Agent、模型和工具调用；BlobStore 的每次底层请求不扩展为全链路追踪。
- 日志允许记录 provider、bucket alias、key hash、大小、耗时和错误码；禁止记录 Secret、签名 URL 查询参数和完整用户内容。
- Backend 可增加轻量指标：上传/下载计数、字节数、失败数、孤儿清理数和 PENDING 超时数。

## Rollback

- 代码回退时保留新增表和字段，不做破坏性 DROP。
- 将 `BLOB_STORE_PROVIDER` 切回 local 只影响新写入；已有 s3 文件仍必须按行级 provider 可读，不能假设全局 provider。
- 若旧版本代码不能读取 s3 行，则发布前必须保留兼容读取路径或先停止切流；不能通过修改数据库 provider 假装字节已迁回本地。
- Tool Gateway 内部重构使用 façade 保持 Agent 调用入口，允许按模块回退而不改外部协议。

## Future Extraction Triggers

只有满足以下至少一项时，才另提案拆独立 Tool Gateway 或远程 Sandbox Service：

- 多个 Runtime 需要共享同一执行治理边界；
- 桌面 Local Executor 和云 Executor 需要跨网络统一调度；
- 沙箱资源池需要独立扩缩容和安全域；
- 多用户并发使执行资源明显影响 Runtime 延迟；
- 第三方客户端需要绕过 Runtime 直接使用受治理工具。

在这些条件出现前，模块边界优先于部署边界。
