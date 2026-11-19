# 实现设计

## 一条用户请求

工具页读取 `/catalog/connectors` → 选择麦当劳安装 → 在共用弹窗填写 Token → 原 `/me/connections/:connector/probe` 发现 → 原 `/grant` 确认 → 缓存接收服务器权威状态 → 显示安装成功。去对话只通过 React Router state 传入非秘密的草稿和 connector_id / skill_id，消费后移除 state；用户明确发送后才沿用原 Run → Harness → Tool Gateway → MCP 执行链。

## 数据与契约

- ConnectorPresentation：简介、分类、枚举图标、HTTPS Token 帮助链接。部署可提供默认展示信息；后台保存覆盖到 connector_publication.presentation。schema 10 为可加性变更，不重写个人连接、凭据或授权。
- 个人连接和管理员配置返回可选 presentation，旧写请求省略 presentation 时保留当前值。字段只用于展示，不进入模型 prompt / snapshot / checkpoint。
- `/catalog/mcp-services` 提供启用且符合现有准入的平台 MCP 名称与已开放工具摘要，沿用 enabledTools 的权限判断，不返回 credential_ref、endpoint、Header 或原始错误。configured 表示已有配置和授权，不声称远端实时在线。
- React 公共连接管理模块承接目录卡片与对话抽屉。Token 仅存在输入组件内存和单次请求体，提交/关闭清空，不写 URL、浏览器存储或 console。

## 状态与失败

ready / auth_required 显示在已安装视图，disconnected / pending 不冒充安装完成。pending 清单必须确认；更新时保留现有授权版本规则。取消正在确认的清单调用 discard。更新或卸载失败不显示成功。目录下架或加载失败时不继续使用旧卡片快照进行操作。状态代表已知配置，不通过列表浏览自动探测远端。

对话抽屉安装不会卸载 Chat，因此取消或失败不会清空草稿。卡片去使用不会自动发送消息。错误恢复按钮打开原地管理，避免跳页丢失草稿。管理员展示编辑使用已有 revision 并发控制；安全目标仍由部署策略决定。

## UI

浅色侧栏、白色细边框卡片、青绿色主操作，Skill/MCP 标签、全部/个人筛选、搜索、详情、分步安装、管理和卸载。只显示真实目录；没有原型演示开关或占位服务。桌面三列，中等屏幕两列，手机一列。模型/搜索/沙箱配置状态移至设置；高级组合检查与工具明细折叠。

## 运行变化与不做项

重建 Backend/Web；现有 Runtime、MCP worker、Langfuse、沙箱和审批执行不变。契约生成器更新 Go/TS/Python 消费副本。新增展示列无需迁移秘密。没有新增依赖、常驻服务、OAuth 或任意 URL 安装。
