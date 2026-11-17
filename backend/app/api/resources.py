"""Resource API — global shared tool bookmarks and HTML files.

Read:  any authenticated user.
Write: admin only (require_admin).
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user, require_admin
from app.models.auth import User
from app.storage.local import StorageError
from app.schemas.resource import ResourceCreate, ResourcePublic, ResourceUpdate
from app.services.resource_service import (
    create_resource_html,
    create_resource_url,
    delete_resource,
    get_creator_emails,
    get_resource_or_404,
    list_resources,
    replace_resource_file,
    update_resource,
)
from app.storage.base import get_storage

router = APIRouter(prefix="/resources", tags=["resources"])


def _enrich(resources: list, emails: dict) -> list[ResourcePublic]:
    out = []
    for r in resources:
        pub = ResourcePublic.model_validate(r)
        pub.created_by_email = emails.get(r.created_by) if r.created_by else None
        out.append(pub)
    return out


@router.get("", response_model=list[ResourcePublic])
async def list_all(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ResourcePublic]:
    resources = await list_resources(session)
    emails = await get_creator_emails(
        session, {r.created_by for r in resources if r.created_by}
    )
    return _enrich(resources, emails)


@router.post("", response_model=ResourcePublic, status_code=status.HTTP_201_CREATED)
async def create_url_resource(
    body: ResourceCreate,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ResourcePublic:
    """Create a URL-type resource (JSON body)."""
    if body.type != "url":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "此端点仅支持 url 类型")
    resource = await create_resource_url(
        session,
        title=body.title,
        description=body.description,
        url=body.url,  # type: ignore[arg-type]
        created_by=current_user.id,
    )
    emails = await get_creator_emails(session, {current_user.id})
    return _enrich([resource], emails)[0]


@router.post(
    "/upload",
    response_model=ResourcePublic,
    status_code=status.HTTP_201_CREATED,
)
async def upload_html_resource(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str | None = Form(default=None),
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ResourcePublic:
    """Upload an HTML file resource (multipart/form-data)."""
    if not file.filename or not file.filename.lower().endswith(".html"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "仅支持 .html 文件"
        )
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "文件不超过 5 MB")
    resource = await create_resource_html(
        session,
        title=title,
        description=description,
        data=data,
        created_by=current_user.id,
    )
    emails = await get_creator_emails(session, {current_user.id})
    return _enrich([resource], emails)[0]


@router.patch("/{resource_id}", response_model=ResourcePublic)
async def update_one(
    resource_id: uuid.UUID,
    body: ResourceUpdate,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ResourcePublic:
    resource = await get_resource_or_404(session, resource_id)
    resource = await update_resource(
        session,
        resource=resource,
        title=body.title,
        description=body.description,
        url=body.url,
    )
    emails = await get_creator_emails(
        session, {resource.created_by} if resource.created_by else set()
    )
    return _enrich([resource], emails)[0]


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one(
    resource_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    resource = await get_resource_or_404(session, resource_id)
    await delete_resource(session, resource=resource)


@router.post("/{resource_id}/file", response_model=ResourcePublic)
async def replace_file(
    resource_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ResourcePublic:
    """Replace the HTML file of an existing html-type resource."""
    resource = await get_resource_or_404(session, resource_id)
    if resource.type != "html":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "仅 HTML 类型资源支持文件替换")
    if not file.filename or not file.filename.lower().endswith(".html"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "仅支持 .html 文件")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "文件不超过 5 MB")
    resource = await replace_resource_file(session, resource=resource, data=data)
    emails = await get_creator_emails(
        session, {resource.created_by} if resource.created_by else set()
    )
    return _enrich([resource], emails)[0]


@router.get("/{resource_id}/file")
async def get_html_file(
    resource_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return HTML file bytes for in-browser blob rendering."""
    resource = await get_resource_or_404(session, resource_id)
    if resource.type != "html" or not resource.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该资源无附件")
    storage = get_storage()
    try:
        data = await storage.read_bytes(resource.storage_key)
    except (StorageError, FileNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件已丢失，请重新上传")
    return Response(
        content=data,
        media_type="text/html",
        headers={"X-Content-Type-Options": "nosniff"},
    )
