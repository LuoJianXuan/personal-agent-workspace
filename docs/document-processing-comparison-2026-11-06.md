# 文档处理源码核查（2026-11-06）

后续已补充[个人Agent开源方案调研与架构判断](research/personal-agent-document-processing-2026-11-06.md)。本文保留灵机AI与Demo当前实现事实，不作为继续维持独立文档worker的架构建议。

范围：只读灵机AI源码与当前独立Demo，不执行测试/模型/文档任务，不修改公司实现。以下区分实际固定解析能力、可用工具链与未经格式验收的潜在转换能力。

## 灵机AI

文档处理主要是工具执行，不是“每来一个文件就启动专用文档子智能体”。系统支持子智能体委派，具体配置可使用文档工具；文件格式处理本身仍由工具/解析程序完成。动态用户/专家包可以扩展，不能据内置源码推断任意部署都启用了同一份能力。

链路：附件URL下载→通过受控Backend桥接存入/workspace/.attachments→向模型提供路径/类型提示→Agent按可见工具和技能选择读取/脚本/转换/OCR→Tool Gateway裁决本地或云端执行→结果与产物。XLSX有前10行的有限预览，不代表整份工作簿已读。

- TXT/Markdown：文本read_file分段读取。
- DOCX/XLSX等：受控执行中使用Office库/脚本；sandbox/Dockerfile安装python-docx、pypdf、openpyxl、python-pptx、xlrd和LibreOffice。依赖存在是可用处理基础，不等于每种格式已验收。
- PDF/图片：document_ocr工具经Tool Gateway的paddle_ocr_gateway路由；registry绑定TieredOcrExecutionProvider，源码含Paddle/腾讯/阿里OCR实现，实际路由取决开关/配置。也可用沙箱中的pypdf做文字PDF提取。普通read_file不能把PDF/base64当文字送入模型。
- 桌面端另有goffice技能，声明支持本地.docx/.xlsx；不能把它说成直接支持所有PDF/PPT/WPS。
- 未发现原生.wps专用解析和验收承诺；旧.doc只有通用转换基础，未在本次证明稳定支持。

证据入口（公司目录只读）：services/runtime/src/deepagent/attachments.py:270、backend/workspace/reads.py、assembly/request_context.py、assembly/subagent_assembly.py；services/tool_gateway/src/services/execution/route_resolver.py:118、providers/registry.py:78、providers/tiered_ocr.py；sandbox/Dockerfile；apps/desktop/skills/goffice/SKILL.md。

## 当前Demo

采用“固定预解析+主Agent调用资料工具”。document-worker是普通Python服务，不是子智能体，没有LLM推理，也不消耗模型调用额度。

PDF/DOCX/XLSX上传→Backend保存原件并登记document_job→worker领任务、子进程中使用固定解析器→保存chunks/页码段落等定位→主Agent经builtin_read_material读取已授权片段→模型总结、比较、引用→publish_report导出。TXT/MD/CSV直接走文本/数据读取，无需二进制解析worker。可选Python计算工具不是常规PDF/DOCX读取的必经路径。

| 格式 | Demo实际边界 |
| --- | --- |
| .txt | 支持UTF-8文本读取/片段引用 |
| .md | 支持Markdown文本；上传扩展名白名单不包含.markdown |
| .docx | python-docx提取正文段落/表格和定位；不完整复现复杂排版 |
| .doc | 不支持上传/没有旧Word转换 |
| .pdf | pypdf提取文字与物理页码；不支持扫描件OCR，纯扫描无可提取文字会明确报出 |
| .wps | 不支持原生WPS格式；用WPS保存的标准.docx按docx处理 |
| .csv | 支持固定Decimal统计、图表与CSV输出 |
| .xlsx | openpyxl读取表/行/单元格缓存值；不重算公式，缺缓存的统计请求明确失败 |
| .ppt/.pptx、图片 | 当前资料上传不支持；没有OCR工具 |

以文件格式为准，不按文件由Microsoft Office还是WPS创建来决定。每轮最多3份、单份5MiB；PDF最多100页。正式报告目前MD/DOCX，尚无通用PDF/WPS格式转换与导出。

源码：services/backend/internal/agententry/files.go:255上传白名单；apps/web/src/delivery.tsx:67/91；services/backend/internal/workspace/documents.go；services/runtime/app/document_worker.py、documents.py、materials.py:read；schemas/builtin-tools.json。上轮本地验收实际验证过文字PDF/DOCX/XLSX；本次不重复执行。

结论：两边都是Agent通过工具处理文档。灵机AI偏通用受控工具/沙箱与OCR，Demo偏固定格式预解析再读取。仅为读取/总结文档没有必要增加一个专用子智能体；是否委派应取决于任务复杂度与是否需要独立上下文。
