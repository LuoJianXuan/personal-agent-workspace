# 007 — 以 Personal Agent 为目标，保持 Harness 核心精简

日期：2026-11-06。状态：产品与架构原则已采纳；S16–S20 已实现、验收并切换日常 5173。适用独立agent-workspace，不改变公司灵机AI定位或实现。

## 背景

用户明确要求：项目最终目标为个人Agent，后续规划必须参考Harness和Pi的核心思想。对文档处理的[一手资料调研](../research/personal-agent-document-processing-2026-11-06.md)显示，工具/技能、固定解析模块、内部worker或脚本执行可结合，不要求按功能增加独立常驻部署。当前文档预解析流程的部署复杂度需要收敛。

## 三个决策

1. **精简核心，复用框架。** 保留已经接通的DeepAgents/LangGraph与标准模型客户端，不更换为Pi或重新实现循环。参考Pi的稳定小核心、扩展机制与技能按需加载；个人助手能力通过现有工具准入和可组合能力接入。默认单主Agent，子Agent按独立上下文/并行收益另行论证。
2. **能力模块化，部署按需求。** 新增能力优先为工具、技能或内部模块，执行复用受限子进程/执行池或已有可选Docker设施。拆常驻服务须说明资源、依赖、隔离或独立扩容必要性及轻量替代方案；不能按PDF、日历、记忆等功能名机械拆服务。文档读取按需，固定解析库与缓存保留，不强制所有任务进Docker。
3. **保留产品边界与可核查结果。** Web/Go Backend/Python Runtime维持独立职责；文件归属、原件/产物、审批与运行事实仍由现有数据域管理。工具统一准入、取消、限额、脱敏、来源和幂等不以“精简”名义删除。Langfuse当前仅Agent/模型/工具调用，不扩为全请求链路。

## 不由本决策推出的结论

Pi是参考思想，不是本项目下一次底座替换目标；不复制其默认本机shell权限。保持核心精简不等于把所有解析放回主事件循环，也不等于所有服务合并。固定解析不低于技能脚本，脚本不必由模型每次生成。个人版仍可在重型OCR、GPU、大批量索引有实际需要时接入外部服务。

## 每次后续规划必须回答

- 用户实际完成什么任务？默认主Agent是否足够？
- 现有Harness/工具/执行环境可以复用什么？
- 为什么新增模块、工具或技能？若新增服务，其依据与成本是什么？
- 输入、权限、失败、取消、资源/费用边界在哪里？
- 哪些行为要保留，如何验收，哪些能力明确不在范围？

## 当前接入点

先执行[Personal Agent优化方案](../plan-v3/PERSONAL-AGENT-OPTIMIZATION.md)的S16–S20，再进入原P2–P4。历史S08–S15验收记录保留，不把新方案写成已实现。用户未授权新测试/真实请求时，只准备入口。

依据：[Pi定位](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md)、[Pi技能按需加载](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md)、[Deep Agents官方概览](https://docs.langchain.com/oss/python/deepagents/overview)、[框架优先决策006](006-framework-first-harness.md)。
