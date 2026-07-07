实现 ROADMAP.md 中的 模块 M2 · 文档入库与归类。

**你必须按 Unit 逐个推进**：一次只做一个 Unit，做完跑测试，绿了汇报，我确认后再继续。

按顺序：M2-U1 → M2-U2 → M2-U3 → M2-U4 → M2-U5 → M2-U6 → M2-U7

严格约束：
- API 路径与 DESIGN.md 完全一致（/workspaces/{ws}/documents, /documents/{id}, /documents/{id}/download, /documents/{id}/tasks, /documents/{id}/reprocess, /categories）
- documents 表含 search_tsv + GIN 索引；processing_tasks 表记录状态/日志/重试；分类必须属管理员预定义的 categories
- 归类**只能经 app/engine/**：让 ClaudeCliEngine 直接读原文，**一趟产出 {分类归属, 摘要, 标签, content_text 可搜正文}**；禁止直连任何 LLM SDK；MVP 不自建文档解析库
- 文件存取**只能经 app/storage/**（LocalStorage，本地目录）；业务层禁止直接拼路径
- 归类是**后台任务**：上传立即返 202+processing；worker 处理；processing_tasks 落详细日志；失败落 error+status=failed，可经 reprocess 重试（不得静默失败）
- 所有文档查询强制带 workspace 权限过滤，跨空间零泄漏（必须有测试）
- **越权校验**：/documents/{id}、/download、/tasks、/reprocess 均须 require_ws_member(doc.workspace_id)，不只校验登录；workspace 过滤下沉 SQL；非成员返 403/404 且有测试（含 Partner 跨空间用例）
- **路径穿越**：storage_key 服务端生成（UUID），原始文件名只存 documents.title；LocalStorage 存取内部 realpath 校验落在 LOCAL_STORAGE_DIR 内，越界拒绝；禁止把请求参数拼进文件路径
- **下载响应头**：Content-Disposition: attachment + X-Content-Type-Options: nosniff（防存储型 XSS）
- 下载走本地受控下载端点，限时（DOWNLOAD_URL_TTL_SEC）；非空间成员返回 403

已决策（无需再问）：
- 文件类型=所有常见格式，交 CLI 读取；存储=本地路径；归类=后台任务+日志+重试；可搜正文=复用 CLI 产物。

开工前确认（仍待定，如未定先问我）：
- Q2 用哪个 Claude 模型 + 单文档超时/并发上限 + 超大文件处理策略
- Q6 后台任务承载：进程内 asyncio 任务 vs arq/redis 队列（影响重启后任务是否丢失）
- Q7 本地下载端点的限时鉴权方式（临时 token vs 短期签名）

验收重点：上传→status=processing→后台归类完成 status=ready（可经 /tasks 查进度、失败可 reprocess）→列表看到分类/摘要/标签→下载拿到原文；跨 workspace 不可见。

现在开始 M2-U1，先给我实现计划，我确认后再改文件。
