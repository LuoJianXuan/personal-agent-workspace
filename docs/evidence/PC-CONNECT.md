# PC-CONNECT

用户可发现工具并授权、刷新目录、验证新 Token、断开。候选 Token 在确认前不覆盖有效连接，过期清理由 Backend 执行。真实麦当劳 Token 通过本地被忽略的配置读入，只绑定隔离测试账号。合成服务的无效 Token 返回安全认证错误，原连接仍有效。

运行范围、失败边界与后续验收见 [本轮验证记录](PC-VERIFY.md) 和 [任务清单](../../openspec/changes/platform-capabilities-and-personal-connections/tasks.md)。
