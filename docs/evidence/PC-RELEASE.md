# PC-RELEASE

日期 2026-11-16。个人连接已切换到本机正式 [5173 工作台](http://localhost:5173)。切换前确认无活跃 Run。Backend 迁移由 007 升至 009，原有 3 个用户和 7 个会话保留，旧共享麦当劳连接启用数为 0。Backend、Runtime 和 Web 健康检查通过。

用户在「能力设置 → 我的连接」配置自己的麦当劳 Token 并确认授权。验收账号在正式站授权了 16 个查询工具，管理员自己的工具目录看不到该用户的工具。真实写操作走审批，审批恢复使用合成 MCP 验证。

正式浏览器对话显示「已完成、已同步」。同一 Run 的两次 DeepSeek 请求和一次活动日历调用已在 Langfuse 入库。

Runtime 重建后仍读取到 DeepSeek、Tavily 和专用 Langfuse 配置。复核同一测试用户仍可见 16 项查询授权，无需重新填写 Token。5174 已恢复 Mock。联合验收实际使用 6 次模型请求，保留 2 次给本机正式站，单次输出上限 4096 tokens。配置保存在 Git 忽略的本机环境文件。Tavily 本轮仅核对配置，真实调用见历史验收记录。

详见 [本轮验证记录](PC-VERIFY.md) 和 [任务清单](../../openspec/changes/platform-capabilities-and-personal-connections/tasks.md)。
