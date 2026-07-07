你正在初始化项目 KB-Agent。请只做以下事情，不写任何业务代码：

1. 按照 CLAUDE.md 的目录约定创建空目录结构（backend/app/{api,services,models,schemas,core,engine,skills,storage}、backend/tests、infra/postgres）
2. 生成 .env.example，列出所有需要的环境变量占位（值留空）：
   - DATABASE_URL, JWT_SECRET, JWT_EXPIRE_MIN
   - ALLOWED_EMAIL_DOMAINS（注册域名白名单，逗号分隔，如 company.com,partner-a.com）
   - ENGINE_BACKEND(=claude_cli), CLAUDE_CLI_PATH, CLAUDE_MODEL, ENGINE_TIMEOUT_SEC
   - STORAGE_BACKEND(=local), LOCAL_STORAGE_DIR（本地原文存放目录）
   - DOWNLOAD_URL_TTL_SEC（下载链接有效期）
3. 生成 .gitignore（含 .env、__pycache__/、.venv/、*.pyc、.pytest_cache/）
4. 生成 README.md 骨架（项目简介、技术栈、快速启动、目录说明）
5. 初始化 git 仓库

不允许：写任何 .py/.sql 业务文件。
完成后跑：
  ls *.md .env.example .gitignore
  find backend -type d
  git status --short
输出验收结果。
