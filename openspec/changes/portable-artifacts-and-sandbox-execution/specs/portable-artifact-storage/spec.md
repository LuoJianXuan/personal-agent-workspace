# Spec Delta

## Purpose

为 Personal Agent 提供与具体厂商解耦的私有字节存储、稳定产物身份、不可变版本链和可跨端使用的短期下载定位，同时保留现有本地文件兼容能力。

## ADDED Requirements

### Requirement: 可替换的 BlobStore
Backend SHALL 通过统一 BlobStore 契约读写正式文件字节，并至少支持现有本地文件存储和 S3 兼容存储；业务逻辑不得直接依赖 MinIO 或阿里云 OSS 专属 API。

#### Scenario: 使用本地存储
- **WHEN** 部署配置 `BLOB_STORE_PROVIDER=local`
- **THEN** 新文件 SHALL 由 LocalFilesystemBlobStore 保存并可通过现有产品下载入口读取

#### Scenario: 使用本机 MinIO
- **WHEN** 部署配置有效的 S3 Endpoint、Bucket 和专用凭据
- **THEN** 新文件 SHALL 写入 MinIO，数据库 SHALL 记录该对象的 provider、key、大小和 SHA-256

#### Scenario: 对象存储不可用
- **WHEN** MinIO 在发布新对象时不可达
- **THEN** 系统 SHALL 返回明确存储错误且 MUST NOT 静默把同一对象写入 LocalFS

### Requirement: 行级存储定位
每个不可变文件对象 SHALL 记录自己的 storage provider 和 storage key；读取行为不得只依赖当前进程的全局 provider 配置。

#### Scenario: 切换新写入 provider
- **WHEN** 部署从 local 切换为 s3 且数据库仍包含旧 local 文件
- **THEN** 系统 SHALL 从各行记录的 provider 读取旧文件，并把新文件写入 s3

### Requirement: 稳定产物和不可变版本
系统 SHALL 以稳定 artifact identity 表示逻辑产物，并以独立、不可变的 revision 表示每次正式内容版本；创建新版本不得覆盖旧版本对象。

#### Scenario: 创建首个版本
- **WHEN** 工具首次发布一个新的逻辑产物
- **THEN** 系统 SHALL 创建 artifact、revision 1 和唯一 object key，并把该 revision 设为当前版本

#### Scenario: 从指定版本继续加工
- **WHEN** 用户选择历史 revision 继续生成新内容
- **THEN** 系统 SHALL 创建带 parent revision 的新 revision，同时保留原 revision 可定位和下载

#### Scenario: 并发版本冲突
- **WHEN** 两个请求以同一预期当前 revision 并发推进产物
- **THEN** 系统 SHALL 只接受符合并发控制条件的更新，并为另一个请求返回明确冲突

### Requirement: 版本来源可追踪
每个生成 revision SHALL 记录可用的来源 thread、run、tool execution、parent revision 和说明；缺失的可选来源不得通过猜测填充。

#### Scenario: 工具生成产物
- **WHEN** sandbox 或其他工具成功发布候选文件
- **THEN** 新 revision SHALL 关联该 execution 和 run，且产物详情 SHALL 能返回这些来源标识

### Requirement: 原子产物发布
正式 revision SHALL 经过 PENDING、对象写入与完整性核验后才能变为 READY；失败或不完整 revision 不得作为可下载版本展示。

#### Scenario: 正常发布
- **WHEN** 对象写入成功且 Head 结果与预期大小和 SHA-256 一致
- **THEN** 系统 SHALL 在数据库事务中把 revision 标为 READY 并更新当前版本

#### Scenario: 对象校验失败
- **WHEN** 对象大小或 SHA-256 与候选 manifest 不一致
- **THEN** 系统 SHALL 标记发布失败、阻止下载并返回 `FILE_INTEGRITY_ERROR`

#### Scenario: 幂等重试
- **WHEN** 同一 execution 和 artifact key 在不确定响应后重试
- **THEN** 系统 SHALL 返回或完成同一发布记录，而不是创建两个正式 revision

### Requirement: 私有短期下载
所有对象 SHALL 保持私有；用户下载必须先通过 Backend 鉴权，S3 对象只可获得短期预签名定位，签名 URL 不得持久化。

#### Scenario: 下载本地对象
- **WHEN** 已授权用户下载 local provider 文件
- **THEN** Backend SHALL 使用安全响应头流式返回文件

#### Scenario: 下载 MinIO 对象
- **WHEN** 已授权用户下载 s3 provider 文件
- **THEN** Backend SHALL 使用浏览器可访问的 public endpoint 生成有限有效期的预签名 GET

#### Scenario: 越权下载
- **WHEN** 用户请求不属于自己的 file 或 revision
- **THEN** Backend SHALL 拒绝请求且 MUST NOT 生成或泄漏对象 URL

#### Scenario: 下载地址过期
- **WHEN** 预签名 URL 已超过有效期
- **THEN** 客户端 SHALL 重新请求 Backend 鉴权生成，而不是复用或延长旧 URL

### Requirement: 非破坏性兼容迁移
迁移 SHALL 保留现有 File API 和旧 local 对象的可读性；旧数据不得仅通过修改 metadata 冒充已经迁移到对象存储。

#### Scenario: 升级旧数据库
- **WHEN** migration 遇到没有 storage provider 的现有 file 行
- **THEN** 系统 SHALL 将其按现有本地布局解释为 local，并保留原 storage key

#### Scenario: 无法确定旧版本链
- **WHEN** backfill 无法可靠判断两个旧文件是否属于同一 artifact
- **THEN** 系统 SHALL 保留独立产物而不是猜测合并或删除文件

### Requirement: 对象存储版本不是产品真相
产品 revision SHALL 由 PostgreSQL 元数据定义；MinIO/S3 Bucket Versioning 只能作为底层保护，不能决定业务版本号、父子关系或当前版本。

#### Scenario: Bucket Versioning 已开启
- **WHEN** MinIO 为同一 key 返回多个底层 version ID
- **THEN** 产品 SHALL 仍只依据 artifact revision 元数据展示和继续加工版本
