# Day 4–7 完整验收报告

最新版本（2026-11-04）已执行完整业务回归并修复三个前端问题，参见 [最新回归报告](regression-2026-11-04.md)。下文保留 2026-11-03 的历史验收记录。

日期：2026-11-03，Asia/Shanghai。当前等级：首版代码齐备、Mock 核心闭环通过、DeepSeek 指定闭环通过。不是生产高可用或其他平台认证。

## 环境与版本

- 开发：agent-workspace，127.0.0.1:5173，真实模型；保留原数据库和文件。
- 隔离回归：agent-workspace-verification，5174；新环境：agent-workspace-fresh，5175。独立网络、PG/文件卷及随机秘密；未接触公司数据库或代码。
- fresh 首次确实创建了空卷并执行迁移/seed。中途发现脚本问题后使用同一验收卷续跑，如实记录为修复后续验，没有声称每次重试都是全新环境。
- Backend/Runtime schema version 4；公开仓库建立后统一由 Git commit 定位源码版本，不再提交容易过期的重复 SHA256 清单。
- 构建：Docker Compose 的 Go 编译、Python 锁定依赖、TS + Vite 通过；Go 全包测试通过；模型协议 6 项与固定统计/哈希 5 项单测通过。

## 已执行命令

```powershell
powershell -File scripts/verify-mock.ps1 -Authorized -Fresh -SkipBuild -KeepRunning
powershell -File scripts/verify-mock.ps1 -Authorized -ResumeFresh -SkipBuild -KeepRunning
# 修复后仅重跑失败阶段和相关边界：设置 WORKSPACE_TEST_ENV / PROJECT 为隔离项目
python scripts/accept-faults.py
python scripts/accept-boundaries.py
python scripts/accept-storage.py
python scripts/accept-streams.py
# 上述范围另外执行 Go tests、Runtime test_models.py / test_materials.py 和 Web build
```

完整入口 `verify-mock.ps1` 已包含所有阶段。浏览器使用 UI 操作单独验收，未把 API 测试冒充浏览器测试。

## A01–A27

| 项目 | 结果 | 验证行为 | 脱敏证据（docs/evidence） |
|---|---|---|---|
| A01 | 通过 | 新项目 fresh、空 PG/文件卷、迁移至 4、重复 seed、服务 ready；Day 1 证据补充迁移前 readiness。 | verify-mock.ps1 -Fresh；day1/day7 证据 |
| A02 | 通过 | 管理员/普通用户登录，管理接口 403，禁用后身份失效。 | day2-api-results.json |
| A03 | 通过 | 协议优先、受控选项、版本/默认模型、目录同步、凭据地址绑定；错误不降级。 | day2-api-results.json；test_models.py |
| A04 | 通过 | 技能 CRUD、个人偏好隔离、快照与版本更新。 | day2-api-results.json |
| A05 | 通过 | 真实 MCP SDK 初始化/发现/调用，默认禁用和显式启用。 | day2-api-results.json；day3-mock-results.json |
| A06 | 通过 | 模型/技能/MCP/用户撤权与工具参数、文件选择越权拒绝。 | day2-api-results.json；day6-boundary-results.json |
| A07 | 通过 | 完成前多个正文块、多轮历史、最终全文一致。 | day3-mock-results.json；day3-real-results.json |
| A08 | 通过 | Mock 仅替换模型；图、PG、真实 MCP、审批与文件均执行。真实错误明确返回。 | day3-mock-results.json；day6-real-results.json |
| A09 | 通过 | 同键同参重放、异参冲突、同 thread 忙状态。 | day3-mock-results.json |
| A10 | 通过 | Runtime 离线持久派发、同 run 重发无重复执行。 | day3-mock-results.json |
| A11 | 通过 | 未批准零工单，拒绝/过期收敛并释放 thread。 | day4-5-results.json；day6-fault-results.json |
| A12 | 通过 | 并发同意共享 decision_id，仅一张工单，冲突决定 409。 | day4-5-results.json |
| A13 | 通过 | 等待点重启保持提案；已保存决定在派发前重启可继续。 | day4-5-results.json；day6-fault-results.json |
| A14 | 通过 | checkpoint 已保存而 WAITING 未发布：重启核对等待点并发布；未发布提案不对外暴露。 | day6-fault-results.json |
| A15 | 通过 | 工单提交响应丢失查询原结果；查询不可达 UNKNOWN，不盲重写。 | day6-fault-results.json |
| A16 | 通过 | 取消/批准竞争；写入完成后取消保留实际结果；持久取消先于命令到达也收敛。 | day6-fault-results.json；day6-boundary-results.json |
| A17 | 通过 | 审批期间禁用模型，旧快照失败且零工单。 | day6-fault-results.json |
| A18 | 通过 | 正文断线游标补读不重不漏，失败草稿保留；刷新不重新提交。 | day3-mock-results.json；浏览器验收 |
| A19 | 通过 | 真实文件上传/预览/下载/hash、格式/编码/大小/行列限制、选入对话。 | day4-5-results.json；day6-storage-results.json |
| A20 | 通过 | 跨用户 thread/run/file/approval 拒绝，附件引用不能越权。 | day3-mock-results.json；day4-5-results.json；day6-boundary-results.json |
| A21 | 通过 | 重复报告同 ID、无新模型调用；DB/物理存储失败无 READY，缺失文件不伪成功。 | day4-5-results.json；day6-fault-results.json；day6-storage-results.json |
| A22 | 通过 | sum/avg/count、bar/line 与固定值核对；UI 图表显示来源与统计口径。 | day4-5-results.json；day6-boundary-results.json；day7 UI |
| A23 | 通过 | 脱敏 Run 元数据、审批/写入审计可关联，无私有正文或秘密泄漏。 | day6-boundary-results.json |
| A24 | 通过（限 DeepSeek） | 本轮 8 次 provider 请求：7 次成功、1 次占位凭据 401；全部未超输出配置 512。真实审批、文件和统计解读通过；429/超时/截断用 fixture 验证。 | day6-real-results.json；test_models.py |
| A25 | 通过 | 受控地址、非法文件 ID/未授权文件拒绝；Markdown 脚本、图片事件与 javascript URL 不执行。 | day2-api-results.json；day6-boundary-results.json；day7 UI |
| A26 | 通过 | 重启后配置、历史、文件、等待点仍可读取。 | day2-api-results.json；day6-fault-results.json |
| A27 | 通过（功能边界） | 每用户 4 / 全局 32 SSE、33rd 429+Retry-After、心跳、未读取订阅不阻塞管理/普通 Run；队列 32、等待释放 4 槽、满队列恢复不丢决定。 | day3-mock-results.json；day6-stream-results.json；day6-boundary-results.json |

## 本轮发现并修复的问题

1. 工具快照以 JSON 字符串比较，JSONB 重排键导致误报 CAPABILITY_CHANGED。改成 JSON 结构比较，复验审批和文件链路。
2. Backend 重建后 Nginx 缓存旧容器 IP 返回 502。改用 Docker DNS 定期解析，容器重建后复验。
3. 旧 Day 2 回归脚本重启服务时漏带 Mock override，导致 fresh 的一次调用使用占位凭据收到 401。统一各阶段 Compose 列表，Runtime 在 Mock-only 环境直接拒绝 real 入场，已验证无网络旁路。
4. Backend 已持久取消而 Runtime 尚未收到命令便重启，会错误终结为 INTERRUPTED。终结前核对 Backend 持久取消，已复验为 CANCELLED，已写工单仍可核查。
5. API 原先可以列出尚未发布的提案。现在只有证明等待点后设置 published，列表和外部提案读取均要求 published。
6. 初次派发短暂 404 提示残留；恢复后清除暂时不可达提示。固定 CSV 场景显式使用空技能列表，避免无关的个人偏好超限阻断场景。
7. 长会话列表增加滚动高度限制；工具输出及来源字符串允许换行。已完成空白消息卡片隐藏修复继续保留。

测试脚本本身也修正了取消 202、非法附件引用 409、默认模型禁用规则、启动健康等待以及把 TOKEN_TTL_HOURS 当秘密的误判；没有为了通过而删除产品错误路径。

## 真实模型预算

本轮授权最多 8 次请求、每次输出上限 512 tokens。实际 **8 次**：7 次使用授权 Key 成功，另 1 次隔离环境占位凭据请求返回 401（纳入总数，没有另行追加）。详细 revision、run_id、每次 usage 在 [真实记录](evidence/day6-real-results.json)。未读取供应商账单，因此不提供未经核实费用；其他 provider 未验证。

首轮真实模型选择先文字征询，后续在同一会话明确“调用工具提交提案，由系统审批卡等待决定”后完成真正的审批。没有把文字确认当已审批，也没有绕过网关。

## 浏览器验收

- 隔离用户登录、新建会话、完整工单参数与绑定信息展开、批准后 SUCCEEDED、报告生成与浏览器实际下载。
- 资料库进入 CSV 场景，选择分组/指标/单位并提交，在同一聊天链路展示华东 15、华北 3 的柱图、来源文件与统计方式。
- 恶意 Markdown 预览：无脚本节点、图片事件或 javascript 链接执行，无 JS 弹窗。
- 390×844 窄屏：导航抽屉可开关，场景表单可操作，document scrollWidth 与 clientWidth 均为 375，无横向溢出。
- 最终开发环境只读查看已完成的真实模型结果；没有追加模型调用。

## 局限与未执行

未验证多副本 Runtime、灾备、生产吞吐、操作系统级网络饱和/断电、更多 provider 与协议。32 个受控 HTTP 订阅用于功能边界，其中未读取客户端不等同于生产极慢网络压测。构建存在前端大包提示。首版只提供受控工具和有限审批恢复，普通运行崩溃不会自动重新调用模型。

详细设计和五段演示见 [交付说明](delivery-guide.md)。真实 Key 不在源码、报告或快照；本地 .env 属于部署秘密，不应分发。

最终截图：[真实分析页面](evidence/day7-real-analysis.png)、[窄屏导航](evidence/day7-mobile-menu.png)、[窄屏表单](evidence/day7-mobile-analysis.png)。浏览器记录：[day7-ui-results.json](evidence/day7-ui-results.json)。

参考核对：[Nginx resolver](https://nginx.org/en/docs/http/ngx_http_core_module.html#resolver)、[ECharts 入门](https://echarts.apache.org/handbook/en/get-started/)。
