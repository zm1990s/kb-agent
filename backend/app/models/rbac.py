"""F5-F7 · 用户组、入组规则、RBAC 权限、空间按组授权。与 migration 008 对齐。"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# RBAC 模块与权限级别
MODULES = (
    "chat",
    "chatplus",
    "cases",
    "documents",
    "workspaces",
    "users",
    "settings",
    "stats",
    "whatsnew",
    "skills",
)
LEVELS = ("none", "read", "write")
RULE_FIELDS = ("email_domain", "email", "role")
RULE_OPS = ("equals", "endswith", "contains")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class GroupRule(Base):
    __tablename__ = "group_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(String, nullable=False)
    op: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("ix_group_rules_group", "group_id"),)


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (Index("ix_group_members_user", "user_id"),)


class GroupPermission(Base):
    __tablename__ = "group_permissions"

    group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    module: Mapped[str] = mapped_column(String, primary_key=True)
    level: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "level IN ('none', 'read', 'write')", name="group_permissions_level_check"
        ),
    )


class WorkspaceGroupGrant(Base):
    __tablename__ = "workspace_group_grants"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_in_ws: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "role_in_ws IN ('owner', 'editor', 'viewer')",
            name="ws_group_grants_role_check",
        ),
        Index("ix_ws_group_grants_group", "group_id"),
    )
