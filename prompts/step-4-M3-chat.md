实现 ROADMAP.md 中的 模块 M3 · 对话式检索取件。

**你必须按 Unit 逐个推进**：一次只做一个 Unit，做完跑测试，绿了汇报，我确认后再继续。

按顺序：M3-U1 → M3-U2 → M3-U3 → M3-U4 → M3-U5

严格约束：
- API 路径与 DESIGN.md 完全一致（/chat, /conversations/{id}）
- 检索走 PG 全文检索（search_tsv）+ workspace/分类过滤；**不引入向量库**
- 答案生成把命中文档的原文交给 app/engine/ 生成，返回 {answer, sources, conversation_id}
- sources 每项必须含 doc_id + title + download_url（限时签名）
- 仅返回用户所属 workspace 的文档；跨空间零泄漏（必须有测试）
- 无命中时明确返回“未找到相关文档”，禁止编造答案（降低幻觉，符合原文优先原则）

验收重点：提问→检索命中→返回带原文链接的答案；无命中场景返回明确提示；Partner 只能查到授权空间内容。

现在开始 M3-U1，先给我实现计划，我确认后再改文件。
