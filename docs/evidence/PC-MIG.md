# PC-MIG

本地隔离部署将密钥环写入已忽略的 .env.test，Compose 仅注入 Backend。默认功能开关保持关闭，启用时沿用已有服务。迁移保留旧历史，不把共享凭据分配给用户。

Backend 和 Runtime 已实际重建。麦当劳个人测试连接仍显示已连接、16 项只读工具，其他账号不可见。

运行范围、失败边界与后续验收见 [本轮验证记录](PC-VERIFY.md) 和 [任务清单](../../openspec/changes/platform-capabilities-and-personal-connections/tasks.md)。
