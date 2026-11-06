# 005 — 按协议适配模型，以 DeepSeek 作为首个接入实例

日期：2026-11-03。状态：按用户反馈修订为协议优先；S02 配置与契约已实现并验收，S03 模型调用待实现。
本次修订撤销将 protocol + adapter_profile 作为联合选择键的方案，取消必填的平台专用 profile。
范围：独立个人项目 agent-workspace；不修改灵机 AI 公司仓库，不部署 NewApi。

## 结论与当前事实

保留 Web → Backend → Runtime → ModelAdapter → provider 的结构，在 Day 2 前补齐配置与适配边界。无需重做 Day 1 的认证、数据库和部署。

S02 已将协议、协议选项、能力及输出上限落实到权威 schema、三端 DTO 和配置管理；Runtime 已实现配置状态与真实 MCP 发现，尚无真实模型适配器。不能把配置管理完成称为已接通 DeepSeek。

本文件描述目标设计；S02 实现与实际证据见 [S02 报告](../evidence/S02.md)。S03 仍须实现协议适配器及真实模型验证。

## 三个决策

1. DeepSeek 官方接入是首个交付与验收目标；先完成文本聊天、真实流式和非思考模式工具闭环。模型 ID 是管理员输入的供应商模型名，不在业务代码或模型名正则中写死。
2. 仅按 protocol 选择适配器；provider 是可选展示元数据，不能改变调用路径。平台预设只帮助填入地址与协议选项，解析后必须形成可查看的显式配置。首版实现 openai_chat_completions，其他协议按需增加适配器。
3. 首版保留一条模型配置记录，配置与运行快照有明确边界。暂不增加独立渠道表、网关进程、自动路由或故障换模型；多模型共享凭据可以复用部署别名。需要多渠道、独立渠道权限或批量轮换时，再拆连接与模型表。

## 配置与契约目标（S02 先落实）

| 字段 | 含义与限制 |
| --- | --- |
| id/name | 内部配置 ID、用户可读名称 |
| provider | 可选的平台标识，例如 deepseek、dashscope；用于展示与检索，不参与适配器选择，不是模型品牌 |
| protocol | 首版仅允许 openai_chat_completions；其他协议只有在适配器实现并注册后才允许保存为可用配置 |
| protocol_options | 可选、有严格 schema 的协议扩展参数，默认空对象；首版仅允许 thinking.type=disabled。DeepSeek 连接显式配置该选项，其他地址仅在已确认支持时使用；不根据 provider 自动注入 |
| provider_model_name | 平台实际模型 ID；在百炼上使用 DeepSeek 模型时 provider 仍是 dashscope |
| base_url | SDK/客户端基础地址，按适配器规则构造请求路径，不能简单对所有平台重复追加 /v1；HTTPS、部署 origin/path 准入，禁止重定向携带密钥 |
| credential_ref | 已部署的凭据别名；部署策略将别名绑定允许的目标 origin/path。不得仅凭两个各自合法的下拉选项任意组合发送凭据 |
| context_limit/max_output_tokens | 正整数；明确输入预算与输出预留，拒绝越界；不能承诺自动发现供应商实际限制 |
| capabilities | streaming、tool_calling 两个显式布尔能力声明；文字输入/输出为首版固定边界。声明不等于已通过探测，也不能使适配器凭空支持某能力 |
| 首版模式约束（非配置字段） | 仅准入非思考模式；有关闭参数的连接通过 protocol_options 显式声明。空选项不等于已关闭，需依据目标接口行为确认；需要私有推理续传的模式暂不准入 |
| enabled/is_default/revision | Backend 权威配置；并发编辑、默认模型与失效规则沿用既有契约 |

不开放任意 headers、extra_body 或 SDK kwargs 编辑器。protocol_options 按协议校验，不按品牌枚举允许的平台；未知选项必须拒绝。后续新增扩展参数时先补 schema、序列化和验证样例，禁止覆盖鉴权、URL、tools、messages、stream 等受控字段。供应商差异若涉及不同消息或响应语义，须增加明确的协议兼容处理及验证，不能仅靠开放任意参数宣称支持。

EffectiveCapabilities.model 保留运行必需的非敏感字段，增加 protocol/protocol_options/max_output_tokens/capabilities（provider 仅作可选展示元数据），与现有 model.revision 一起冻结。enabled/is_default 由 Backend 选择与复核，不成为 Runtime 的第二份配置真相。

普通用户 catalog 仅返回 ID、显示名、能力与可用状态；base_url、credential_ref 等仅管理与受认证内部接口可见。密钥从 Runtime 部署环境在调用时解析，不进入快照、checkpoint、审计或 UI。

保存配置不发起付费请求；缺少凭据允许保存并明确显示不可用。resolve 时核对凭据存在、协议及其选项支持、模型 enabled 与请求所需能力；失败 MODEL_UNAVAILABLE，不静默替换默认模型。模型配置与运行快照不得由用户提交 URL/key 等字段覆盖。

## Runtime 适配边界（S03 落实）

ModelAdapter 对图输出统一的正文增量、完整工具请求、完成原因、用量和安全错误。协议解析、工具参数碎片合并、空 content、usage 缺失、finish_reason 等差异在适配器内处理；完整工具请求仍统一通过 ToolGatewayService。

注册表仅以 protocol 选择适配器：openai_chat_completions → OpenAIChatAdapter。DeepSeek、百炼或其他平台使用同一协议时复用该适配器；通过显式 protocol_options 序列化经校验的兼容参数，不建立 DeepSeekAdapter/百炼Adapter 的平行实现。真正不同的协议（如 Anthropic Messages、Gemini GenerateContent、OpenAI Responses）才分别增加适配器。首版尚未实现这些扩展协议；图、工具网关和前端事件保持统一。

流式能力声明为 false 的模型不能承诺真实流式；工具能力为 false 的模型不能运行需要工具的请求。Backend 解析有效能力时明确拒绝不匹配组合，不能悄悄忽略用户已选工具能力。供应商返回非声明能力或不完整工具参数时安全失败，不执行半截工具调用。

已向用户输出正文后不自动重发模型请求；401/429/超时/上游错误归一化并脱敏，不能切换 Mock 或其他平台。配置变化复核失败沿用 CAPABILITY_CHANGED，恢复不替换模型。

### DeepSeek 思考模式的边界

官方文档说明，思考模式在携带 tools 的后续请求中有 reasoning_content 回传要求；只保留 content/tool_calls 的通用映射可能不够。首版明确关闭思考模式，不承诺这一模式已经兼容。

后续启用前必须定义 provider 私有续传状态、按其协议处理多轮/工具轮次、checkpoint 与恢复，并确认跨 Run 历史边界。该状态不是用户正文，不进入公共 SSE、普通历史投影或日志。仅增加一个 thinking=true 开关不足以完成接入；不得未经设计就把整份 SDK 响应放进图状态。相关实现和授权验收完成前拒绝启用。

## 按协议划分实现范围

| protocol | 适配器 | 首版状态 |
| --- | --- | --- |
| openai_chat_completions | OpenAIChatAdapter | S03 待实现；首个配置实例与真实验收目标为 DeepSeek |
| anthropic_messages | 后续独立适配器 | 未实现，不允许配置为可用 |
| gemini_generate_content | 后续独立适配器 | 未实现，不允许配置为可用 |
| openai_responses | 后续独立适配器 | 未实现；与 Chat Completions 是不同协议，不能因同厂商而共用序列化 |

上述后续协议名是设计示例，不预先加入当前 schema 的可用枚举。新增一个兼容平台主要新增连接/模型配置与兼容性证据；新增一种线协议才新增协议适配器。同一个平台可以提供多个协议，同一种协议可以连接多个平台。

例如 DeepSeek 官方连接配置 protocol=openai_chat_completions、对应 base_url/credential_ref、实际模型 ID，以及 protocol_options={"thinking":{"type":"disabled"}}。同协议的其他平台可复用适配器，专有参数必须显式验证；接入平台名称变化不会改变代码分派。尚未调用验证任何平台。

## 灵机 AI 对照：管理渠道与运行协议是两层

只读核对了公司仓库，未复制实现或修改文件：

- Backend 的 SaveModelChannelInput 包含 Type/BaseURL/Key/Models，允许的 NewApi 渠道类型为 OpenAI=1、Anthropic=14、阿里百炼=17；创建/编辑/探测通过 NewApi 管理 API。这里的渠道类型混合了协议家族和平台类型，不能直接当成纯协议枚举。
- Runtime 聊天 resolver 统一构造 ReasoningCompatibleChatOpenAI，地址来自 MODEL_GATEWAY_BASE_URL；公司架构将上游渠道/provider 差异交给 Model Gateway。没有在此聊天 resolver 中按平台创建多套模型客户端。
- Runtime 仍存在思考参数及流式内容兼容处理，说明统一入口也不能消除所有能力差异。此次只核对代码与设计，不代表 NewApi 各渠道真实联调通过，也不把聊天路径结论推广到图像路径。

本项目没有部署 Model Gateway，因此由 Runtime 的协议适配边界承担直连兼容；公司项目则将上游转换放在网关。借鉴统一调用边界，无需复制 NewApi 渠道数字枚举或引入平台专用必填 profile。

源码依据：
- C:/MyWorkSpace/lingji-ai/services/backend/internal/modules/modelgovernance/application/model_service.go：108、203、563 行起。
- C:/MyWorkSpace/lingji-ai/services/backend/internal/modules/modelgovernance/integration/newapi/client.go：296 行起。
- C:/MyWorkSpace/lingji-ai/services/runtime/src/deepagent/model/resolver.py：168、206 行起。
- C:/MyWorkSpace/lingji-ai/services/runtime/src/deepagent/model/openai_compat.py：30 行起。

管理员页面区分：配置合法性、凭据存在性、真实 chat/stream/tool_loop 各项验证状态和时间。真实调用状态按 model.revision 绑定；配置变更后原结果失效。部署凭据变更使历史结果不再代表当前连通性，页面不得以“曾成功”承诺当前可用。

真实探测由 Runtime 发起，Backend 负责鉴权和保存结果。D2 仅实现不消耗模型额度的配置检查与“未验证”展示；D3 准备受授权的真实验收入口并保存分项结果。工具探测使用固定无副作用工具结果，不能触发业务写入。未拿到授权不调用、不标通过；无探测记录不阻止管理员保存配置。

## 一条请求与一个失败点

用户选择内部 model_id → Backend 验证身份、配置和本轮所需能力 → 冻结模型快照及 revision → Runtime 复核配置并仅按 protocol 选适配器，再校验 protocol_options → 解析受目标约束的凭据 → DeepSeek 流式响应 → 工具请求经过 ToolGatewayService → 再次调用模型 → 规范事件经 Backend 返回 Web。

失败例：模型未声明 tool_calling，却选择了需要工具的任务。Backend 在派发前返回明确 MODEL_UNAVAILABLE 原因；不发送带 tools 的请求，不静默丢弃工具，也不偷偷换模型。

## 完成条件

- S02：先更新 JSON Schema/OpenAPI/样例/生成 DTO，再实现字段、部署准入清单、配置 CRUD、可用能力解析和 UI；未知协议/协议选项 由服务端拒绝。
- S03：实现公共 OpenAI Chat Completions 协议适配器，以 DeepSeek 配置打通真实流式、工具回传、错误归一化；准备传输 fixture 与真实模型分项验收入口。Mock 图闭环和 provider 协议验证分别报告。
- A03 覆盖配置与能力匹配；A24 在用户授权额度内记录 DeepSeek 文本、流式、工具闭环证据。未验证其他平台必须标未验证。
- S02 已完成授权测试并部署到开发环境；本轮真实模型调用为 0。

## 官方依据（2026-11-03 核对）

- [DeepSeek API](https://api-docs.deepseek.com/)：接入入口与兼容协议说明。
- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)：模式参数与工具请求的推理内容回传规则。
- [阿里云百炼 OpenAI 兼容接口](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)：兼容接口及地域/工作空间地址，凭据与地域绑定。
