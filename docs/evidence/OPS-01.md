# OPS-01：配置与运行文档

日期：2026-11-07。实现：代码齐备。验证：运行通过。

## 改动与契约

配置只透传Backend，MinIO不是默认新服务；记录Bucket专用凭据、internal/public差异、HTTPS、签名与CORS、versioning和备份边界。

涉及：.env.example、compose.yaml、README.md、ARCHITECTURE.md、docs/portable-artifacts-guide.md。

## 一条请求

部署配置 → Backend Registry → LocalFS 或已有 MinIO。

## 失败边界

Docker Linux Engine 已启动；真实 MinIO 仅使用随机前缀专用桶并完成清理，长期凭据未输出或写入仓库。正式 5173 已切换到最新镜像，仍保持 LocalFS 默认值。

## 已执行证据

Compose 构建、隔离栈、真实 MinIO、真实 Docker 沙箱和正式 5173 启动均通过；默认 Compose 未新增常驻服务。

## 验收边界

尚未为日常环境创建长期专用 Bucket/最小权限用户；这是后续选择启用 MinIO 时的部署动作，不影响 LocalFS 默认发布。
