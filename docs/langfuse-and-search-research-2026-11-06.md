# Langfuse与搜索API调研（2026-11-06）

范围：独立agent-workspace源码核查；只读参考C:/MyWorkSpace/lingji-ai；只读检查本机Docker；官方网页价格/集成说明核对。本次没有修改公司代码、接入实现、配置或容器状态，没有执行测试/模型/项目搜索请求。

## 1. Demo当前覆盖

| 层 | 当前实际实现 | 缺口 |
| --- | --- | --- |
| HTTP | Go RequestID/FastAPI中间件生成UUID，响应X-Request-ID；审计记录request_id | 两个服务分别生成，未透传成完整调用链；缺统一结构化请求耗时与状态日志 |
| 业务运行 | runtime.run_events持久化事件（run_id/thread_id/seq/时间），UI工具过程与回放 | 产品事件不是完整框架span树，不能直接分析每层模型/工具耗时 |
| 工具 | tool_executions含execution_id/run_id/tool_name/request_hash/status/result；tool.started/completed/failed | 无Langfuse trace/span、完整耗时瀑布图与统一聚合 |
| 模型 | model_calls保存调用身份/状态/usage/error，预算真实落库 | 无每次generation的可视化输入输出、首token/延迟和模型分布看板 |
| 运维 | 容器stdout与少量异常日志 | 无完整服务/队列/worker指标告警，部分后台捕获异常只重试未记录原因 |

源码：services/backend/internal/platform/http.go、services/backend/internal/agententry/runs.go；services/runtime/app/main.py、engine.py、tool_gateway.py、runtime_schema.sql。Demo pyproject/uv.lock没有Langfuse SDK。

## 2. 灵机AI的实现参考

源码入口：C:/MyWorkSpace/lingji-ai/services/runtime/src/deepagent/tracing/langfuse.py；装配：src/deepagent/assembly/factory.py；设计：docs/langfuse-data-mapping.md。

- 锁定Python SDK langfuse==4.15.1；通过LANGFUSE_ENABLED/HOST/PUBLIC_KEY/SECRET_KEY启用。缺key则关闭trace并记录警告。
- 官方langfuse.langchain.CallbackHandler装入Agent session config callbacks，metadata合并业务作用域。
- thread_id映射session，user_id映射用户；携带tenant/project/run/thread/turn与实际模型信息。run_id派生稳定trace id，审批恢复继续关联原run。
- 对审批/凭据/本地执行等待做状态分类，避免全部标成工具失败；根observation保存原始请求与结果，恢复命令不覆盖原始用户请求。
- 超大观测副本限长/hash；模型generation记录usage。run总token另写幂等numeric score，避免把usage写到不支持的根chain节点后丢失。
- 工具调用从当前OTel上下文生成traceparent，注入ToolGateway invocation_context；ToolGateway接收并存储该字段。不能据此声称每个下游服务都已完整导出span。
- Langfuse是观测投影；canonical events/Backend才是业务权威，指标和成本不作为配额/账单权威。

代码包含SDK v4与旧写入兼容补丁，这些是公司版本背景；个人Demo应基于官方API独立实现最小集成，不复制整套适配器或任何凭据。官方已有[DeepAgents集成](https://langfuse.com/integrations/frameworks/langchain-deepagents)与[LangChain回调/分布式追踪](https://langfuse.com/integrations/frameworks/langchain)说明。

## 3. 本机部署只读快照

- langfuse-langfuse-web-1：v4镜像，宿主3000端口，running但health=starting，复核时restart_count=457。
- langfuse-langfuse-worker-1：v4镜像，running，无容器healthcheck结果，不能仅据此判断可用。
- langfuse-postgres-1、langfuse-redis-1、langfuse-clickhouse-1、langfuse-minio-1：exited。

本机确有Langfuse部署，但当前不是已确认健康的观测服务。应先恢复现有部署与数据卷、确认健康；不另建一套数据库/观测平台。没有启动/重建/升级这些共享容器，也没有读取/输出其密钥。后续个人Demo应新建独立Langfuse Project和专用API key，不能复用公司项目数据或凭据。

## 4. 个人Demo的建议接入范围（尚未实施）

1. 一个业务run对应一个稳定trace，thread对应session；用户、租户、项目与run统一关联。恢复分段属于原run，重新运行则新run，避免并发/恢复串链。
2. 官方CallbackHandler挂到现有DeepAgents执行配置，自动采集实际模型、工具、图执行；不自写一套Agent追踪回调框架。不获取模型未公开的内部思考，仅记录实际可观测调用与事件。
3. 补少量手动观测：排队/派发、治理准入、审批等待与恢复、文档worker、搜索HTTP、Python broker/容器、产物发布。异步/进程任务必须传递traceparent并保留run/execution关联；等待和执行耗时分开，取消与失败分开。
4. Go/Python统一JSON结构化日志，透传受校验的request上下文，关联request_id/run_id/thread_id/execution_id/trace_id；记录安全错误码、耗时和结果状态。Langfuse链接用于运行详情，不把密钥给前端。
5. 导出数据单独脱敏/限长，默认白名单字段与受限预览；不直接导出部署环境、访问令牌、checkpoint或完整原始文档。异步有界投递与故障日志/计数，Langfuse离线不阻塞Agent。恢复/关闭时按SDK规范flush。
6. 第一批关注run/工具成功率与延迟、token、取消/超时、队列/执行耗时；成本仅在模型价格和usage可靠时展示。CPU/内存、worker存活、数据库和队列告警仍需要基础设施指标，Langfuse不替代所有运维系统。

验收门槛应为：Mock+真实MCP链路能在本地Langfuse看到根run、模型与工具子观测；同run审批恢复关联稳定；取消/失败状态正确；Langfuse故障不影响主任务；没有部署秘密。无须为首次可观测性验证消耗DeepSeek额度。测试仍按会话明确授权执行。

## 5. 搜索API免费额度（当日官方网页）

| 服务 | 免费额度 | 周期/注意事项 | 官方来源 |
| --- | --- | --- | --- |
| Tavily | 1,000 API credits/月，无需信用卡 | basic每次1，advanced每次2；次数按所用功能计，不是所有接口统一1次1credit | https://docs.tavily.com/documentation/api-credits |
| Exa | $10 credits/月，另有$10首次赠额，无需支付方式 | 按端点与结果数计价，不能直接当固定请求次数 | https://exa.ai/pricing |
| Brave Search | 标准Search套餐明确$5 credits/月，Search标价$5/1,000请求 | 纯Search按该价推算约1,000次；需信用卡。首页另有最高$20宣传，本文按套餐明确$5保守记录 | https://brave.com/search/api/ |
| SerpApi | 250 searches/月 | Free计划，50次/小时 | https://serpapi.com/pricing |
| Serper | 2,500免费查询，无需信用卡 | 官网未明确每月续赠，作为注册试用看待，不能列成2,500次/月 | https://serper.dev/ |

资料来自官方页面，不使用第三方聚合站的旧价格。没有新建这些服务的账号，也没有实调比较中文质量、国内网络可达性或账号实际余额；额度以各账号控制台与当时条款为准。

Demo当前research.py直连https://api.tavily.com/search，search_depth=basic、max_results默认5，未调用Tavily Extract；正文由项目自身fetch_public以HTTP+BeautifulSoup读取。因此若全部免费credits只用于当前basic搜索，理论可做1,000次/月。当前每run最多2次搜索/6次正文读取；若每任务恰好2搜，约500个任务，这是额度算术估计，不是质量/性能测试。

项目SEARCH_CALL_BUDGET是本地请求次数保护，不自动查询或同步Tavily账号月度credits。需要独立API key、显式联网许可与本地窗口额度；免费额度耗尽也不能自动换服务或放开消费。之前“付费搜索未验证”的准确表述应为“Tavily真实接口尚未验收”，使用免费credits也属于真实接口验收。

建议保持Tavily首选，先用每月免费额度验证现有实现；确有比较需要时再接Exa或Brave。搜索供应商接口不统一，适合用轻量provider适配，保持Agent侧web_search工具契约与现有来源/网页读取不变，无需为了多个免费key建立复杂搜索网关。

## 6. 用户确认的实施边界

用户随后明确：当前只要Agent每一步调用，不需要整个HTTP请求链路或后台系统完整观测。后续实施以此为准：官方CallbackHandler采集Agent/模型/工具，按run与thread关联，观测副本脱敏限长、Langfuse故障不阻塞任务。上文第4节中的统一全链路、排队、审批等待、独立文档worker、Python容器内部阶段等为后续可选项，不属于当前必须实现范围。工具整体调用仍可由标准回调看到。
