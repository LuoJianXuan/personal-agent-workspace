# ART-01：BlobStore 与 MinIO

日期：2026-11-07。实现：代码齐备。验证：运行通过。

## 改动与契约

LocalFS 与 S3 驱动实现；行级 provider；S3 internal/public endpoint 分离、600秒默认签名；MinIO SDK固定v7.0.83。默认local允许空凭据。

涉及：services/backend/internal/blobstore/store.go、go.mod/go.sum、compose.yaml、.env.example。

## 一条请求

Backend → Registry.For(row.provider) → Local/S3 Get/Put/Head → hash 检查。

## 失败边界

网络/凭据/配置失败返回安全存储错误，不静默切换provider。对象Key不可覆盖；路径和symlink校验。

## 已执行证据

Windows 与 Linux 均通过 LocalFS 不可变、路径穿越、symlink 和完整性测试；真实 MinIO 通过 Put/Get/Head/Delete、私有桶 403、短签名和错误摘要拒绝。端到端使用随机专用桶验证并完成对象/桶清理。

## 验收边界

正式 5173 当前仍使用 LocalFS；MinIO adapter 已实际验证，但未把 Langfuse 业务桶设为个人 Agent 的长期桶。S3 DNS/TCP、TLS 和响应超时已补齐。
