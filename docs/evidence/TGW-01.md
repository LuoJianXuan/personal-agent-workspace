# TGW-01：进程内工具治理

日期：2026-11-07。实现：代码齐备。验证：运行通过。

## 改动与契约

保留façade，提取Registry/Policy/Lifecycle/Router/Ticket/Builtin/MCP executors；参数/文件/审批/预算在dispatch前；同一execution成功缓存；失败重试不改写其他在途执行。

涉及：services/runtime/app/tool_gateway.py、tool_execution.py、artifact_collector.py、materials.py。

## 一条请求

DeepAgents工具回调 → façade → policy → lifecycle.begin → router → collector → canonical result。

## 失败边界

缺审批/无授权文件不dispatch；副作用不确定保持UNKNOWN。Langfuse继续由现有官方回调观察真实工具节点。

## 已执行证据

完整 Mock 业务回归通过 builtin、MCP、审批、取消、预算、幂等、UNKNOWN、事件回放、文件作用域和并发上限；Mock 只替换模型输出，网关与副作用链路为真实模块。

## 验收边界

本轮真实模型/搜索调用为 0；网关治理结论来自真实 Runtime、数据库、MCP、Backend 与 Docker 执行，不把 Mock 模型冒充真实供应商验证。
