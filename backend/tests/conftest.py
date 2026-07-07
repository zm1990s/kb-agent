"""测试夹具：在导入应用前注入最小必需的环境变量。"""

import os
import tempfile

# 在任何 app.* 导入之前设置环境变量（config 用 lru_cache 读取）
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://kbagent:kbagent@localhost/kbagent")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-prod")
os.environ.setdefault("ALLOWED_EMAIL_DOMAINS", "company.com")
os.environ.setdefault("LOCAL_STORAGE_DIR", tempfile.mkdtemp(prefix="kb_test_store_"))
