"""M1-U3：密码哈希与 JWT 工具的边界测试，含算法锁定安全用例。"""

import uuid

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.security import (
    ALGORITHM,
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# ── 密码 ────────────────────────────────────────────────


def test_hash_and_verify_roundtrip():
    h = hash_password("correct horse battery")
    assert h != "correct horse battery"  # 不明文存储
    assert verify_password("correct horse battery", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("right-password")
    assert verify_password("wrong-password", h) is False


def test_same_password_different_hashes():
    # bcrypt 加盐，两次哈希不同
    assert hash_password("samepw12") != hash_password("samepw12")


# ── JWT ─────────────────────────────────────────────────


def test_token_roundtrip_carries_claims():
    uid = uuid.uuid4()
    token = create_access_token(user_id=uid, role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["role"] == "admin"


def test_decode_rejects_tampered_token():
    token = create_access_token(user_id=uuid.uuid4(), role="internal")
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    with pytest.raises(TokenError):
        decode_access_token(tampered)


def test_decode_rejects_alg_none():
    """安全用例：拒绝 alg=none 的未签名 token（SECURITY #9）。

    jose 不允许 encode alg=none，故手工构造未签名 token，验证 decode 拒绝它。
    """
    import base64
    import json

    def b64(d: dict) -> str:
        raw = json.dumps(d, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = b64({"alg": "none", "typ": "JWT"})
    payload = b64({"sub": str(uuid.uuid4()), "role": "admin"})
    forged = f"{header}.{payload}."  # 空签名
    with pytest.raises(TokenError):
        decode_access_token(forged)


def test_decode_rejects_wrong_secret():
    settings = get_settings()
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "admin"},
        key=settings.jwt_secret + "-tampered",
        algorithm=ALGORITHM,
    )
    with pytest.raises(TokenError):
        decode_access_token(forged)
