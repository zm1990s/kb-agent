"""M1 · 认证与空间的请求/响应 schema。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ── 认证 ────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: str
    created_at: datetime
    email_verification_pending: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  # 非密码，OAuth token 类型字面量
    role: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: str
    created_at: datetime


# ── 空间 ────────────────────────────────────────────────


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class WorkspacePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class WorkspaceWithRole(WorkspacePublic):
    """空间列表返回：附带当前用户在该空间的角色。"""

    role_in_ws: str


class MemberAddRequest(BaseModel):
    user_id: uuid.UUID | None = None
    email: str | None = None
    role_in_ws: Literal["owner", "editor", "viewer"]


class AllowedDomainCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=253)


class AllowedDomainPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    domain: str
