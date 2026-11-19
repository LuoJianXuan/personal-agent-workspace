# 个人连接本机验收

日期 2026-11-16。环境为 Docker Desktop Linux Engine 与本机浏览器，隔离端口 5174。用户允许将现有麦当劳 MCP Token 绑定到隔离测试账号。

## 已验证

- Backend Go 测试、Runtime Python 编译、Web TypeScript 与 Vite 生产构建通过。
- 已运行既有 `verify-phase1.ps1 -Authorized -KeepRunning -SkipBuild`。通过模型/技能配置、平台 MCP、审批、取消、流式、事件持久化、资料、解析、报告和迁移回归。
- 本地真实 MCP 协议夹具验证两个用户的工具和账户结果分别隔离，伪造连接 ID 被拒绝。坏 Token 返回安全认证提示，保留旧连接。
- 迁移 009 在隔离库运行成功。管理员隐藏连接器后，用户目录与有效工具均移除它；重新发布后，原授权可用于新的快照。普通用户无法读取管理员配置 API。
- 合成服务故意回显测试 Token。模型输出和 canonical events 只看到脱敏结果。模拟写工具在批准前执行 0 次，批准后执行 1 次。断开后原待审批写工具执行 0 次。
- Skill 包含必需个人连接和可选平台搜索时，无个人连接会拒绝提交，可选搜索缺失会写入安全快照的缺失能力字段。
- 浏览器从对话顶部打开「我的连接」，填写合成 Token，验证发现 4 个工具，选择「仅授权查询」，显示 1 项获授权。屏幕内的操作使用合成账户。
- 实际麦当劳连接为隔离测试账号授权了 16 个查询工具。另一账号看不到其工具。重建 Backend、Runtime 后仍保持授权，读取目录无需重输 Token。

## 浏览器真实活动查询

在隔离对话中点击「发送消息」，运行结果为 `SUCCEEDED`。工具卡显示「麦当劳中国 · 查询活动日历」并出现真实活动条目。模型使用 Mock，发现、凭据获取、SDK、PG、Tool Gateway、SSE 和麦当劳服务均为实机链路。

数据库记录同一用户连接的 2 次只读执行，分别为 `campaign-calendar` 和 `now-time-info`，每项均产生 `tool.requested → tool.started → tool.completed`。审批、真实模型、搜索或网页读取、真实写操作的次数均为 0。验收指令的前缀匹配导致第二次时间读取，已修正 Mock 指令匹配。

最终构建复测使用活动查询对话。浏览器显示已完成、已同步，数据库状态 `SUCCEEDED`。实际执行 `campaign-calendar` 1 次，记录完整的请求、启动、完成事件。两次活动对话合计 3 次远端只读工具执行，0 次远端写执行、0 次真实模型请求。

Git 忽略规则覆盖 `.env` 与 `.env.test`。对候选源文件逐值扫描未发现麦当劳 Token、Tavily Key 或个人连接密钥环。

## 真实 DeepSeek、麦当劳及 Langfuse 联合验收

| 环境 | 网页对话与运行 | 数据库及 Langfuse |
| --- | --- | --- |
| 隔离 5174 | 活动查询已完成 | 两次真实 `deepseek-flash` 请求。个人连接成功执行活动日历和当前时间各一次，每项均写入请求、启动、完成事件。Langfuse 查到 20 条观测，其中包含两条模型 generation、活动工具 observation 和 Agent 根节点。 |
| 正式 5173 首次 | 保留已显示的部分回答 | 已调用一次活动工具。两次真实模型请求，第二次以 `MODEL_STREAM_INCOMPLETE` 结束，数据库缺少该次请求的 token 用量。正式默认模型当时的输出上限为 512。 |
| 正式 5173 复测 | 活动查询已完成、已同步 | 正式模型上限调整为 4096。两次真实 `deepseek-flash` 请求，个人连接成功执行 `campaign-calendar` 一次，依次记录 `tool.requested → tool.started → tool.completed`。Langfuse 查到 18 条观测，其中包含两条模型 generation、对应的活动工具 observation 和 Agent 根节点。 |

隔离浏览器运行曾显示持续残留的超时提示。已分离后台轮询错误与用户操作错误，轮询恢复后清除旧提示。Web TypeScript 和 Vite 生产镜像重新构建通过，正式站成功结果显示「已完成、已同步」。

三轮联合验收合计 6 次真实模型请求，包含失败请求。5 次有可读用量记录，合计 62,544 输入 tokens、457 输出 tokens。四次真实麦当劳只读工具执行，真实写操作及新增 Tavily/网页抓取请求各 0 次。连接发现属于配置操作。Tavily 在正式 Runtime 核对的是部署配置。

扫描当前 Git 可见文件，6 项实际部署值均未出现，其中包括模型/搜索/MCP/Langfuse 密钥和两个环境的连接密钥。正式切换见 [发布记录](PC-RELEASE.md)。
