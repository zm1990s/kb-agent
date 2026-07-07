实现 ROADMAP.md 中的 模块 MF · 前端（单端口入口）。

技术栈：Next.js（App Router）+ TypeScript + Tailwind。**用户只暴露一个端口**。

**你必须按 Unit 逐个推进**：一次只做一个 Unit，做完自测（能起、关键交互通），绿了汇报，我确认后再继续。

按顺序：MF-U1 → MF-U2 → MF-U3 → MF-U4 → MF-U5 → MF-U6

严格约束（来自 CLAUDE.md / DESIGN.md）：
- **单端口**：前端经 next.config.js rewrites 把 `/api/*` 反代到后端 FastAPI；前端代码**禁止硬编码后端地址**，一律用相对 `/api/*`。docker-compose 里后端不再对宿主暴露端口（仅 compose 网络内可达），只暴露 frontend 端口。
- **鉴权**：登录拿 JWT，统一经 `lib/auth` 存取；`lib/api` 统一注入 `Authorization: Bearer` 并处理 401（跳登录）。路由守卫拦截未登录访问受保护页。
- **XSS（SECURITY #6）**：LLM 产物（summary / chat answer）若按 Markdown 渲染，**必须 sanitize（如 DOMPurify）**；禁止 `dangerouslySetInnerHTML` 未净化内容。
- **角色显隐**：上传/建空间/建分类/reprocess 等管理入口仅对 admin 显示（仅体验层；后端仍是强制防线，前端不作唯一防线）。

页面对应后端契约（见 DESIGN.md API）：
- 登录/注册 → POST /auth/register, POST /auth/login, GET /auth/me
- 对话查询 → POST /chat（展示 answer + sources[].download_url），GET /conversations/{id}
- 文档管理 → POST/GET /workspaces/{ws}/documents, GET /documents/{id}/tasks, /download, POST /reprocess
- 空间/成员/分类 → /workspaces*, /categories

对应后端已实现并通过测试（100 passed），前端只对接、不改后端契约；如需后端调整，先告诉我走 /design。

开工前确认（如未定先问我）：
- 前端对外端口号（默认 3000？生产 80？）
- 是否需要一个最简 e2e 冒烟（如 Playwright）纳入 MF，还是先手动验收

现在开始 MF-U1，先给我实现计划（目录树 + 关键文件 + compose 改动），我确认后再动手。
