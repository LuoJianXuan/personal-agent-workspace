# 任务清单

日期 2026-11-16。新版已在本机 5173 运行。验证列记录各项实测结果，详见 [本机验收](../../../docs/evidence/PC-VERIFY.md) 和 [发布记录](../../../docs/evidence/PC-RELEASE.md)。

实现状态：未开始 / 实现中 / 代码齐备 / 需修复。验证状态：未执行 / 静态核对 / 运行通过 / 运行失败。完成实现不能直接勾选运行验证；每个任务的证据分别记录。

## 依赖与交付批次

| 顺序 | 任务 | 依赖 | 可交付结果 | 实现 | 验证 |
| --- | --- | --- | --- | --- | --- |
| 1 | PC-CON | 无 | 契约、权限和兼容语义冻结 | 代码齐备 | 运行通过 |
| 2 | PC-DATA | PC-CON | 所有权和版本化数据库结构 | 代码齐备 | 隔离升级运行通过 |
| 3 | PC-SEC | PC-DATA | 加密存取、隔离与轮换 | 代码齐备 | 加密单测与隔离执行通过 |
| 4 | PC-CONNECT | PC-SEC | 个人连接、发现、授权生命周期 API | 代码齐备 | 连接与无效 Token 运行通过 |
| 5 | PC-POLICY | PC-CONNECT | 批量工具授权和用户有效目录 | 代码齐备 | 隔离与管理员发布运行通过 |
| 6 | PC-RUN | PC-POLICY | Gateway 个人凭据执行闭环 | 代码齐备 | 只读、写审批与撤权运行通过 |
| 7 | PC-SKILL | PC-POLICY、PC-RUN | Skill 混合依赖及缺失处理 | 代码齐备 | 运行通过 |
| 8 | PC-WEB | PC-CONNECT、PC-POLICY、PC-RUN、PC-SKILL | 连接卡、弹窗、对话与审批交互 | 代码齐备 | 浏览器连接授权和对话通过 |
| 9 | PC-MIG | PC-DATA、PC-RUN、PC-WEB | 旧数据兼容迁移与正式配置就绪 | 代码齐备 | 隔离重建、正式升至 009、旧共享停用通过 |
| 10 | PC-VERIFY | 前述所有任务 | Mock、隔离与真实只读联合证据 | 代码齐备 | Mock 回归、浏览器真实 DeepSeek/MCP、Langfuse 入库通过 |
| 11 | PC-RELEASE | PC-VERIFY | 正式 5173 切换与重建后复核 | 代码齐备 | 正式实机复测、配置与授权持久性通过 |

内部可分三批交付：基础与 API（PC-CON～PC-POLICY）、运行与交互（PC-RUN～PC-WEB）、迁移与发布（PC-MIG～PC-RELEASE）。必须完整完成最终闭环才算本变更交付，不能只上线连接按钮。

## PC-CON：冻结契约

**前置**：无。**输入**：现有 Snapshot/Start/Mcp/Skill/Submit、现有审批字段和本方案。

**边界与工作**：修改 `schemas/jsonschema/contracts.json`、`schemas/openapi.yaml`、共享样例；定义 scope/source/owner、connection/grant/credential/catalog 版本、Token writeOnly DTO、公开状态、错误码、内部秘密响应。补 Snapshot schema_version 和 Skill dependencies。明确“未知工具需确认”与“明确禁止”区别。生成 Go/Python/TS，禁止手改生成副本。

**完成结果**：所有消费方使用同一权限与版本语义，秘密字段与安全 DTO 分离。

**失败边界**：旧 Snapshot 解析不能因新增必填字段直接失败；新个人快照不能被旧代码解释成平台连接。

**验收**：合法/非法样例、owner 伪造、DTO 额外字段、旧/新版本兼容和 Token 不回显契约检查。

**证据**：`docs/evidence/PC-CON.md`。

## PC-DATA：数据与身份隔离

**前置**：PC-CON。**输入**：既有 007 数据库与平台 MCP 记录。

**边界与工作**：Backend 下一增量迁移、connector/connection 数据访问模块；建立 definitions、encrypted credentials、grants、access operations；扩展现有 mcp_connections/mcp_tools，保留 ID。为 user owner 和 active connection 设置约束与索引。旧 MCP 显式标为 platform，麦当劳旧连接记为迁移例外。

**完成结果**：数据库中可以区分平台连接和每位用户的个人连接；历史记录仍可读取。

**失败边界**：不自动为用户授予共享个人 Token；不删除旧文件、审批或 Run；非法 scope/owner 组合拒绝落库。

**验收**：旧库升级、空库、重复迁移、唯一约束、同名工具不同连接、A/B 访问隔离；下一迁移编号以实施时仓库为准。

**证据**：`docs/evidence/PC-DATA.md`。

## PC-SEC：个人凭据模块

**前置**：PC-DATA。**输入**：主密钥注入配置、连接 owner 与版本。

**边界与工作**：建议新增 `services/backend/internal/credentials/`；AES-GCM、AAD、随机 nonce、candidate/active 切换、key_id 轮换；主密钥只给 Backend。HTTP 日志和错误处理禁止序列化秘密 DTO。内部解析接口使用已有服务认证并校验持久授权发放记录。默认无凭据读取管理 UI。

**完成结果**：数据库只保存密文，API 只返回状态；重建后可解密，换 Key 可控。

**失败边界**：错 key_id/主密钥缺失/密文移动/密文损坏明确失败，平台能力不受影响；不临时生成新主密钥掩盖配置丢失。

**验收**：密文非明文、随机化、AAD 跨用户失败、轮换前后读取、重建不丢失、公开 API/异常/日志不回显。

**证据**：`docs/evidence/PC-SEC.md`。

## PC-CONNECT：用户连接生命周期

**前置**：PC-SEC。**输入**：预置麦当劳 definition、固定 target 和新接口契约。

**边界与工作**：建议新增 `backend/internal/connectors/` 与 Runtime 发现适配；实现 /catalog/connectors、/me/connections、probe/operation/grant/credential/disconnect。发现 operation 有期限，支持轮询；进程重启后挂起 operation 转 interrupted/unavailable，不永久显示 loading。换 Token 用候选验证，确认后切换；取消/超期清理候选。

**完成结果**：可以完成“输入 Token → 发现 → 授权 → ready”，并能断开、重连、换 Token。

**失败边界**：401 与超时区分；认证错误不能删除旧有效凭据；body 不可自定义 URL/Header/owner；重试创建不重复连接。

**验收**：正确/错误 Token、发现超时、取消、重启、revision 冲突、幂等、候选过期、换 Token 失败保留旧连接。真实远程操作限发现和明确只读调用。

**证据**：`docs/evidence/PC-CONNECT.md`。

## PC-POLICY：批量授权与能力解析

**前置**：PC-CONNECT。**输入**：工具清单、平台 policy、用户 grant。

**边界与工作**：修改 `control/mcp.go`、`capabilities.go`、`execution.go`；将全局 `enabledTools` 改成身份相关解析；实现全能力/仅查询授权、直接执行/需确认/禁止、目录 hash 与增量授权。普通 catalog 与 Run Snapshot 使用同一 resolver；保留平台规则并阻止个人凭据回退。

**完成结果**：个人连接一次授权后可用工具完整可见；权限不能跨用户，更新只影响对应工具/连接。

**失败边界**：readOnlyHint 不能直接扩大权限；确认当前清单后新增工具不得自动启用；授权模式切换不能追认旧待审批请求。

**验收**：A/B 不同目录和不同 Token、平台工具共同可用、个人目录不含平台共享麦当劳、陌生工具需确认、禁止项无执行入口、增量/删除/改 schema/改说明、快照撤权。

**证据**：`docs/evidence/PC-POLICY.md`。

## PC-RUN：个人 MCP 执行闭环

**前置**：PC-POLICY。**输入**：Snapshot 引用、内部执行材料接口、现有 Tool Gateway/HITL。

**边界与工作**：修改 `runtime/app/access.py`、`tool_execution.py`、`tool_worker.py`、`mcp_worker.py`、`errors.py`、`approvals.py`、`observability.py` 及对应 Backend 授权接口；最小 worker 环境、局部 Token、输出/错误清洗。审批绑定连接/凭据/grant 版本；维护 execution 幂等、取消、限流、UNKNOWN 和 canonical events。不要把 Token 作为 LangChain 工具参数。

**完成结果**：DeepAgents 使用当前用户连接完成真实任务，平台工具继续原路执行。

**失败边界**：暂停期间换 Token/断开/撤权必须拒绝旧审批；上游执行结果未知不得自动重放；秘密解析失败不能回退其他身份。远端已提交的操作不能承诺取消成功。

**验收**：无审批写工具零执行；批准一次只执行一次；参数变动、跨用户、撤权竞态、取消、超时、限流、重启恢复；恶意服务回显 Token 时事件/结果/checkpoint/trace 无秘密。Mock 模型但使用真实内部模块与合成 MCP。

**证据**：`docs/evidence/PC-RUN.md`。

## PC-SKILL：混合依赖

**前置**：PC-POLICY、PC-RUN。**输入**：Skill dependencies 与原 Skill 版本/加载机制。

**边界与工作**：Backend Skill 配置/依赖 resolver、Runtime 安全依赖摘要；引用稳定 definition/capability ID。必需依赖阻止提交并返回结构化原因，可选缺失明确传给 UI/Agent；旧 Skill 默认无依赖。

**完成结果**：管理员发布的 Skill 可以组合平台工具与用户自己的连接，Skill 不保存个人 Token/connection_id。

**失败边界**：发布 Skill 不替用户授权；可选能力缺失不能伪造完成；循环 Skill 依赖不开放。

**验收**：平台-only、个人-only、混合、必需缺失、可选缺失、Skill 更新和禁用、旧 Skill 兼容。使用合成服务验收，无需增加真实 Tavily 调用。

**证据**：`docs/evidence/PC-SKILL.md`。

## PC-WEB：能力页与对话

**前置**：PC-CONNECT、PC-POLICY、PC-RUN、PC-SKILL。**输入**：安全 catalog 与错误码。

**边界与工作**：`apps/web/src/control.tsx`、`chat.tsx`、路由与可复用连接组件；平台提供/我的连接/技能视图，Token 弹窗、权限摘要、全部能力/仅查询选择、工具详情、变化确认、换 Token、断开；对话缺失连接入口、保留草稿、友好工具名称和参数审批。

**完成结果**：用户无需管理员介入或逐个工具开关即可连接麦当劳、查询活动，写操作按次确认。

**失败边界**：Token 不进入 URL/浏览器持久存储/console；不能把“已配置”显示成“实时健康”；连接成功不自动发送草稿或自动下单。

**验收**：真实浏览器验证管理员平台配置、A/B 用户连接流程、401/超时、工具变化、审批、退出账号后不残留账户状态、390px 窄屏。测试必须按仓库规则获得运行授权。

**证据**：`docs/evidence/PC-WEB.md`。

## PC-MIG：迁移与部署配置

**前置**：PC-DATA、PC-RUN、PC-WEB。**输入**：旧部署级 MCP、既有 5173 与忽略的本机 secret 配置。

**边界与工作**：更新 `.env.example`、Compose 只透传配置名、迁移说明、开发指南；个人主密钥只给 Backend；平台 Key 继续留 Runtime；验证模式开关。旧麦当劳不分配 owner，隔离为 legacy。确认 Langfuse 专用 Key 持久配置，不创建新项目/Key 除非确有必要且已获授权。

**完成结果**：容器重建后凭据/授权仍有效，平台能力不因个人连接开关失败；部署说明准确。

**失败边界**：不自动扩大 DeepSeek/Tavily 预算，不删库/卷，不新增备份回滚脚本；旧版不识别 owner 的代码不能直接读个人连接。

**验收**：带旧记录迁移、幂等、legacy 排除、开关关闭、重建与密钥轮换；不识别新 scope 的旧版本阻止发布/回退。

**证据**：`docs/evidence/PC-MIG.md`。

## PC-VERIFY：完整验收

**前置**：全部实现与迁移入口齐备。**输入**：[acceptance.md](acceptance.md)。

**边界与工作**：准备 `scripts/accept-personal-connections.py` 等验收入口及合成 MCP 场景，验证连接、授权、真实 Runtime、数据库与审批闭环。按授权执行 Mock 全回归、A/B 隔离、浏览器与少量真实 DeepSeek/MCD 只读链路；真实写操作全部禁用。

**完成结果**：逐项成功/失败证据、调用次数、token 使用、工具次数和 trace 入库证据，明确哪些未执行。

**失败边界**：不能用 API 代替浏览器测试、Mock 模型代替真实 DeepSeek、trace URL 代替 trace 实际入库。未获额度或出现错误则相应项保留未通过。

**验收**：acceptance.md 中所有发布必需项通过，错误 Token/超时/撤权/秘密回显无泄露。

**证据**：`docs/evidence/PC-VERIFY.md` 与脱敏机器结果。

## PC-RELEASE：正式切换

**前置**：PC-VERIFY 全部门槛通过。**输入**：最终代码、迁移、正式部署配置和未超额调用窗口。

**边界与工作**：排空活动 Run，迁移并按兼容顺序启动 Backend/Runtime/Web，切换 5173，核对旧麦当劳连接已移出普通目录、用户个人连接正常；再次重建 Runtime 检查平台配置和 Langfuse。更新 README、ARCHITECTURE、原变更的被替代范围，记录最终证据。

**完成结果**：正式用户可连接自己的麦当劳并完成活动查询；平台公共功能保持可用；用户看到的是新产品流程。

**失败边界**：阶段切换不等于 Git 提交/推送授权；任何验收未通过不得标发布完成，关闭功能开关不得重新暴露共享个人 Token。

**验收**：正式页面、健康检查、持久凭据、配置状态、用户隔离和一条授权的只读真实任务复核。真实复核消耗计入本轮总额度，不另行无界追加。

**证据**：`docs/evidence/PC-RELEASE.md`。
