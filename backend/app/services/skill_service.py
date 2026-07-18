"""Skill 管理 service：CRUD、权限检查、审计日志。"""

import logging
import uuid
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.skill import Skill, SkillAuditLog, SkillGroupPermission

logger = logging.getLogger(__name__)


async def _write_audit(
    session: AsyncSession,
    *,
    skill: Skill,
    user: User,
    action: str,
    detail: dict | None = None,
) -> None:
    log = SkillAuditLog(
        id=uuid.uuid4(),
        workspace_id=skill.workspace_id,
        skill_id=skill.id,
        user_id=user.id,
        action=action,
        detail=detail or {},
    )
    session.add(log)


# ── 可见性检查 ────────────────────────────────────────────────────────────────

async def check_skill_access(
    session: AsyncSession,
    *,
    user: User,
    skill: Skill,
    level: Literal["read", "write"],
) -> bool:
    """返回 True = 有权限。admin 绕过一切。"""
    if user.role == "admin":
        return True
    if level == "read" and skill.is_public:
        return True
    if skill.created_by == user.id:
        return True
    result = await session.execute(
        select(SkillGroupPermission).where(
            SkillGroupPermission.skill_id == skill.id,
            SkillGroupPermission.level == level,
        )
    )
    perm_rows = result.scalars().all()
    if not perm_rows:
        return False
    group_ids = {p.group_id for p in perm_rows}
    from app.models.rbac import GroupMember
    member_result = await session.execute(
        select(GroupMember).where(
            GroupMember.group_id.in_(group_ids),
            GroupMember.user_id == user.id,
        )
    )
    return member_result.scalars().first() is not None


# ── 查询 ──────────────────────────────────────────────────────────────────────

async def list_visible_skills(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: uuid.UUID | None = None,
) -> list[Skill]:
    """返回用户可见的 Skill（公开 + 有 read 权限的私有）。"""
    q = select(Skill)
    if workspace_id is not None:
        q = q.where(
            (Skill.workspace_id == workspace_id) | (Skill.workspace_id.is_(None))
        )
    if user.role != "admin":
        from app.models.rbac import GroupMember
        member_result = await session.execute(
            select(GroupMember.group_id).where(GroupMember.user_id == user.id)
        )
        user_group_ids = [r for (r,) in member_result.all()]
        readable_skill_ids_result = await session.execute(
            select(SkillGroupPermission.skill_id).where(
                SkillGroupPermission.group_id.in_(user_group_ids),
                SkillGroupPermission.level.in_(["read", "write"]),
            )
        )
        readable_ids = [r for (r,) in readable_skill_ids_result.all()]
        q = q.where(
            (Skill.is_public == True)  # noqa: E712
            | (Skill.created_by == user.id)
            | (Skill.id.in_(readable_ids))
        )
    q = q.order_by(Skill.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def list_hub_skills(
    session: AsyncSession,
    *,
    user: User,
    search: str | None = None,
    category: str | None = None,
) -> list[Skill]:
    """全平台 Skill Hub 列表：可选搜索（名称/描述/标签）与分类筛选。

    可见性沿用 list_visible_skills 规则（公开 ∪ 创建者 ∪ 有 read 权限的组）。
    """
    q = select(Skill)
    if user.role != "admin":
        from app.models.rbac import GroupMember

        member_result = await session.execute(
            select(GroupMember.group_id).where(GroupMember.user_id == user.id)
        )
        user_group_ids = [r for (r,) in member_result.all()]
        readable_result = await session.execute(
            select(SkillGroupPermission.skill_id).where(
                SkillGroupPermission.group_id.in_(user_group_ids),
                SkillGroupPermission.level.in_(["read", "write"]),
            )
        )
        readable_ids = [r for (r,) in readable_result.all()]
        q = q.where(
            (Skill.is_public == True)  # noqa: E712
            | (Skill.created_by == user.id)
            | (Skill.id.in_(readable_ids))
        )
    if category:
        q = q.where(Skill.category == category)
    if search:
        like = f"%{search}%"
        q = q.where(
            Skill.name.ilike(like)
            | Skill.description.ilike(like)
            | Skill.content.ilike(like)
        )
    q = q.order_by(Skill.updated_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


def parse_skill_upload(filename: str, data: bytes, *, derive: bool = True) -> dict:
    """从上传文件解析 Skill 字段。

    遵循 Anthropic Agent Skills 约定——入口文件必须名为 SKILL.md：
    - 单文件：文件名必须是 SKILL.md（不区分大小写）；
    - .zip / .skill（zip 格式）：文件名不限，但包内必须含 SKILL.md（不区分大小写）。
    返回 {name, description, content, category, tags}。

    derive=True（默认，创建时用）：frontmatter 缺 name/description 时从文件名/首个
      标题/首段派生，尽量给出可用值。
    derive=False（预览时用）：name/description/category/tags 只取 frontmatter 中显式
      存在的值，缺失则留空（name/description/category=None、tags=[]），供前端让用户填写。
    """
    import io
    import re
    import zipfile
    from pathlib import PurePosixPath

    lower = filename.lower()
    base_lower = PurePosixPath(filename).name.lower()

    def _parse_md(text: str, default_name: str) -> dict:
        name: str | None = None
        description: str | None = None
        category: str | None = None
        tags: list[str] = []
        body = text
        # 解析 YAML frontmatter（--- 包裹的简单 key: value）
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if fm_match:
            fm, body = fm_match.group(1), fm_match.group(2)
            for line in fm.splitlines():
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key = key.strip().lower()
                val = val.strip().strip("\"'")
                if key == "name" and val:
                    name = val
                elif key in ("description", "desc") and val:
                    description = val
                elif key == "category" and val:
                    category = val
                elif key == "tags" and val:
                    val = val.strip("[]")
                    tags = [t.strip().strip("\"'") for t in val.split(",") if t.strip()]
        if derive:
            # 无 frontmatter name：取首个 # 标题，再退回文件名
            if not name:
                h = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
                name = h.group(1).strip() if h else default_name
            # 无显式描述时，从正文首个非空/非标题段落派生一句简介
            if not description:
                for para in re.split(r"\n\s*\n", body.strip()):
                    line = para.strip()
                    if not line or line.startswith("#"):
                        continue
                    snippet = " ".join(line.split())
                    description = snippet[:120] + ("…" if len(snippet) > 120 else "")
                    break
        return {
            "name": name,
            "description": description,
            "content": body.strip(),
            "category": category,
            "tags": tags,
            "has_bundle": False,
        }

    default_name = re.sub(
        r"\.(md|zip|skill)$", "", PurePosixPath(filename).name, flags=re.IGNORECASE
    )

    # 单文件：必须是 SKILL.md（标准入口名，不区分大小写）
    if base_lower == "skill.md":
        return _parse_md(data.decode("utf-8", errors="replace"), default_name)
    if lower.endswith(".md"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "单文件必须命名为 SKILL.md"
        )

    # 压缩包：文件名不限，但包内必须含 SKILL.md（按 basename 精确匹配，不区分大小写）
    if lower.endswith(".zip") or lower.endswith(".skill"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                infos = zf.infolist()
                target = next(
                    (i.filename for i in infos
                     if PurePosixPath(i.filename).name.lower() == "skill.md"),
                    None,
                )
                if target is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, "压缩包内未找到 SKILL.md"
                    )
                text = zf.read(target).decode("utf-8", errors="replace")
                parsed = _parse_md(text, default_name)
                # 判断是否为多文件包：除 SKILL.md 外还有普通文件（忽略目录条目）
                parsed["has_bundle"] = any(
                    i.filename != target and not i.is_dir()
                    for i in infos
                )
                return parsed
        except zipfile.BadZipFile as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "无效的 zip/skill 文件"
            ) from exc

    raise HTTPException(
        status.HTTP_400_BAD_REQUEST, "仅支持 SKILL.md 或含 SKILL.md 的 .zip / .skill"
    )


async def get_skill(
    session: AsyncSession,
    *,
    skill_id: uuid.UUID,
    user: User,
) -> Skill:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill 不存在")
    if not await check_skill_access(session, user=user, skill=skill, level="read"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该 Skill")
    return skill


# ── 写操作 ────────────────────────────────────────────────────────────────────

async def create_skill(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: uuid.UUID | None,
    name: str,
    description: str | None,
    content: str,
    is_public: bool,
    category: str | None = None,
    tags: list[str] | None = None,
    bundle_data: bytes | None = None,
) -> Skill:
    """创建 Skill。bundle_data 非空时表示这是多文件包：整包存入 storage，
    bundle_key 指向它（服务端生成 key，不含客户端文件名）。"""
    skill = Skill(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name=name,
        description=description,
        content=content,
        category=category,
        tags=tags or [],
        is_public=is_public,
        created_by=user.id,
    )
    session.add(skill)
    await session.flush()  # 拿到 skill.id

    if bundle_data is not None:
        from app.storage.base import get_storage

        bundle_key = f"skills/{skill.id}/bundle.zip"
        await get_storage().save(bundle_key, bundle_data)
        skill.bundle_key = bundle_key

    await _write_audit(session, skill=skill, user=user, action="created")
    await session.commit()
    await session.refresh(skill)
    return skill


async def update_skill(
    session: AsyncSession,
    *,
    skill_id: uuid.UUID,
    user: User,
    name: str | None = None,
    description: str | None = None,
    content: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
) -> Skill:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill 不存在")
    if not await check_skill_access(session, user=user, skill=skill, level="write"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权修改该 Skill")
    diff: dict = {}
    if name is not None and name != skill.name:
        diff["name"] = {"old": skill.name, "new": name}
        skill.name = name
    if description is not None and description != skill.description:
        diff["description"] = {"old": skill.description, "new": description}
        skill.description = description
    if content is not None and content != skill.content:
        diff["content_changed"] = True
        skill.content = content
    if category is not None and category != skill.category:
        diff["category"] = {"old": skill.category, "new": category}
        skill.category = category
    if tags is not None and tags != list(skill.tags or []):
        diff["tags"] = {"old": list(skill.tags or []), "new": tags}
        skill.tags = tags
    if diff:
        await _write_audit(session, skill=skill, user=user, action="updated", detail=diff)
    await session.commit()
    await session.refresh(skill)
    return skill


async def delete_skill(
    session: AsyncSession,
    *,
    skill_id: uuid.UUID,
    user: User,
) -> None:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill 不存在")
    if not await check_skill_access(session, user=user, skill=skill, level="write"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权删除该 Skill")
    await _write_audit(session, skill=skill, user=user, action="deleted")
    await session.delete(skill)
    await session.commit()


async def set_skill_visibility(
    session: AsyncSession,
    *,
    skill_id: uuid.UUID,
    user: User,
    is_public: bool,
) -> Skill:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill 不存在")
    if not await check_skill_access(session, user=user, skill=skill, level="write"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权修改该 Skill")
    old = skill.is_public
    skill.is_public = is_public
    await _write_audit(
        session,
        skill=skill,
        user=user,
        action="visibility_changed",
        detail={"old": old, "new": is_public},
    )
    await session.commit()
    await session.refresh(skill)
    return skill


async def grant_skill_permission(
    session: AsyncSession,
    *,
    skill_id: uuid.UUID,
    group_id: uuid.UUID,
    level: str,
    user: User,
) -> SkillGroupPermission:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill 不存在")
    if not await check_skill_access(session, user=user, skill=skill, level="write"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权管理该 Skill 权限")
    result = await session.execute(
        select(SkillGroupPermission).where(
            SkillGroupPermission.skill_id == skill_id,
            SkillGroupPermission.group_id == group_id,
        )
    )
    perm = result.scalars().first()
    if perm is None:
        perm = SkillGroupPermission(
            id=uuid.uuid4(), skill_id=skill_id, group_id=group_id, level=level
        )
        session.add(perm)
        action = "permission_granted"
    else:
        perm.level = level
        action = "permission_granted"
    await _write_audit(
        session,
        skill=skill,
        user=user,
        action=action,
        detail={"group_id": str(group_id), "level": level},
    )
    await session.commit()
    await session.refresh(perm)
    return perm


async def revoke_skill_permission(
    session: AsyncSession,
    *,
    skill_id: uuid.UUID,
    group_id: uuid.UUID,
    user: User,
) -> None:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill 不存在")
    if not await check_skill_access(session, user=user, skill=skill, level="write"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权管理该 Skill 权限")
    result = await session.execute(
        select(SkillGroupPermission).where(
            SkillGroupPermission.skill_id == skill_id,
            SkillGroupPermission.group_id == group_id,
        )
    )
    perm = result.scalars().first()
    if perm is not None:
        await _write_audit(
            session,
            skill=skill,
            user=user,
            action="permission_revoked",
            detail={"group_id": str(group_id)},
        )
        await session.delete(perm)
        await session.commit()


# ── 上传者 / 下载 ──────────────────────────────────────────────────────────────

async def resolve_creator_emails(
    session: AsyncSession, skills: list[Skill]
) -> dict[uuid.UUID, str]:
    """批量解析 created_by → email，返回 {user_id: email}。"""
    ids = {s.created_by for s in skills if s.created_by is not None}
    if not ids:
        return {}
    result = await session.execute(select(User.id, User.email).where(User.id.in_(ids)))
    return {uid: email for uid, email in result.all()}


def build_skill_markdown(skill: Skill) -> str:
    """把 Skill 序列化为带 YAML frontmatter 的 SKILL.md 文本。"""
    lines = ["---", f"name: {skill.name}"]
    if skill.description:
        lines.append(f"description: {skill.description}")
    if skill.category:
        lines.append(f"category: {skill.category}")
    if skill.tags:
        tags = ", ".join(skill.tags)
        lines.append(f"tags: [{tags}]")
    lines.append("---")
    lines.append("")
    lines.append(skill.content)
    return "\n".join(lines)


def _safe_slug(name: str) -> str:
    import re

    slug = re.sub(r"[^\w\-]+", "-", name, flags=re.UNICODE).strip("-")
    return slug or "skill"


async def build_skill_download(
    session: AsyncSession, *, skill_id: uuid.UUID, user: User, fmt: str
) -> tuple[bytes, str, str]:
    """构造 Skill 下载包，返回 (bytes, filename, media_type)。

    fmt='zip' 或 'skill'（均为 zip 容器，内含 <slug>/SKILL.md）。
    """
    import io
    import zipfile

    skill = await get_skill(session, skill_id=skill_id, user=user)
    slug = _safe_slug(skill.name)
    ext = "skill" if fmt == "skill" else "zip"

    # 多文件包：直接返回保存的原始整包，完整往返（含附属文件）
    if skill.bundle_key:
        from app.storage.base import get_storage
        from app.storage.local import StorageError

        try:
            data = await get_storage().read_bytes(skill.bundle_key)
            return data, f"{slug}.{ext}", "application/zip"
        except (FileNotFoundError, StorageError):
            logger.warning("skill bundle 缺失，回退单文件下载 skill=%s", skill.id)

    # 纯文本 Skill：按 DB 字段重建单文件 SKILL.md 包
    md = build_skill_markdown(skill)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{slug}/SKILL.md", md)
    data = buf.getvalue()
    return data, f"{slug}.{ext}", "application/zip"


# ── 审计日志查询 ──────────────────────────────────────────────────────────────

async def list_audit_logs(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | None = None,
    skill_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[SkillAuditLog]:
    q = select(SkillAuditLog).order_by(SkillAuditLog.created_at.desc()).limit(limit)
    if workspace_id is not None:
        q = q.where(SkillAuditLog.workspace_id == workspace_id)
    if skill_id is not None:
        q = q.where(SkillAuditLog.skill_id == skill_id)
    result = await session.execute(q)
    return list(result.scalars().all())
