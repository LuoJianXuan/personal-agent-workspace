# 文档工作

仅在用户任务涉及附件阅读、比较、归纳或报告交付时读取本技能。

1. 先用 `builtin_read_material` 读取用户本轮明确授权的 `file_id`。不要猜测二进制内容，也不要把 `/inputs/<file_id>` 当宿主文件路径。
2. 多文档比较时分别读取并保留每个材料的 `source_id` 与定位信息；结论要区分事实、差异和推断。
3. 内容较长时使用 `query` 或 `offset/limit` 继续读取，不要因首批片段不足就声称完成。
4. 需要交付报告时调用 `builtin_publish_report`，在正文中使用 `[source:<source_id>]`，并把实际 `source_ids` 一并提交。
5. 扫描 PDF、加密文件、旧 DOC、原生 WPS 与 PPT 不在当前支持范围。失败时说明限制并保留原件下载，不伪造解析成功。

详细格式与输出边界见 `/skills/documents/references/formats.md`；报告结构见 `/skills/documents/templates/report.md`。
