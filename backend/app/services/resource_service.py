"""Resource business logic — global shared tool bookmarks and HTML files."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.resource import Resource
from app.storage.base import get_storage


class ResourceNotFoundError(Exception):
    pass


def _resource_key() -> str:
    """Server-generated storage key for resource HTML files (no workspace prefix)."""
    return f"resources/{uuid.uuid4().hex}"


async def list_resources(session: AsyncSession) -> list[Resource]:
    result = await session.execute(
        select(Resource).order_by(Resource.created_at.desc())
    )
    return list(result.scalars().all())


async def get_resource_or_404(session: AsyncSession, resource_id: uuid.UUID) -> Resource:
    resource = await session.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")
    return resource


async def create_resource_url(
    session: AsyncSession,
    *,
    title: str,
    description: str | None,
    url: str,
    created_by: uuid.UUID,
) -> Resource:
    resource = Resource(
        id=uuid.uuid4(),
        title=title,
        description=description,
        type="url",
        url=url,
        created_by=created_by,
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return resource


async def create_resource_html(
    session: AsyncSession,
    *,
    title: str,
    description: str | None,
    data: bytes,
    created_by: uuid.UUID,
) -> Resource:
    storage = get_storage()
    key = _resource_key()
    await storage.save(key, data)
    resource = Resource(
        id=uuid.uuid4(),
        title=title,
        description=description,
        type="html",
        storage_key=key,
        created_by=created_by,
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return resource


async def delete_resource(session: AsyncSession, *, resource: Resource) -> None:
    if resource.storage_key:
        storage = get_storage()
        try:
            await storage.delete(resource.storage_key)
        except FileNotFoundError:
            pass
    await session.delete(resource)
    await session.commit()


async def replace_resource_file(
    session: AsyncSession,
    *,
    resource: Resource,
    data: bytes,
) -> Resource:
    """Replace the HTML file of a resource; delete old file, save new one."""
    storage = get_storage()
    # Save new file first (fail-safe: don't delete old until new is saved)
    new_key = _resource_key()
    await storage.save(new_key, data)
    # Delete old file
    if resource.storage_key:
        try:
            await storage.delete(resource.storage_key)
        except FileNotFoundError:
            pass
    resource.storage_key = new_key
    await session.commit()
    await session.refresh(resource)
    return resource


async def update_resource(
    session: AsyncSession,
    *,
    resource: Resource,
    title: str | None,
    description: str | None,
    url: str | None,
) -> Resource:
    if title is not None:
        resource.title = title
    if description is not None or url is not None:
        # allow explicit null to clear description; url only on url-type resources
        resource.description = description
        if resource.type == "url" and url is not None:
            resource.url = url
    await session.commit()
    await session.refresh(resource)
    return resource


async def get_creator_emails(
    session: AsyncSession, user_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    result = await session.execute(
        select(User.id, User.email).where(User.id.in_(user_ids))
    )
    return {row.id: row.email for row in result}
