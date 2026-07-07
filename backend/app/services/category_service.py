"""分类业务逻辑：管理员在空间内维护分类体系（支持层级）。

隔离：分类隶属 workspace；查询/创建都带 workspace 约束。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Category


class ParentCategoryInvalidError(Exception):
    """指定的父分类不存在或不属于同一 workspace。"""


async def create_category(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    parent_id: uuid.UUID | None,
) -> Category:
    """在空间内建分类。父分类必须存在且同属该空间。"""
    if parent_id is not None:
        parent = await session.get(Category, parent_id)
        if parent is None or parent.workspace_id != workspace_id:
            raise ParentCategoryInvalidError(str(parent_id))

    cat = Category(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name=name,
        parent_id=parent_id,
    )
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


async def list_categories(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> list[Category]:
    stmt = (
        select(Category)
        .where(Category.workspace_id == workspace_id)
        .order_by(Category.name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
