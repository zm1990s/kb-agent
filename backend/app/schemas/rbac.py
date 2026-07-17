"""F4-F7 · 用户管理 / 用户组 / RBAC schema。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── F4 用户 ────────────────────────────────────────────

class UserAdminView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    email_verified: bool
    created_at: datetime


class SetActiveRequest(BaseModel):
    is_active: bool


class SetRoleRequest(BaseModel):
    role: Literal["admin", "user"]


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


# ── F5 组 ──────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class GroupPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None


class GroupRuleCreate(BaseModel):
    field: Literal["email_domain", "email", "role"]
    op: Literal["equals", "endswith", "contains"]
    value: str = Field(min_length=1, max_length=200)


class GroupRulePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    field: str
    op: str
    value: str


# ── F6 RBAC ────────────────────────────────────────────

class PermissionSet(BaseModel):
    module: Literal["chat", "documents", "workspaces", "users", "settings", "stats", "whatsnew"]
    level: Literal["none", "read", "write"]


class GroupPermissionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module: str
    level: str
