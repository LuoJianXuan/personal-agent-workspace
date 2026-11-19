# Spec Delta

## Purpose

把 Runtime 内现有工具准入能力固化为可维护、可扩展的治理主干，使 builtin、MCP、沙箱和未来桌面执行共享权限、审批、预算、生命周期和产物发布规则。

## ADDED Requirements

### Requirement: 唯一工具准入入口
所有由 Agent 发起的工具调用 SHALL 通过进程内 Tool Gateway façade；Agent 和模型不得直接调用 builtin、MCP、sandbox executor 或 BlobStore。

#### Scenario: 调用 builtin 工具
- **WHEN** Agent 请求已注册的 builtin 工具
- **THEN** Tool Gateway SHALL 在执行前完成解析、参数校验和策略判断

#### Scenario: 调用 MCP 工具
- **WHEN** Agent 请求已启用的 MCP 工具
- **THEN** Tool Gateway SHALL 使用同一 execution lifecycle 路由到 MCP executor

#### Scenario: 请求未注册工具
- **WHEN** Agent 请求 Registry 中不存在或当前快照未启用的工具
- **THEN** Tool Gateway SHALL 拒绝执行并产生安全的失败事件

### Requirement: 执行前治理
Tool Gateway MUST 在 executor dispatch 前完成 schema、文件作用域、权限、审批、预算、网络策略和幂等检查；executor 的存在不得被视为授权来源。

#### Scenario: 缺少审批
- **WHEN** 高风险工具调用没有匹配 execution 和参数 hash 的有效审批
- **THEN** Tool Gateway SHALL 返回 `APPROVAL_REQUIRED` 且 executor MUST NOT 被调用

#### Scenario: 文件超出作用域
- **WHEN** 工具参数引用不在当前授权 file_refs 中的文件
- **THEN** Tool Gateway SHALL 拒绝调用且不得向 executor 提供该文件

#### Scenario: 工具预算耗尽
- **WHEN** 当前 Run 的对应工具预算已耗尽
- **THEN** Tool Gateway SHALL 返回明确预算错误且不得静默增加预算

### Requirement: 统一执行生命周期
每个工具调用 SHALL 具有稳定 execution_id，并支持幂等、超时、取消和 SUCCEEDED/FAILED/CANCELLED/UNKNOWN 终态。

#### Scenario: 重复成功请求
- **WHEN** 相同 execution_id 和参数 hash 在成功后重试
- **THEN** Tool Gateway SHALL 返回既有成功结果而不是再次执行副作用

#### Scenario: 参数冲突重试
- **WHEN** 相同 execution_id 使用不同参数 hash 重试
- **THEN** Tool Gateway SHALL 返回冲突并拒绝执行

#### Scenario: 用户取消执行
- **WHEN** Run 在工具执行期间被取消且 executor 支持取消
- **THEN** Tool Gateway SHALL 请求真实取消并在确认后记录 CANCELLED

#### Scenario: 终态无法确认
- **WHEN** executor 连接中断且无法判断副作用是否已发生
- **THEN** Tool Gateway SHALL 记录 UNKNOWN 且不得自动重复副作用操作

### Requirement: 统一 executor 结果
所有 executor SHALL 返回规范化 ToolExecutionResult；文本必须有界，文件只能作为 candidate artifacts 返回，不能由 executor 直接创建业务 revision。

#### Scenario: 工具产生文件
- **WHEN** executor 返回一个或多个候选文件
- **THEN** Artifact Collector SHALL 校验 manifest 并通过 Backend 发布，只有 READY revision 才能进入最终结果

#### Scenario: 候选文件校验失败
- **WHEN** 候选文件的路径、类型、大小或 checksum 不符合策略
- **THEN** Tool Gateway SHALL 使该候选发布失败且不得暴露 executor 内部路径

### Requirement: Canonical events 保持权威
Tool Gateway SHALL 为工具请求、执行、审批恢复、取消、完成和失败产生 canonical events；内部模块拆分不得创建第二套运行事实。

#### Scenario: 正常执行
- **WHEN** 工具从请求进入成功终态
- **THEN** 事件序列 SHALL 可按 execution_id 重建其请求、运行和完成状态

#### Scenario: 审批后恢复
- **WHEN** 用户批准暂停中的工具调用并恢复 Run
- **THEN** 恢复 SHALL 继续关联原 execution、参数 hash 和审批决定

### Requirement: Tool Gateway 保持进程内
本变更 SHALL 将 Tool Gateway 作为 Runtime 内部模块重构，不得新增独立常驻 Tool Gateway 服务或要求 Kubernetes。

#### Scenario: 默认部署
- **WHEN** 用户使用本变更后的默认 Compose 启动项目
- **THEN** 服务清单 MUST NOT 因 Tool Gateway 重构增加新的常驻业务容器

### Requirement: Agent 级观测不扩张为基础设施全链路
Langfuse SHALL 继续表达真实 Agent、模型和工具调用；内部 Policy、Router、BlobStore 和容器步骤不得被伪装成额外 Agent 或模型调用。

#### Scenario: 工具内部经过多个模块
- **WHEN** 一次工具调用经过策略、executor 和产物发布
- **THEN** Langfuse SHALL 保持一个可理解的真实工具调用节点，并可通过 metadata 关联 execution_id

#### Scenario: Langfuse 不可用
- **WHEN** 观测服务离线或回调失败
- **THEN** Tool Gateway SHALL 继续执行并依据 canonical events 决定业务终态
