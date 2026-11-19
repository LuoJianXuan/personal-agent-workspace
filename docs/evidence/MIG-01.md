# MIG-01：兼容迁移

日期：2026-11-07。实现：代码齐备。验证：运行通过。

## 改动与契约

migration 007纳入现有迁移/ready；旧文件local回填；明确父链backfill，无解链独立保留；File API兼容；更新旧验收脚本的版本和物理路径假设。

涉及：007_portable_artifacts.sql、database.go、files.go、blob_cleanup.go、scripts/accept-day2.py、accept-storage.py。

## 一条请求

旧schema → migration007 → 旧obj-key/local读取 + 新revision/S3可选写入。

## 失败边界

迁移已在隔离库与正式库运行；不 DROP 旧列/表，不搬迁或删除旧字节。清理只删除预先记录且无引用的失败对象。

## 已执行证据

007 在既有卷上执行并重复执行通过；正式 `backend.schema_migrations` 已包含 1–7，旧对象在重复迁移后仍可按 SHA 下载。

## 验收边界

本轮未做旧镜像回滚演练；迁移设计保持向前兼容并保留新增表/字段。
