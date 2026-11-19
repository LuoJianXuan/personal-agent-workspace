# SBX-01：可替换沙箱执行

日期：2026-11-07。实现：代码齐备。验证：运行通过。

## 改动与契约

SandboxExecutor Protocol、Task/Limits/Result与Output；LocalDockerExecutor复用broker单次lease；限制通过DTO传递并在broker严格验证；输出size/hash在runner、broker、collector核验。

涉及：services/runtime/app/sandbox.py、compute.py、compute_broker.py、services/compute-runner/runner.py。

## 一条请求

工具准入 → 授权输入/hash → LocalDockerExecutor → Docker → 候选输出 → ArtifactCollector → Backend。

## 失败边界

确认取消后CANCELLED；取消/超时无法确认或连接中断为UNKNOWN；未知provider不降级为宿主执行。容器仍禁网、非root且无长期凭据。

## 已执行证据

真实 Docker 验证通过非 root、只读根、无 Docker socket、无长期凭据、禁网、输出上限、symlink 拒绝、幂等、冲突、前置/运行中取消和超时；Harness→Python→CSV 发布与 API 取消均通过，任务容器/卷残留为 0。

## 验收边界

这是本机单用户 Docker 隔离验收，不等同于企业多租户安全认证；收费云沙箱 adapter 仍不在本轮范围。
