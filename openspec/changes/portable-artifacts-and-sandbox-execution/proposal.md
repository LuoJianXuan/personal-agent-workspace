# Proposal：可移植产物存储、受治理工具执行与可替换沙箱

状态：`COMPLETED`。代码、迁移、LocalFS/真实 MinIO、完整 Mock 业务回归和真实 Docker 沙箱均已验收；正式 5173 已更新，当前默认存储为 LocalFS。浏览器视觉及新增真实模型/搜索调用未纳入本次验收。
变更 ID：`portable-artifacts-and-sandbox-execution`\
规划单位：任务，不绑定 Day 或固定工期。

## Why

当前 Personal Agent 已经具备 DeepAgents 主 Agent、Runtime 内逻辑 Tool Gateway、可选 Docker Compute Broker、文件上传下载和初步报告版本能力，但三个基础边界仍不完整：

1. 文件字节只保存在 Backend 本地目录或容器卷，尚无可替换对象存储接口；Web、未来桌面端和手机端无法依赖稳定的跨端存储与临时下载地址。
2. 产物版本通过 `parent_file_id + version` 和工作文件 revision 分散表达，缺少稳定产物身份、不可变 revision、来源 Run/工具执行和原始对象之间的统一关系。
3. 现有 Tool Gateway 与工具具体执行耦合较紧，Compute Broker 也没有统一 Sandbox Executor 契约；未来接入 MinIO、云沙箱、MCP 和桌面本地执行时容易在 Runtime 内继续堆积分支。

本变更要补齐这些边界，但保持 Personal Agent 的小核心原则：不新增独立 Tool Gateway 微服务，不强制引入 Kubernetes，不把 Agent 本身搬进沙箱，不把阿里云 OSS 或某个沙箱厂商写死为产品依赖。

## Current Facts

- `ToolGatewayService` 已在 Runtime 内处理工具准入、参数校验、审批绑定、幂等、取消和 canonical events；它是逻辑网关，不是缺失状态。
- Compute Broker 已能创建非 root、禁网、短生命周期 Docker 容器；它适合本地开发和单用户受限计算，但当前没有 provider-neutral executor。
- Backend `files` 表保存文件元数据，实际字节写入本地 `fileRoot()`；下载由 Backend 读取后返回。
- 既有 `/api/files/{id}/versions` 能读取部分报告版本链，但 `file_id` 同时承担内容对象和产品版本身份，无法完整支撑持续编辑。
- 用户本机已有 MinIO，可复用；本变更不要求再启动一套 MinIO，也不要求购买阿里云 OSS。

## What Changes

### 1. 产物与对象存储

- 在 Go Backend 中增加 provider-neutral `BlobStore`，首批支持 `local` 和 `s3`。
- `s3` 驱动以 MinIO 作为本轮实际目标；只使用 Put/Get/Head/Delete/PresignGet 等公共 S3 子集。
- 对象存储 Bucket 保持私有，Backend 是唯一持有存储凭据的应用服务。
- 新增稳定 `artifact` 和不可变 `artifact_revision` 概念；数据库是版本、来源和当前 revision 的权威源，对象存储只保存字节。
- 继续兼容当前 File API；不要求一次性重写所有文件消费方。
- 下载入口继续由 Backend 鉴权：本地存储由 Backend 流式返回，MinIO 返回短期预签名地址或 302；签名 URL 不持久化。

### 2. 进程内 Tool Gateway 重构

- 保留进程边界，将现有实现拆成 Registry、Policy、Lifecycle、Router、Executor 和 Artifact Collector 等内部职责。
- 所有 builtin、MCP 和 sandbox 工具都必须经过同一准入入口；executor 不能自行绕过审批、预算、作用域或审计。
- 工具执行保持现有 canonical events、幂等、取消和 UNKNOWN 语义，不通过重构削弱第一阶段能力。

### 3. 可替换沙箱执行

- 定义 `SandboxExecutor` 契约，把现有 Compute Broker 包装为 `LocalDockerExecutor`。
- 本轮继续使用“sandbox-as-tool”：Agent、模型密钥、Tavily 密钥、数据库凭据和对象存储凭据都留在主服务，沙箱只获得当前执行需要的文件和参数。
- 本轮不接入收费云沙箱；阿里云 Agent Sandbox、E2B 或 Daytona 只能作为未来 adapter，在通过兼容性、费用、网络和数据位置评估后增加。
- 沙箱输出先返回 Tool Gateway，经校验后由 Backend 发布为正式产物；沙箱文件系统和快照不是长期业务真相。

## Capabilities

本变更新增三项可独立验收的 capability：

- `portable-artifact-storage`：可替换字节存储、不可变产物版本、原子发布和私有下载。
- `governed-tool-execution`：进程内统一工具准入、路由、生命周期和产物收口。
- `isolated-sandbox-execution`：受限、可取消、可替换的 sandbox-as-tool 执行。

对应 delta specs 位于本变更目录的 `specs/` 下。

## User Outcomes

完成本变更后，用户可以：

1. 上传 PDF、Word 等现有支持的资料，或让 Agent 生成当前已支持的 Word、Markdown、CSV 产物，文件字节可以落在本机 MinIO。本变更不扩展文档生成格式。
2. 在资料库看到同一个逻辑产物的多个不可变版本、来源会话和来源执行，并选择指定版本继续加工。
3. 通过现有鉴权入口下载文件；MinIO 模式返回短期可用的私有下载地址，不暴露永久公共对象地址。
4. 使用当前 Docker 沙箱完成受限 Python/文件任务；未来更换云沙箱时无需改写 Agent loop、产物模型和工具审批。

## In Scope

- Backend BlobStore 接口、LocalFS 驱动和 S3/MinIO 驱动。
- 独立 Bucket、专用凭据、内部与外部 Endpoint、预签名下载和完整性校验。
- artifact/revision 元数据、来源关系、状态机和当前 revision。
- 当前 File API 的兼容投影与非破坏性迁移。
- Runtime 内 Tool Gateway 职责拆分。
- Local Docker sandbox adapter、执行限制、取消和输出收集。
- Web 的版本列表、下载失败和存储不可用状态适配。
- 配置样例、运行说明、迁移入口和验收入口。

## Out of Scope

- 独立 Tool Gateway、Artifact Service 或 Sandbox Service 微服务。
- 新增 Kubernetes、容器编排平台或常驻云沙箱池。
- 本轮真实接入阿里云 Agent Sandbox、E2B、Daytona 或付费云资源。
- 永久公开 OSS/MinIO URL、匿名 Bucket 或不可撤销分享链接。
- 实时多人协同编辑、Office 原位编辑和二进制文档差异算法。
- 把 MinIO Bucket Versioning 作为产品版本权威源。
- 沙箱直接持有 MinIO/OSS 长期密钥或直接写正式对象前缀。
- 自动备份用户当前演示数据；已有数据不做破坏性删除。

## Deployment Impact

- 默认服务数量不增加。Backend、Runtime、Web 和可选 Compute Broker 维持现有边界。
- `BLOB_STORE_PROVIDER=local` 时保持当前单机兼容行为。
- `BLOB_STORE_PROVIDER=s3` 时连接用户已有 MinIO；仓库不把 MinIO 加入默认常驻 Compose。
- MinIO 不可用时，新的对象发布必须明确失败，不能静默写回另一存储形成双重事实；读取既有 local 对象仍按其记录的 provider 处理。

## Success Criteria

- 同一套业务代码可通过配置在 LocalFS 和 MinIO 间选择，数据库明确记录每个对象的存储 provider 和 key。
- MinIO Bucket 保持私有；未经 Backend 鉴权不能从产品 API 获得下载定位。
- 每个正式 revision 指向一个不可变对象，包含 SHA-256、大小、媒体类型和来源信息。
- 上传中断、对象校验失败或数据库提交失败不会生成可见 READY revision。
- 原有 builtin/MCP/Compute 工具均继续通过 Tool Gateway，并保持审批、预算、幂等、取消和审计行为。
- Local Docker executor 被统一接口消费，沙箱内不存在模型、搜索、数据库或存储长期凭据。
- 未获得测试授权前只准备验证入口；实现状态与验证状态分别报告。

## Research Basis

- DeepAgents 官方将 sandbox backend 设计为可替换文件/执行后端，并区分 agent-in-sandbox 与 sandbox-as-tool：<https://docs.langchain.com/oss/python/deepagents/sandboxes>
- MinIO 提供 S3 API、预签名访问和 Bucket Versioning：<https://min.io/docs/minio/linux/operations/concepts/architecture.html>
- 阿里云 OSS 兼容常用 S3 API 但存在请求风格、ACL、ETag 等差异，因此不应把完全兼容作为未经测试的假设：<https://help.aliyun.com/zh/oss/developer-reference/compatibility-with-amazon-s3>
- 阿里云 Agent Sandbox 提供 E2B 兼容路径但并非所有能力完全一致，保留 adapter 比写死供应商更稳妥：<https://help.aliyun.com/zh/agent-sandbox/e2b-compatibility-explanation>

## Related Decisions

- `docs/decisions/006-framework-first-harness.md`
- `docs/decisions/007-personal-agent-harness.md`
- `docs/plan-v3/PERSONAL-AGENT-OPTIMIZATION.md`
- `docs/plan-v3/ROADMAP.md` 的 P2 产物连续编辑目标
