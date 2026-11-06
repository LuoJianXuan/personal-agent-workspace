# 最新版本业务回归 · 2026-11-04

结果：通过。实现状态：代码齐备；验证状态：运行通过（首版范围，隔离 Mock）。本轮真实模型请求 0 次。

用户授权：对最新版本做完整业务回归并修复发现的问题。数据分析维持现有产品设计，只检查现有行为。

## 环境与覆盖

- 日常环境 agent-workspace / 5173 保留原有数据、配置和 Runtime；写操作与故障注入全部在 agent-workspace-verification / 5174。
- 使用已有隔离卷，执行迁移和重复 seed，不宣称本轮重新验证空库首次安装。
- Mock 只替换模型输出；Backend、Runtime、LangGraph、PostgreSQL、MCP、审批、文件、SSE 和浏览器交互均使用真实模块。
- 当时尚无可用 Git commit；公开仓库建立后统一使用 commit 标记版本，临时源码 SHA256 清单不再作为发布文件。

## 自动化回归结果

| 套件 | 通过组数 | 主要覆盖 |
|---|---:|---|
| Day 2 | 13 | 登录、后台 CRUD、模型协议与默认项、Skill 偏好、MCP 发现/启用、撤权、审计脱敏 |
| Day 3 | 9 | 多轮、幂等、流式、断线补读、工具调用、并发限制、离线派发、中断状态 |
| Delivery | 6 | 并发审批仅写一次、等待点重启、拒绝/取消、文件授权、统计、产物与报告幂等 |
| Faults | 10 | 过期、等待发布边界、决定持久化、写响应丢失、UNKNOWN、取消竞争、撤权、存储失败 |
| Boundaries | 6 | 文件边界/越权、avg/count、取消与批准竞争、满队列恢复、隐私审计 |
| Storage | 2 | 不可写存储、物理对象缺失、恢复后下载哈希 |
| Streams | 2 | 每用户/全局订阅上限、心跳、未读取订阅与管理请求响应 |

合计 **48 组**集成与故障检查；每组包含多个断言，不能将组数理解为 HTTP 请求数。

另外通过：Backend `go test ./...`；Runtime 模型协议 6 项及材料计算 5 项；Web `tsc -b && vite build`。构建保留已有大包提示。

Backend 测试首次在仅包含服务目录的构建镜像中缺少共享 schemas 样例；随后只读挂载完整个人项目，在禁网容器中执行全包测试通过。该失败属于验收环境路径问题。

## 发现、修复与复测

1. **手机新建会话后抽屉没有关闭。** 390×844 打开近期会话抽屉并新建，路由切换后抽屉仍遮住输入区。创建成功后关闭抽屉、清空草稿；复测抽屉关闭且可输入。
2. **运行中回看旧轮次错误释放发送状态。** 第二轮 `mock:long` 生成时查看上一轮过程，页面按旧轮显示完成并允许继续发送。当前任务完成前禁用过程切换；原有历史正文仍可阅读。复测运行时切换禁用，完成后恢复，取消按钮收敛。
3. **Runtime 离线时最新已保存回答消失。** Backend 历史有三轮消息，刷新时最新一轮仅依赖事件重放，因此无法显示。现在优先显示历史投影中已持久化的最终回答，流式草稿与最终投影去重；历史 `run.started` 也不再把已完成状态倒退成运行中。停止测试 Runtime 后刷新，最新回答可见且只显示一份；恢复后正常同步。

产品代码改动仅在 `apps/web/src/chat.tsx`；新增两个隔离浏览器数据准备/核对脚本。没有改共享 API、数据库契约或模型凭据。

## 浏览器业务回归

普通用户登录与后台路由拒绝；管理员创建技能并搜索，前台搜索、启用、查看正文；首页首次发送建会话、多轮流式与最终去重；运行中禁用过程切换；离线历史刷新；手机会话抽屉；MCP 查单与完整审批参数、批准后继续；报告导出、右侧产物及实际下载；文件选择器上传 CSV；CSV 表单选择字段、提交并显示东区 15/西区 3；资料引用与真实读取工具；Markdown 安全预览；失败草稿与错误提示；生成期间取消并收敛至 CANCELLED。

后续权威 API/数据库交叉核对：三轮会话恰好三份最终回答；浏览器批准产生恰好一张合成工单；图表绑定浏览器上传的文件并保持预期数值。详细记录：[ui-data-results.json](evidence/regression-2026-11-04/ui-data-results.json)。

| 证据 | 路径 |
|---|---|
| 汇总及 14 组浏览器操作记录 | [summary.json](evidence/regression-2026-11-04/summary.json) |
| 抽屉修复前／后 | [before](evidence/regression-2026-11-04/mobile-new-before.jpg) / [after](evidence/regression-2026-11-04/mobile-new-after.jpg) |
| 离线历史修复前／后 | [before](evidence/regression-2026-11-04/offline-history-before.jpg) / [after](evidence/regression-2026-11-04/offline-history-after.jpg) |
| 实际上传文件的统计图表 | [analysis-after.jpg](evidence/regression-2026-11-04/analysis-after.jpg) |

新回归的原始结果都归档到 `docs/evidence/regression-2026-11-04/`；旧 Day 4–7 证据保留原值，避免把历史验收报告链接改成另一轮数据。

## 主要命令

```powershell
./scripts/verify-mock.ps1 -Authorized -KeepRunning
# Backend 构建 stage 镜像；只读挂载个人项目完整目录，--network none 执行 go test ./...
python -X utf8 scripts/accept-regression-ui-fixture.py
# 浏览器通过 cua_repl 真实交互；不以 API 请求冒充 UI 操作。
python -X utf8 scripts/accept-regression-ui-state.py
# Web 单独更新到日常环境，保持 Runtime、配置和凭据不变。
docker compose -p agent-workspace up -d --no-deps web
```

## 结论与限制

修复后的同一 Web 镜像已更新到 5173，首次使用请刷新页面。本轮通过的是首版业务与故障范围；没有重新请求真实模型供应商，没有验证生产多副本、高可用、灾备或其他模型协议。后台配置 CRUD/权限由接口全回归覆盖，页面重点补测“后台创建技能 → 前台启用与查看”的链路，并非逐字段穷举所有后台表单。
