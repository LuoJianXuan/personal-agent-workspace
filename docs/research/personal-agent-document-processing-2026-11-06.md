# Personal Agent 文档处理架构调研（2026-11-06）

本次任务是调研与判断，不是实施重构。没有修改运行代码、协议、部署配置、数据库或容器；未执行测试、模型调用、项目搜索接口调用或安装外部技能。外部技能文件仅作为源码资料阅读，其指令没有用于本次执行。

## 结论与证据强度

对“个人Agent默认处理用户文件”的目标，当前Demo把PDF/DOCX/XLSX上传、后台常驻解析和Agent读取绑定，部署与生命周期治理偏重；建议改为工具按需处理，独立常驻document-worker不作为默认前提。但研究不支持“固定解析器完全偏离主流”或“全部文档都必须进Docker沙箱”。Nanobot内置固定解析，OpenClaw内置提取插件/worker，Hermes用技能提供固定CLI脚本；AnythingLLM说明资料入库预处理本身有实际用途。

上述是基于选取样本与当前源码的架构推断，不是全市场统计、运行性能基准或已完成重构。之前本地验收证明既有实现行为可运行，并不能证明其部署拆分是当前产品目标的最优选择。

## 一手资料样本

### Pi：小核心，按需扩展

当前badlogic/pi-mono地址重定向到earendil-works/pi。内置read实现针对文本/图片，并非通用PDF/Office解析器。官方skills文档描述按需加载说明及附带脚本，使用PDF工具包举例；README说明默认不内置subagents。可核实的是能力扩展方式，不把PDF示例误说成所有安装均已自带办公能力。

来源：[read源码](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/tools/read.ts)、[skills说明](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md)、[README](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md)。

### Nanobot：文件工具直接使用固定解析库

ReadFileTool.execute根据扩展名进入PDF或Office读取，调用document.py中的解析函数，支持页码/行范围。document.py使用pypdf、openpyxl等库，并包含大小、展开与输出边界。此读取路径未调用独立文档HTTP服务。固定解析与工具驱动可以同时成立，不必让模型每次编写解析程序。

来源：[文件工具](https://github.com/HKUDS/nanobot/blob/main/nanobot/agent/tools/filesystem.py)、[解析模块](https://github.com/HKUDS/nanobot/blob/main/nanobot/utils/document.py)。

### OpenClaw：PDF工具，原生模型输入或本地提取插件

官方PDF工具可按模型能力选择原生PDF输入或提取文字/页面图片后分析。文档说明本地提取在可复用worker中执行，取消会停止排队或活动提取；插件源码使用WorkerTaskPool，共享计算、singleton类别并带超时/取消信号。这里的内部worker机制不能等同于要求用户单独部署、配置和维护文档微服务，也不能等同任意代码Docker沙箱。

来源：[官方PDF工具说明](https://docs.openclaw.ai/tools/pdf)、[提取插件](https://github.com/openclaw/openclaw/blob/main/extensions/document-extract/document-extractor.ts)、[worker入口](https://github.com/openclaw/openclaw/blob/main/extensions/document-extract/document-extractor.worker.ts)。

### Hermes Agent：技能、固定脚本与可选执行环境

现有pdf技能包含读取/生成/修改脚本以及OCR说明；microsoft-office技能统一Word/PPT/Excel脚本，按任务调用terminal，产物/结果再由文件工具读取。支持共享的文档Python依赖环境，脚本可在本地或选定终端环境执行。README列出local、Docker、SSH等执行后端。没有理由将“技能脚本”解释为必须子智能体、必须新增文档服务或必须每次模型生成全部代码。检索到的旧docx/ocr-and-documents路径已不可获取，当前主分支合并后的技能文件作为本报告依据，不引用旧镜像目录结论。

来源：[PDF技能](https://github.com/NousResearch/hermes-agent/blob/main/skills/productivity/pdf/SKILL.md)、[Office技能](https://github.com/NousResearch/hermes-agent/blob/main/skills/productivity/microsoft-office/SKILL.md)、[执行环境概览](https://github.com/NousResearch/hermes-agent/blob/main/README.md)。

### WorkBuddy：只按官方产品资料核实

本次未获得可审阅的完整产品内核源码，因此不把WorkBuddy列为源码审计样本。官方文档提供PDF/DOCX/PPTX/XLSX技能；权限文档说明可调用脚本和外部程序，在工作区与沙箱策略下执行。这支持其工具/技能组织方式，但不足以推断内部没有解析服务、所有格式执行位置相同或整个产品开源。腾讯Enterprise Skills页的导航实际为CodeBuddy Code高级功能，不将其实现细节无条件套到所有WorkBuddy形态。

来源：[办公文档四件套](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/WorkBuddy-Zero-Cost-Skill-Top-10/Office-Document-Suite)、[权限与沙箱](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Permission-Modes)。

### AnythingLLM：资料入库型架构的反例

README明确包含文档入库和文档管线。collector进程有/process和/parse等HTTP接口，按文件类型调用处理器；默认Docker entrypoint在同一容器启动server与collector两个进程，Compose只列一个应用服务。它说明固定预处理/独立进程并非错误，也说明内部进程数量与用户部署服务数量不能混为一谈。文档入库/检索型产品与按任务操作文件的个人Agent有不同重心。

来源：[产品定位](https://github.com/Mintplex-Labs/anything-llm/blob/master/README.md)、[collector](https://github.com/Mintplex-Labs/anything-llm/blob/master/collector/index.js)、[启动脚本](https://github.com/Mintplex-Labs/anything-llm/blob/master/docker/docker-entrypoint.sh)、[Compose](https://github.com/Mintplex-Labs/anything-llm/blob/master/docker/docker-compose.yml)。

## 样本支持的共同判断

- 工具是Agent可调用的操作接口；技能是方法、脚本和模板；模块是代码组织方式。这些都不自动等于一个独立部署的网络服务。
- 固定解析库、固定CLI脚本、模型原生文档输入、OCR可并存。执行位置、处理触发时机和算法选择是不同维度，不应强绑。
- 为避免阻塞或隔离解析失败，可以用线程、受限子进程、内部worker池或容器。它们不必带来额外的公共API、部署配置与长期状态机。
- 文档能力的扩展通常进入既有工具/技能/执行环境，而不是以每一种文件或功能增加一个必须常驻的用户部署服务。
- 这些样本没有证明单进程永远最稳、沙箱没有成本或企业架构不合理；是否拆服务仍取决于独立资源、信任边界、并发、硬件和交付需求。

## 当前Demo的具体判断

核查位置：compose.yaml的document-worker服务；services/backend/internal/agententry/files.go的Upload/QueueDocument调用；internal/workspace/documents.go的领取/租约/重试/结果；services/runtime/app/document_worker.py、documents.py、materials.py和compute.py。

已有合理点：原件与提取结果分离；授权/hash与来源定位；解析限资源、超时；不将原始二进制当文字；固定库避免模型重复写基础解析代码。这些应保留。

偏重之处：

1. 上传支持的二进制文档会强制登记预解析，默认路径依赖常驻document-worker；即使用户本来只想保存原件，也创建解析任务。
2. 为该功能增加常驻容器以及claim/input/result内部接口、document_jobs/parsed_documents、租约/重试/状态同步，超出了普通按需读文件的最低需要。它没有独立数据库，也不是一个对外HTTP解析服务器，不能把成本夸大为已经建立了独立文档微服务平台。
3. 解析依赖一套路径，动态Python计算依赖另一套可选broker/runner；未来若每个新功能继续新增独立常驻worker，会形成重复执行治理。当前runner尚非完整办公通用执行器，不能宣称停掉worker即可自动替代。
4. 当前功能侧重文字提取与比较，缺少编辑、格式转换、扫描OCR等路径。新增服务数量没有直接换来个人办公助手所需的通用操作面。

因此这是目标匹配、部署与扩展方式的问题，不是依据现有证据认定解析算法严重错误或全部运行结果无效。没有进行故障率/吞吐测量，不能声称减少容器必然更稳定。

## 推荐方向（待用户后续决定实施）

默认采用Agent通过文档工具按需处理，不再要求每份文件先经过独立常驻解析服务。保留现有固定解析器，放在文档能力模块；通过受限子进程或内部执行池运行，返回可分页片段/位置。若改为缓存，按内容hash和解析器版本缓存，授权每次独立校验。

编辑/转换/报告生成通过技能和可复用脚本进入通用受控执行入口。生成代码、Office转换和高资源任务可使用已有可选Docker执行设施，但需要先补所需依赖与工具协议；纯文本/固定轻量提取不必为了统一而强制走Docker。通用执行是能力复用，不是取消文件授权、超时、资源限制、取消和审计。

Backend继续管理文件、授权、结果；Runtime继续管理Agent与工具，不合并既有Web/Backend/Runtime。重型OCR/GPU、大批量资料入库/全库索引或独立扩容有实际要求时，再选配外部/独立服务。以后增加功能先加模块/工具/技能，按资源与隔离需求拆部署，不按功能名称拆服务。

灵机AI值得借鉴的是工具准入与可替换执行环境，不能照搬其企业控制面、全套网关或多租户部署。也不因其已有沙箱，就断言所有PDF提取都必须进沙箱。

若后续实施，必须先处理旧document_jobs和parsed结果兼容、上传/预览状态、引用与下载回归；不能现在直接停worker、删表或把二进制解析挪进Go Backend请求线程。本次没有进行这些变更。

## 范围与限制

查阅日期为2026-11-06，使用各项目当时官方文档及主分支公开源码，未安装运行这些项目，也未验证商业产品内部部署。主分支、技能目录和文档会变；部分网络缓存日期不同，无法从缓存确认的内部线程/进程机制不作更具体断言。报告采用行为路径与可核查部署文件，不以star数、营销文案或社区镜像代替实现证据。
