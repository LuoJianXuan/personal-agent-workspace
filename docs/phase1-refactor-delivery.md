# 第一阶段重构交付记录

实施：2026-11-05 至 2026-11-06。范围：独立个人 Demo 的 S08–S20。**代码、隔离回归、真实 DeepSeek/Tavily 工具链和日常 5173 切换均已完成。** 详情以 [本次验收报告](phase1-acceptance-2026-11-06.md) 为准，不沿用历史报告作为新底座通过证据。

仅修改 agent-workspace，公司灵机 AI 未改。交付末尾已初始化 Git 仓库；公开版本统一由 commit 定位，不再保留实现期间生成的重复源码 hash 清单。隔离验收位于 5174，当前日常入口为 5173。

## 交付与验证

| Spec | 已实现能力 | 本次实际验证 / 未执行范围 |
| --- | --- | --- |
| S08 | 锁定依赖、共享契约/生成副本、v5、新 checkpoint schema | Linux 镜像/服务、迁移保护与重复执行通过；随后日常迁移和切换通过 |
| S09 | 实际 DeepAgents、标准模型集成、官方 HITL/限次、应用治理 | 既有 48 组业务/故障/权限回归、审批恢复/取消/流式/UNKNOWN；后续真实 DeepSeek DOCX/MCP 工具链通过 |
| S10 | 搜索/正文/来源/引用报告 | 显式 fixture 回归与 SSRF 边界通过；后续真实 Tavily 搜索→IANA 正文→引用报告及 Langfuse 三工具节点通过 |
| S11 | 首页、会话组织、任务/来源/上下文展示 | 17 项浏览器操作通过，桌面与390×844窄屏、下载/审批/取消/刷新；非生产性能认证 |
| S12 | PDF/DOCX worker、受控工作文件、定位/版本 | 实际文字 PDF/DOCX、授权隔离、原生 write/edit/read、修订和 v1/v2 通过；OCR 不支持 |
| S13 | 官方长结果外置/摘要、统一请求硬限 | 实际触发外置/摘要/原始历史保存、摘要计费计数、12 次停止通过；未评估真实模型摘要质量 |
| S14 | XLSX Decimal、可选真实 Docker Python | XLSX东30/西7；8组隔离+2组全链路，实际输入4+9=13；取消/超时和零残留通过；日常默认关闭 |
| S15 | 实际 MD/DOCX/CSV/Chart、鉴权下载与版本 | 三类本地任务与导出/中文内容、浏览器37,157字节DOCX通过；固定真实研究闭环和日常迁移通过 |

分项链路与失败点见 [S08](evidence/S08.md) 至 [S15](evidence/S15.md)。23 个单元用例最终均通过（初次22/23，测试配置修复后定向1/1），其余结果和修复列表见验收报告；没有把组数相加当成不重复用例数。

## 框架替换结果

1. `harness.py` 装配 `create_deep_agent`，使用官方文件、任务清单、摘要、模型/工具限次及 HITL。Engine 保留接收、队列、终态和取消协调，不再构造旧 Agent 图。
2. `models.py` 使用标准 ChatOpenAI，保留协议配置、凭据目的地址、物理请求计数/限制与错误过滤；删除旧 SSE 逐行解析和工具参数碎片合并。小型子类仅将 SDK 的 `max_completion_tokens` 恢复为本项目协议使用的 `max_tokens`，不接管流解析。
3. 删除手写 model/prepare/approval/execute/merge 节点。原生 HITL/checkpointer/Command 处理等待恢复，应用仍校验 owner、参数 hash、权限版本、有效期、用户决定与写入幂等。

默认 shell/execute、通用 subagent、delete、自动长期记忆没有开放。只读 MCP、工单、资料和文件访问继续经过治理；`write_todos` 是框架计划状态。原件不能由工作文件工具覆盖。

产品 thread_id 仍是会话，私有 checkpoint 用 run_id 隔离单次运行并保留恢复计数。后续轮次读取既有历史和同会话工作文件，没有另建会话主线真相。

## 构建与证据

Windows 依赖安装/Go/Web 编译、Linux Docker 构建均通过；实际服务和 Agent 链路已在隔离项目运行。最终 Web 产物 `index-D8piSVuX.js` / `index-Ab0R6Yvj.css`，主 JS 约2.07 MB提示仍在。

[构建记录](evidence/phase1-build-checks.json) · [源码/契约](evidence/phase1-source-checks.json) · [单元结果](evidence/phase1-unit-results.json) · [环境](evidence/phase1-environment-results.json) · [浏览器](evidence/phase1-browser-results.json)。最初静态交付记录另存 [历史构建记录](evidence/phase1-build-checks-initial-static.json)，其“未运行”描述仅属于当时。

| 依赖 | 锁定版本 |
| --- | --- |
| DeepAgents | 0.7.13 |
| LangChain / core / openai集成 | 1.4.9 / 1.7.6 / 1.7.4 |
| LangGraph / checkpoint-postgres | 1.2.20 / 3.2.0 |
| OpenAI SDK / MCP / Pydantic | 3.46.0 / 1.26.0 / 2.14.2 |
| pypdf / python-docx / openpyxl / BeautifulSoup | 6.21.4 / 1.2.0 / 3.1.5 / 4.15.0 |

Runtime 构建用 uv0.8.10。MCP升级后显式固定 `/mcp/` 与 allowlist一致；没有为兼容而允许自动重定向。实际官方依赖与项目业务通过本次本地回归，不表示真实供应商已经通过。

## 边界

- 每轮最多3份文件，单份5 MiB。PDF文字提取最多100页，不做OCR；DOCX不还原完整排版。DOCX/XLSX ZIP展开32 MiB、最多5,000片段/2 MiB结果。XLSX最多10表/100,000单元格，只读公式缓存，不重算。
- 固定统计最多10,000行、50组、30列，Decimal计算，Chart由schema校验。独立数据分析场景按用户意见暂保留，通用对话也可调用。
- 工作文件按用户/会话隔离，最多100个/保留最近20修订；JSON写入256 KiB。正式产物使用不可变file_id，版本UI最多30层。
- 网页需要本轮显式允许与部署开关；每Run最多2次搜索/6次读取。公开HTTP(S)、DNS全结果及每跳复检/固定IP，拒绝私网/凭据/登录态；最多3跳/2 MiB/20秒，超过20,000字符标部分读取。fixture仅在明确测试模式按精确URL放行。
- 搜索摘要不能冒充已读正文；发布校验来源存在与权限，不等于语义和研究质量正确。
- 原生模型上限12/工具20，恢复不重置；物理模型请求硬限12，含摘要。活跃时间累计180秒，审批等待不计入；审批有效600秒。用量元数据不是财务账本。
- Python是可选固定依赖容器，禁网、非root、只读根、无socket/部署凭据、资源/时间限制。`/work` 为每任务私有受限tmpfs volume，`/tmp`为独立tmpfs，清理同时覆盖容器与任务卷。最多5输出/总10 MiB/单5 MiB，仅CSV/MD/DOCX/Chart JSON；XLSX仅输入。
- 可信broker拥有Docker socket，Runtime和生成代码容器没有。实际隔离证据已通过，但这是本机可选执行方案，不是生产企业多租户沙箱认证；日常compute profile保持关闭。
- 取消不回滚已提交写入；UNKNOWN保留对账，不自动重跑。单实例个人Demo，不承诺任意断点恢复或高可用。

## 重复验收与启用

```powershell
.\scripts\verify-phase1.ps1 -Authorized -KeepRunning
.\scripts\verify-compute.ps1 -Authorized -KeepRunning
```

验收使用独立 `.env.test` 与5174，不改日常库；默认停止服务/保留卷，KeepRunning保留。当前已依赖顺序分步执行所有报告中检查组、修复后定向复跑；顶层脚本的最后整段连续执行未重跑。真实模型和搜索不会静默切成Mock。

真实DeepSeek需新 `REAL_CALL_BUDGET`、带时区且不晚于当前时间的 `REAL_CALL_BUDGET_SINCE`、`REAL_MAX_OUTPUT_TOKENS`，每个物理请求占额度。联网需 `ENABLE_PUBLIC_WEB=true`；搜索另需 `TAVILY_API_KEY`、`SEARCH_CALL_BUDGET`、`SEARCH_CALL_BUDGET_SINCE`。直接URL正文不需Tavily凭据，但仍需联网许可。

Python日常启用需compute profile、专用runner镜像、`COMPUTE_BROKER_URL`及不少于32字符的token，凭据仅在部署环境。容器/镜像按Compose project隔离，不共享日常任务命名空间。本次验收后broker已停止，Runtime已恢复不带compute配置。

## 日常切换结果

当前 Backend、Runtime、Web、PostgreSQL 与 demo-mcp 已使用最新镜像运行在 5173；Backend/Runtime 迁移和 seed 完成，切换前后保持 6 个文件、13 个 Run、6 个 thread，管理员登录、会话读取、模型凭据和搜索就绪检查通过。发布过程没有调用真实模型或 Tavily。

用户确认现有数据均为演示数据，撤销备份/回滚脚本和归档要求；相关临时目录、镜像标签和演练资源均已删除。今后若存入真实个人资料，再发布前必须重新建立备份和恢复策略。切换证据见 [phase1-cutover-results.json](evidence/phase1-cutover-results.json)。
