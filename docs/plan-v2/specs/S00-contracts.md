# S00：冻结三端契约与目录

时间：D1 上午。前置：无。

## 目标
建立独立项目目录，明确两个页面布局、两个后端服务与共享契约。只落实契约，不提前生成整套业务。

## 实施任务
- 创建 apps/web、services/backend、services/runtime、services/demo-mcp、schemas、scripts、docs/evidence。
- Backend 固定 internal/control、internal/workspace、internal/agententry；定义能力快照、workspace 应用接口与 RuntimeClient，依赖规则遵守 ARCHITECTURE，不跨模块直接访问业务表。
- 写 docs/decisions/002-entry-topology.md：首版合并入口的收益与故障/资源代价、未来抽出网关的触发条件；不是首版新增服务任务。
- 将 message.started/delta/completed、message_id/chunk_index/is_final、RESOURCE_EXHAUSTED 与重连样例加入共享契约；正文流式是首版要求。
- 将 CONTRACTS.md 落到 OpenAPI/JSON Schema，提供 start、event、snapshot、approval、tool-result、file、chart 的 JSON 样例。
- Go/Python/TS 定义精简消费模型；共享序列化样例，未知字段拒绝规则一致。先固定模型生成/维护方法，禁止三边自行发明字段。
- 写 docs/decisions/001-ownership.md，说明 Backend submission 与 Runtime Run 的区别、审批决定权威源、文件所有权。
- 写规范化参数摘要规则与样例（排序键、UTF-8、数值、空值），不用语言默认 map 序列化碰运气。
- 定义三层幂等、同 thread 串行、一个 Run 同时一个审批、事件游标和错误码。
- 把 PROJECT_RULES 的执行与测试偏好写入新项目 AGENTS.md。

## 完成与验收条件
- 契约明确 Web 只能调用 Backend；Runtime 不提供管理配置真相。
- 快照没有密钥；请求体不能自定身份；服务方向认证与公开认证分开。
- 管理 UI、文件和 CSV 场景在范围内；不退回固定工单页面。
- 产出共享样例与状态图；当前只标静态核对，不能宣称序列化测试通过。

## 交付记录
更新 TASKS.md、docs/evidence/S00.md；列出真实文件、接口、迁移、已执行动作、未执行验证、下一任务接入点。所有代码由 AI 编写。

## 随实现讲解
解释：为什么有 submission 和 Run？审批记录和图等待点分别是谁的事实？一条配置如何变成本轮能力？

## 可直接下发
阅读共同规则、架构、契约和 UI_SPEC，核对前置后只完成本 S00。保持独立三端与冻结首版范围，不主动启动子代理。默认不执行测试或真实模型，准备验收入口并标明状态；已明确授权的动作按原范围继续。不要要求用户手写，不以讲解阻塞下一阶段。
