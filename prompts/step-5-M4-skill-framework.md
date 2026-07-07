实现 ROADMAP.md 中的 模块 M4 · Skill 插拔框架（预留能力，此步开始真正实现）。

**你必须按 Unit 逐个推进**：一次只做一个 Unit，做完跑测试，绿了汇报，我确认后再继续。

按顺序：M4-U1 → M4-U2 → M4-U3 → M4-U4

严格约束：
- SkillBase 抽象至少包含：name、description、input_schema、is_write_operation、async invoke()
- registry 负责发现/注册 skill；GET /skills 列出
- POST /skills/{name}/invoke：**写操作（is_write_operation=True）必须返回 {action_id, status:"pending_approval"}，绝不直接执行**
- POST /actions/{id}/approve：只有审批后才真正执行写操作，并记审计日志
- skill 若需 LLM，仍只经 app/engine/
- 权限：谁能 invoke、谁能 approve，要接 M1 的角色/空间校验

这是未来 SCM 等 skill 的地基，审批闭环是硬约束（涉及真实设备改动）。

现在开始 M4-U1，先给我实现计划，我确认后再改文件。
