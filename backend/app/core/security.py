"""密码哈希与 JWT 工具。

安全要点（SECURITY #9）：
- JWT 签发与校验锁定单一算法（HS256），校验时显式传 algorithms=[ALGORITHM]，
  拒绝 alg=none 及算法混淆攻击。
- 密码用 bcrypt 哈希，不可逆存储。
"""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

ALGORITHM = "HS256"
# bcrypt 限制密码 ≤72 字节；schema 层已限制密码长度，此处再做防御式截断。
_BCRYPT_MAX_BYTES = 72


class TokenError(Exception):
    """JWT 校验失败。"""


# ── 密码 ────────────────────────────────────────────────


def _to_bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(_to_bcrypt_bytes(password), password_hash.encode("utf-8"))


# ── JWT ─────────────────────────────────────────────────


def create_access_token(*, user_id: uuid.UUID, role: str, expire_min: int | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    minutes = expire_min if expire_min is not None else settings.jwt_expire_min
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """校验并解码 JWT；锁定算法，失败抛 TokenError。"""
    settings = get_settings()
    try:
        # 显式限定算法，杜绝 alg=none / 算法混淆
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise TokenError(str(exc)) from exc
    if "sub" not in payload:
        raise TokenError("token 缺少 sub")
    return payload
