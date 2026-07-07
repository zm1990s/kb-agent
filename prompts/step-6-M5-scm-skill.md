实现 ROADMAP.md 中的 模块 M5 · SCM 示范 skill（PANW 产品配置，确认后下发）。

前置：M4 Skill 框架已完成。

**你必须按 Unit 逐个推进**：一次只做一个 Unit，做完跑测试，绿了汇报，我确认后再继续。

按顺序：M5-U1 → M5-U2 → M5-U3

严格约束（安全关键）：
- SCM skill 继承 SkillBase，is_write_operation=True
- 配置生成阶段只“生成方案”，经 app/engine/ 借助知识产出结构化配置，绝不直接下发
- 下发必须走 M4 的审批闭环：pending_approval → approve 后才调 SCM/PANW API 真实下发
- 每次下发写完整审计日志（谁、何时、下发了什么、结果），保留回滚所需信息
- SCM/PANW 凭据走 secret 管理，禁止硬编码

开工前确认：目标 PANW 产品与 API（Strata Cloud Manager / PAN-OS API 等）、认证方式、可回滚范围 —— 如未定，先问我。

现在开始 M5-U1，先给我实现计划，我确认后再改文件。
