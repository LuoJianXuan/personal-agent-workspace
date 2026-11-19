# ART-02：产物与不可变版本

日期：2026-11-07。实现：代码齐备。验证：运行通过。

## 改动与契约

稳定artifact/revision/File关联、来源thread/run/execution、不可变key；PENDING在事务内，失败回滚不可见；独立持久化清理意图覆盖崩溃窗口。

涉及：services/backend/internal/agententry/files.go、artifacts.go、007_portable_artifacts.sql。

## 一条请求

候选manifest → 清理意图提交 → PENDING事务 → Put/Head → READY及current revision事务提交。

## 失败边界

对象/元数据失败无可见READY；新写版本与并发父链冲突明确失败。历史分支允许，Run开始后的竞争版本不会静默覆盖。

## 已执行证据

LocalFS 与真实 MinIO 均通过首次发布、幂等导出、v1→v2 revision、parent/source 关系、历史版本可读、跨用户拒绝及 SHA 校验。

## 验收边界

验收数据位于隔离数据库；MinIO 使用随机专用桶并在验收后清理。正式演示数据未删除或搬迁。
