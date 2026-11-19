# Spec Delta

## Purpose

为 Personal Agent 提供沙箱即工具的隔离执行能力，使当前本地 Docker 与未来云沙箱可通过同一契约接入，同时阻断秘密继承、越权文件访问和不受控产物发布。

## ADDED Requirements

### Requirement: SandboxExecutor 可替换契约
Runtime SHALL 通过统一 SandboxExecutor 契约创建任务、传递授权输入、执行、收集候选输出、取消和销毁；Tool Gateway 不得依赖具体供应商 API。

#### Scenario: 使用现有 Compute Broker
- **WHEN** 本地 Docker 计算能力已启用
- **THEN** LocalDockerExecutor SHALL 把规范化 SandboxTask 映射到现有 Compute Broker 并返回 SandboxResult

#### Scenario: 沙箱能力未启用
- **WHEN** 工具请求需要 sandbox 而部署没有可用 executor
- **THEN** Tool Gateway SHALL 返回明确 capability unavailable 错误且不得在 Runtime 宿主进程执行动态代码

### Requirement: Agent 保持在沙箱外
DeepAgent、模型调用、会话状态、审批和 canonical events SHALL 留在 Runtime；沙箱仅接收执行所需参数、授权输入副本和非秘密配置。

#### Scenario: 执行 Python 任务
- **WHEN** Agent 调用受限 Python/计算工具
- **THEN** 只有代码、资源限制和当前任务授权文件 SHALL 进入沙箱

#### Scenario: Runtime 恢复
- **WHEN** 沙箱任务失败或容器被销毁
- **THEN** Agent Run 的长期状态和已发布产物 SHALL 仍可从外部事实源恢复

### Requirement: 沙箱不得获得长期凭据
SandboxExecutor MUST 使用显式环境白名单，并阻止模型、搜索、数据库、Backend、对象存储和观测服务长期凭据进入任务容器。

#### Scenario: 检查任务环境
- **WHEN** 任务代码枚举其环境变量
- **THEN** 结果 MUST NOT 包含 DeepSeek、Tavily、PostgreSQL、MinIO/OSS、Backend service token 或 Langfuse secret

#### Scenario: 需要认证能力
- **WHEN** Agent 任务需要搜索或其他认证服务
- **THEN** 该能力 SHALL 作为 Tool Gateway 管理的独立主服务侧工具执行，而不是向沙箱注入凭据

### Requirement: 默认拒绝网络
本地沙箱 SHALL 默认无网络；网络访问只能由未来明确注册的策略和受控 executor 能力开放，模型参数不得直接改变网络策略。

#### Scenario: 普通计算访问公网
- **WHEN** 沙箱代码尝试访问公网且当前工具没有网络能力
- **THEN** 连接 SHALL 失败，同时任务不得因此获得宿主网络或凭据

### Requirement: 资源和文件边界
SandboxExecutor SHALL 对 CPU、内存、进程、磁盘、wall time、输入和输出设置上限，并拒绝路径逃逸、符号链接和非普通输出文件。

#### Scenario: 超时任务
- **WHEN** 任务超过 wall time 限制
- **THEN** executor SHALL 终止真实容器、清理工作目录并返回超时终态

#### Scenario: 输出路径逃逸
- **WHEN** 任务尝试把输出声明为绝对路径、父目录路径或指向外部的符号链接
- **THEN** 输出收集 SHALL 拒绝该文件并不得读取沙箱边界外内容

#### Scenario: 输出超限
- **WHEN** 候选输出总大小或单文件大小超过策略
- **THEN** executor SHALL 返回明确超限错误且 Artifact Collector MUST NOT 发布部分伪成功结果

### Requirement: 取消和不确定终态
SandboxExecutor SHALL 支持 execution_id 级取消；无法确认容器是否停止或副作用是否完成时必须返回 UNKNOWN。

#### Scenario: 用户取消运行
- **WHEN** 用户在沙箱执行期间取消 Run
- **THEN** Runtime SHALL 向 executor 发送取消、等待有界清理，并禁止发布取消后的候选输出

#### Scenario: Broker 连接中断
- **WHEN** Runtime 与 Compute Broker 断开且无法查询任务终态
- **THEN** 工具状态 SHALL 为 UNKNOWN，系统不得自动重复执行

### Requirement: 沙箱输出必须经正式发布
沙箱路径、临时文件和快照 SHALL 视为临时状态；只有经 Artifact Collector 和 Backend 完整性校验后形成的 READY revision 才是用户产物。

#### Scenario: 正常生成文件
- **WHEN** 沙箱完成并返回符合 manifest 的候选文件
- **THEN** Runtime SHALL 把字节交给 Backend 发布，并在成功后返回稳定 revision/file 标识

#### Scenario: 容器销毁
- **WHEN** 任务容器在候选文件已正式发布后销毁
- **THEN** 用户 SHALL 仍能从 Artifact Service 下载和继续加工该 revision

### Requirement: 本轮不引入付费云沙箱
本变更 SHALL 只交付 provider contract 和 LocalDockerExecutor；阿里云 Agent Sandbox、E2B、Daytona 等实现必须通过后续独立变更提案接入。

#### Scenario: 配置未知云 provider
- **WHEN** 部署配置本变更尚未实现的云 sandbox provider
- **THEN** 系统 SHALL 拒绝启动该能力或报告 unsupported provider，而不是回退到未隔离宿主执行
