# 产物、MinIO 与沙箱执行

状态：本次代码已接入，静态编译/类型/语法核对完成；真实 MinIO、数据库迁移、Docker 执行和浏览器业务验收尚未执行。当前日常部署未自动切换。

## 存储配置

默认使用 `BLOB_STORE_PROVIDER=local`，旧文件继续按原 `obj-{id}` 读取，新文件使用不可变分层 key。启用 MinIO 时，Backend 需要以下配置：

```env
BLOB_STORE_PROVIDER=s3
S3_INTERNAL_ENDPOINT=http://host.docker.internal:9000
S3_PUBLIC_ENDPOINT=http://localhost:9000
S3_BUCKET=personal-agent
S3_REGION=us-east-1
S3_FORCE_PATH_STYLE=true
S3_PRESIGN_TTL_SECONDS=600
S3_ACCESS_KEY_ID=<仅在本地秘密环境设置>
S3_SECRET_ACCESS_KEY=<仅在本地秘密环境设置>
```

internal endpoint 必须能被 Backend 容器访问；public endpoint 必须能被当前下载设备访问。手机端不能使用指向手机自己的 localhost。正式公网部署使用 HTTPS 域名。预签名 URL 在 public endpoint 上生成，不能生成后替换域名，否则签名失效。

复用已有 MinIO 实例，创建独立私有 Bucket 和只允许该 Bucket 的专用访问凭据。应用凭据只需 Bucket location/list 与 Object get/put/delete 能力；不授予用户、策略或其他 Bucket 的管理权限。Backend 不自动创建 Bucket/用户。MinIO 单节点不是备份；正式个人资料应另行配置复制或备份。

浏览器下载采用跳转/链接，不通过跨域 fetch 拉取 MinIO 字节，因此本次不要求开放 CORS。未来浏览器直传才需要按实际前端 origin 配置 CORS。不要开放公共读策略。

MinIO Bucket Versioning 可选；产品版本由 PostgreSQL artifact/revision 定义，每个 revision 使用不可变 key。若开启底层 versioning，应配置旧版本和未完成分片清理策略，避免长期占满磁盘。

## 发布与下载

Runtime 的 ArtifactCollector 核验候选名称、类型、大小和 SHA-256，Backend 先独立持久化对象 key 的清理意图，再在事务内创建 PENDING 元数据、上传并核验对象，最后提交 READY。失败事务回滚，不对用户展示不完整版本。清理意图覆盖进程崩溃窗口；清理器延迟一小时、重新确认没有 files 引用后才删除，不扫描共享 Bucket。

`/api/files/{id}/download-location` 必须使用用户 JWT。LocalFS 返回同源流式入口；S3 返回 5–15 分钟签名地址。签名只在当前下载操作中使用，不入数据库、事件或日志。链接有效期内持有者可访问该对象，不能当作一次性凭证；永久分享和撤销分享是后续独立能力。

`/api/files/{id}/versions` 保持 File 列表兼容。`/api/artifacts/{id}/revisions` 返回稳定 artifact、current revision 和来源元数据。资料库只展示逻辑产物当前版本，历史版本通过版本列表定位；继续加工会使用所选 File ID。

## 工具与沙箱

ToolGatewayService 仍为 Runtime 内 façade，内部拆为 Registry、Policy、Lifecycle、Router 和 executors。DeepAgents 文件工具仍经过同一 façade 与 WorkspaceBackend 授权。普通固定解析沿用受限子进程；动态 Python 沿用可选 Compute Broker。

`SANDBOX_PROVIDER=local_docker` 是本轮唯一实现的 provider。未配置 broker 时动态计算明确不可用，未知 provider 明确失败。Agent 和所有长期凭据均在容器外，runner 的代码进程只继承显式环境白名单。沙箱内输入是任务副本，修改副本不会改写用户原件；输出经过 manifest 和 hash 校验再发布。

## 升级和兼容

1. 停止提交新任务并等待在途文件/产物写入结束。
2. 构建 Backend/Runtime/Web，执行现有 Backend migrate（新增 007）；Runtime 数据表无需新版本。
3. 旧文件回填 local provider；有明确、同 owner、同媒体类型父链的产物回填 lineage，异常链保留独立产物。字节不移动、不删除。
4. 默认仍为 local；仅在专用 MinIO Bucket/凭据和内外 Endpoint 确认后切换新写入。
5. 切回 local 仅改变新写入，已有 s3 对象仍按行级 provider 读取；保留 S3 配置和凭据，不能改写 provider 冒充搬迁完成。

本次没有创建备份、回滚脚本，也没有删除当前演示数据。

## 验收入口

只读检查可使用 Backend 数据库角色查询：

```sql
SELECT storage_provider, status, count(*) FROM backend.files GROUP BY storage_provider,status;
SELECT count(*) AS pending FROM backend.artifact_revisions WHERE status='PENDING';
SELECT count(*) AS cleanup_candidates FROM backend.blob_cleanup WHERE created_at < now()-interval '1 hour';
```

清理器只处理预先记录且无文件引用的 key；不提供无约束的 Bucket 批量删除入口。运行时详情中的失败是请求事实，PENDING 元数据在失败事务回滚后不会被当作正式版本展示。

以下命令仅为准备好的入口，本次未执行测试：

- Backend 本地边界：`go test ./internal/blobstore -run TestLocal`。
- Backend 真实 MinIO：配置上述 S3 环境，设置 `WORKSPACE_STORAGE_ACCEPTANCE=true` 后运行 `go test ./internal/blobstore -run TestMinio`。只创建随机 acceptance 前缀并在结束时清理。
- 隔离业务链路：先按 README 准备 5174/5175 Mock 验收栈并执行迁移，再设置 `WORKSPACE_ARTIFACT_ACCEPTANCE=true`，运行 `python scripts/accept-portable-artifacts.py`。Mock 仅替换模型输出，数据库、Backend、Runtime 和文件存储均为真实模块。
- 回归：现有 `verify-mock.ps1 -Authorized` 和 `verify-compute.ps1 -Authorized`；真实模型和浏览器依照用户单独授权执行。

存储故障、过期签名、并发 lineage、历史库 backfill、取消/UNKNOWN 和沙箱禁网场景见 OpenSpec delta specs。上述入口并不意味着完整 Scenario 矩阵已经通过。
