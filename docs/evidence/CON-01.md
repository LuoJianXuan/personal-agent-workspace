# CON-01：共享契约

日期：2026-11-07。实现：代码齐备。验证：运行通过。

## 改动与契约

增加 Artifact/Revision/List、DownloadLocation、CandidateArtifact；File 增加 artifact/revision 和来源字段。provider/key 仅在 Backend 内部。内部发布增加 execution、size、sha256。

涉及：schemas/openapi.yaml、schemas/jsonschema/contracts.json、schemas/examples/portable-* 及三语言生成副本。

## 一条请求

Runtime 候选输出 → JSON Schema → Backend 发布 → File/ArtifactRevision → Web。

## 失败边界

错误 checksum、越权 file 或冲突 idempotency key 必须拒绝；不得在 DTO/事件中保存永久签名地址。

## 已执行证据

Go Backend 编译、Web TypeScript、Python 语法、schema 副本与五个样例均通过；LocalFS/MinIO 业务验收使用同一生成契约通过。汇总见 [ACC-01](ACC-01.md)。

## 验收边界

本任务已完成静态和运行验收；浏览器视觉与新增真实模型/搜索调用未执行，且不影响共享契约结论。
