# 序光 · Agent Workspace

工具栏目更新：用户在「工具 → MCP」安装并授权自己的麦当劳账户，在「工具 → 技能」启用方法与输出模板。平台模型、搜索和公共工具继续由管理员配置。新界面的实施与验收状态见 [工具目录改造](docs/evidence/TC-RELEASE.md)。2026-11-16 已完成新界面浏览器核心业务、真实 DeepSeek 活动查询与 Langfuse 入库、完整 Mock 回归；发现问题的修复及验收边界见 [本轮验收报告](docs/evidence/TC-VERIFY.md)。

2026-11-07 开发更新：新增可替换 BlobStore（LocalFS / S3-MinIO）、产物与不可变 revision、私有临时下载、进程内 Tool Gateway 模块拆分和 Local Docker SandboxExecutor。LocalFS、真实 MinIO、迁移 007、完整 Mock 业务回归和真实 Docker 沙箱均已验收；正式栈已更新并运行于 `http://localhost:5173`，当前默认存储仍为 LocalFS。浏览器视觉与新增真实模型/搜索调用不属于本次验收。见 [配置与升级说明](docs/portable-artifacts-guide.md)、[任务清单](openspec/changes/portable-artifacts-and-sandbox-execution/tasks.md) 和 [当前证据](docs/evidence/ACC-01.md)。

2026-11-06 实施更新：项目目标固定为 **Personal Agent**。S16–S20 已完成代码和本地隔离验收；真实 DeepSeek 已通过 DOCX 按需读取、MCP 工具循环与专用 `Personal Agent Demo` Langfuse 调用树验收。文档改为 Runtime 内按需受控解析，默认部署不再需要独立 document-worker；内置文档技能按需读取，Langfuse 仅观测 Agent/模型/工具。最终状态见 [优化方案](docs/plan-v3/PERSONAL-AGENT-OPTIMIZATION.md) 与 [S16–S20 证据](docs/evidence/)。

独立个人 Agent 工作区。Day 1–7 功能已接入：通用聊天、协议化模型管理、技能、分级 MCP、逐次审批恢复、取消、资料库、CSV 图表与报告下载。2026-11-07 已完成 MCP 1.1 与工作台交互基线：真实麦当劳 Streamable HTTP 发现/只读调用通过，写工具进入通用审批，未知工具默认阻断。验收状态以 [验收报告](docs/acceptance-report.md) 和 [各阶段证据](docs/evidence/) 为准。

2026-11-06：第一阶段 S08–S20 采用实际 DeepAgents，补充网页研究、PDF/DOCX/XLSX、工作文件/报告版本、上下文管理、按需文档技能和 Agent 级追踪。**本地隔离业务/故障/浏览器/真实 Docker 计算、真实 DeepSeek 工具链及 Tavily→公网正文→引用报告均验收通过，当前版本已切换到 `http://localhost:5173`。** 用户确认演示数据无需备份，备份/回滚脚本和产物未保留。见 [本次验收](docs/phase1-acceptance-2026-11-06.md) 与 [架构说明](ARCHITECTURE.md)。

## 启动

需要 Docker Desktop Linux engine。Web 仅绑定本机 `http://localhost:5173`；PostgreSQL、Backend、Runtime 与 demo-mcp 为独立服务，默认不发布主机端口。

```powershell
# 项目根目录；首次生成随机秘密，拒绝覆盖现有 .env
.\scripts\init-env.ps1
# 如需真实模型，在本机被忽略的 .env 中设置 DEEPSEEK_API_KEY、
# REAL_CALL_BUDGET、REAL_CALL_BUDGET_SINCE 与 REAL_MAX_OUTPUT_TOKENS
.\scripts\dev.ps1
```

默认账号名称为 admin / user-a / user-b；密码读取本机被忽略的 `.env` 中 SEED_*_PASSWORD，没有公共默认密码。seed 可重复执行，已有账号密码不会重置。不要分享 `.env`、容器环境或真实 Key。

`make dev` 等价于构建、各自迁移、seed 和启动；`make stop` / `docker compose down` 保留卷。请勿使用 `down -v`，除非明确要销毁该项目数据。迁移和首次角色初始化是两步：修改已有卷的数据库密码不能仅改 .env。

Windows 脚本会查找 PATH 中 docker 或 Docker Desktop 默认安装位置。若 Docker Hub 不可达，可在本项目 .env 设置 DOCKER_REGISTRY；不是全局 Docker 设置。

## 页面

### 个人连接

平台模型、搜索和公共 MCP 继续在管理端配置。麦当劳中国在「工具 → MCP」提供个人安装，用户填写自己的 Token，验证工具清单并明确确认授权范围。对话顶部 MCP 面板可选择本轮连接，也可原地安装和管理，保留当前草稿。查询可直接执行，写操作和风险未核实的工具需要逐次确认。工具页“去使用”只填写草稿并选择能力，发送时才创建运行。

首次启用请在项目目录执行 `./scripts/init-connection-secret.ps1`，然后启动或重建项目。该脚本只为当前部署生成加密主密钥，并保存到已被 Git 忽略的环境配置。隔离验证使用 `-Verification`。已配置的密钥需要随部署保留。轮换时将旧密钥保留在密钥环，切换 active key ID 后通过刷新并重新确认授权来更新既有密文，确认更新完成后退役旧密钥。

「管理控制台 → MCP」可以发布或隐藏部署已准入的个人连接器，编辑名称、简介、分类、图标和 Token 获取链接。服务地址、认证类型和工具风险来自部署准入配置。个人 Token 独立存储，迁移不会把此前的共享麦当劳 Token 分给任何用户。模型与环境状态位于「设置」，能力组合检查收进高级诊断；旧技能与能力设置地址兼容跳转到工具页。

- `/app/chat`：会话、模型/技能/资料选择、流式消息、工具结果、审批卡、取消和产物。
- `/app/library`：上传、搜索、预览、下载和引用资料。
- `/app/scenes/data-analysis`：CSV 固定聚合、柱状图/折线图与模型解读。
- `/admin/models`、`skills`、`mcp`、`users`、`audit`、`runs`：管理员控制面。

## 职责与配置

React 只展示与发起操作。Go Backend 保存用户、配置、提交/决定/工单、原始文件与解析缓存。Python Runtime 运行 DeepAgents/LangGraph、标准 ChatModel、逻辑工具网关、按需固定文档子进程与 canonical events/checkpoint。两个服务使用独立 PG schema 与数据库角色；文件存储只挂载给 Backend，新 saver 使用 runtime_harness_v2。未复用或修改本机其他项目 PostgreSQL，见 [数据库决策](docs/decisions/004-local-postgres.md)。

完整组件、调用链和数据边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。

根目录的 `compose.yaml` 是唯一正式运行栈。`tests/compose/` 只保存有明确用途的隔离验收覆盖层：测试端口、隔离镜像、Mock 模型、故障注入、网页夹具和真实调用预算；不得将这些覆盖层用于日常环境。仓库使用 Gitleaks 扫描完整提交历史，真实凭据只能通过本机被忽略的 `.env` 或启动进程环境注入。

`deploy/targets.json` 是确切地址/路径、凭据别名、MCP 工具分类与速率的准入表，不含 Key。模型按协议配置，首选 DeepSeek；平台标签不决定适配器。真实 Key 仅注入 Runtime。网页配置检查只验证声明与部署状态，不执行付费探测。MCP 发现的工具默认禁用；只读工具可明确启用，写工具即使启用也必须逐次审批，未列工具保持阻断。

工具链：Node 22 / pnpm 11.25.0、Go 1.25、Python 3.13 / uv 0.8.10；依赖锁文件齐全。`make install` 安装本地依赖，`python scripts/generate-contracts.py` 生成 Go/Python/TS 契约。共享源在 schemas/，不要手改生成副本。`pnpm dev` 是前端单独开发模式，需要本机 Backend :8080；完整运行推荐 Compose。

## 验收入口（执行需明确授权）

```powershell
# 配置独立 .env.test（端口 5174，独立随机秘密）后
.\scripts\verify-mock.ps1 -Authorized
# 全新项目/卷/秘密，端口 5175；存在同名卷时拒绝覆盖
.\scripts\verify-mock.ps1 -Authorized -Fresh
# 首次验收中断后在该验收卷继续，不再宣称重新创建空卷
.\scripts\verify-mock.ps1 -Authorized -ResumeFresh -SkipBuild
# 第一阶段完整隔离回归（含旧功能），仍需明确授权
.\scripts\verify-phase1.ps1 -Authorized
# 另行授权可选 Docker 计算隔离验证，含前置回归
.\scripts\verify-compute.ps1 -Authorized
```

`make verify-mock` 调用同一 PowerShell 入口；系统需有 pwsh。脚本默认停止测试服务并保留证据/卷；`-KeepRunning` 保留供浏览器验收。Mock 只替换模型，MCP、审批、数据库、文件和业务写入均是真实模块。Runtime 在验收环境拒绝真实模式；`tests/compose/isolated-stack.yaml` 中的占位凭据不是可用 Key。

真实验收另行授权请求数与 token 上限；`tests/compose/real-model-budget.yaml` 可对本次时间窗口设置总调用上限，凭据不进入该文件。脚本 `accept-delivery-real.py` 仅供明确授权且预算保护已配置的环境，勿作为常规回归自动执行。发生错误不会静默转 Mock。

若复用外部 Langfuse 部署，运行 `bootstrap-personal-langfuse.ps1` 时必须通过 `-LangfuseCompose`、`-LangfuseEnv`（或同名环境变量 `LANGFUSE_COMPOSE_FILE`、`LANGFUSE_ENV_FILE`）显式提供路径；仓库不包含也不假定任何个人电脑目录。

## 交付说明

[完整链路与五段演示](docs/delivery-guide.md) · [验收报告](docs/acceptance-report.md) · [任务进度](docs/plan-v2/TASKS.md)

后续方向：[从 Demo 到个人助手的四阶段路线](docs/plan-v3/ROADMAP.md)（P1 已完成并切换 5173，P2–P4 尚未实施）。

第一阶段：[详细执行方案](docs/plan-v3/PHASE1-EXECUTION.md) · [S08–S15 任务清单](docs/plan-v3/TASKS.md)。

重构细化：[替换/保留/删除清单与实施顺序](docs/plan-v3/PHASE1-REFACTOR.md)。

支持单实例和有限审批恢复，不承诺任意断点续跑、生产高可用或企业治理。生成代码仅可进入默认关闭的隔离计算服务；不在 Runtime 或主机直接执行。本地计算隔离验收已通过，日常 profile 仍关闭。文件/图表限制、UNKNOWN 结果以及取消不能回滚已完成写入等边界详见第一阶段交付说明。


旧版本业务验收：[2026-11-04 完整业务回归与缺陷修复](docs/regression-2026-11-04.md)。本次重构不沿用该报告作为通过证据。
