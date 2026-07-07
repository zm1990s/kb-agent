治理层：为 KB-Agent 建立自动化护栏与审查流程。

1. 创建 .claude/hooks/pre-tool-use-guard.sh：拦截危险命令（rm -rf、修改 .env、DROP TABLE、直连 LLM SDK 的 import 如 anthropic/openai）
2. 创建 .claude/hooks/post-tool-use-lint.sh：对改动过的 .py 文件跑 ruff + pyright
3. 创建 .claude/agents/reviewer.md：两阶段 Review
   - 阶段一 Spec Compliance：API 路径/数据模型是否与 DESIGN.md 一致；workspace 隔离是否强制；LLM 是否只经 engine/；skill 写操作是否走审批
   - 阶段二 Code Quality：分层是否清晰、api 层无业务逻辑、测试覆盖 happy+error
4. 创建 .claude/settings.local.json 注册 hooks
5. 用 reviewer 对当前代码跑一次 review，输出报告

本项目 Review 必查红线：
- **越权/IDOR**：每个资源端点是否校验 workspace 归属（不只校验登录）；workspace 过滤是否下沉到 SQL 层；非成员访问是否被拒且有测试
- **路径穿越**：storage_key 是否服务端生成（非客户端文件名）；open_path/download 是否 realpath 校验落在 LOCAL_STORAGE_DIR 内；下载参数是否被直接拼进路径
- **下载渲染**：下载响应是否强制 Content-Disposition: attachment + X-Content-Type-Options: nosniff
- 跨 workspace 数据泄漏
- 硬编码密钥
- 绕过 engine/ 直连 LLM
- skill 写操作绕过 approve
