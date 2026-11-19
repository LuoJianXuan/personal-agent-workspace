# ACC-01：整体验收结论

日期：2026-11-07。变更：`portable-artifacts-and-sandbox-execution`。

实现：完成。验证：本轮范围内运行通过。正式 `http://localhost:5173` 已更新并健康，当前默认存储为 LocalFS。

## 已执行

- 静态与构建：契约生成副本、五个新增样例、OpenAPI 路径、Python AST、Go build、TypeScript/Vite build、Python compileall 与 `diff --check`。
- 完整 Mock 业务回归：模型/技能/MCP 控制面、能力快照、审批、取消、幂等、UNKNOWN、事件回放、资料库、CSV/图表/报告、故障注入、安全边界、32 SSE 上限和 Runtime 单元测试。Mock 仅替换模型输出，数据库、Backend、Runtime、MCP、工具与存储均为真实模块。
- Phase 1 深度回归：DOCX/PDF/XLSX 按需解析、网页夹具研究链、文档技能、原生工作文件、长结果卸载、上下文摘要、模型/工具预算和迁移保护。
- LocalFS：Windows 与 Linux 均验证不可变写入、SHA 完整性、路径穿越和 symlink 逃逸；业务链路验证上传、下载、版本和重复迁移保留字节。
- 真实 MinIO：复用本机现有实例，使用随机 `personal-agent-accept-*` 专用桶完成 Put/Get/Head/Delete、私有桶未签名 403、短期签名下载、错误摘要拒绝和完整业务链路；结束后对象与桶均已清理，未混入 Langfuse 业务桶。
- 真实 Docker 沙箱：验证非 root、只读根、无 Docker socket、无长期凭据、禁网、输出数量、symlink、幂等冲突、取消、超时、Harness→CSV 发布；结束后任务容器和任务卷均为 0。
- 迁移与发布：007 在隔离库和正式既有卷实际执行并可重复；正式 `backend.schema_migrations` 包含 1–7；Backend、Runtime、PostgreSQL、MCP 均 healthy，5173 返回 200。

机器结果：portable-artifacts-results.json（本地验收记录）、phase1-compute-results.json（本地验收记录）、phase1-compute-flow-results.json（本地验收记录）。

## 验收发现并修复

1. S3 transport 只有响应头超时，错误 internal endpoint 可能长时间停在 DNS/TCP 连接。已增加 5 秒连接/TLS 超时、10 秒响应头超时和 1 秒 Expect-Continue 超时。
2. Python 验收客户端自动跟随 Backend 302 时会把 Bearer Token 转发给 MinIO，造成查询签名与 Authorization 双认证 400。实际 Web 本就使用 `download-location`；验收脚本已改为同样的跨源无 Bearer 下载方式并复验通过。
3. Docker 冷启动高负载时首次 SSE 验收出现一次短连接。对应 canonical event 完整保存 150 个连续 delta；同场景单独复验和随后完整回归均通过，未发现事件丢失或可重复产品缺陷。

## 未执行与边界

- 未执行新的浏览器宽屏/窄屏视觉操作；UI 仅完成生产构建、HTTP 和业务 API 验收。
- 新增真实模型调用与真实公网搜索调用均为 0；这两项不是存储/沙箱变更的完成条件。
- 正式 5173 保持 LocalFS。MinIO adapter 已真实验证，但尚未创建日常长期专用 Bucket/最小权限用户，也没有把 Langfuse Bucket 当作个人 Agent Bucket。
- 本机 Docker 沙箱通过不等于企业多租户安全认证；云沙箱 adapter 仍是后续任务。

## 任务证据

[CON-01](CON-01.md)、[ART-01](ART-01.md)、[ART-02](ART-02.md)、[DLV-01](DLV-01.md)、[TGW-01](TGW-01.md)、[SBX-01](SBX-01.md)、[OPS-01](OPS-01.md)、[MIG-01](MIG-01.md)、[UI-01](UI-01.md)。
