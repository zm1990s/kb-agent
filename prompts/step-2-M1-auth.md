实现 ROADMAP.md 中的 模块 M1 · 认证与空间。

**你必须按 Unit 逐个推进**：
- 一次只做一个 Unit
- 每个 Unit 做完先跑测试，绿了再进下一个
- 每个 Unit 完成后停下来向我汇报，我确认后你才能继续

按顺序：M1-U1 → M1-U2 → M1-U3 → M1-U3b → M1-U4 → M1-U5 → M1-U6 → M1-U7

严格约束（来自 DESIGN.md / CLAUDE.md）：
- API 路径必须与 DESIGN.md 完全一致（/auth/register, /auth/login, /auth/me, /workspaces, /workspaces/{id}/members），不得改名
- 表结构严格按 DESIGN.md（users/workspaces/workspace_members），只做 additive
- 注册（M1-U3b）必须校验邮箱域名后缀在 ALLOWED_EMAIL_DOMAINS 白名单内，白名单外返 403、重复返 409；测试覆盖三种情况
- 密码 bcrypt，JWT 密钥从配置读，禁止硬编码
- api/ 层只做校验与转发，业务在 services/
- require_admin / require_ws_member 依赖必须落地；Partner 隔离要有测试覆盖
- 每个端点配 pytest（至少 1 happy + 1 error path）

验收重点：注册(白名单校验)→登录→建空间→加成员→GET /workspaces，Partner 用户看不到未授权空间返回空/403。

现在开始 M1-U1，先给我实现计划，我确认后再改文件。
