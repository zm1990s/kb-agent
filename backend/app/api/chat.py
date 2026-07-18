"""对话检索路由。仅限所属空间；串起检索→生成→落库。"""

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationHistory,
    ConversationSummary,
    ConversationUpdate,
    MessagePublic,
    SourceRef,
)
from app.services.answer_service import (
    AnswerResult,
    Stage,
    ThinkingChunk,
    TokenChunk,
    answer_question,
    answer_question_streamed,
)
from app.services.answer_service_plus import (
    OutputFilesResult,
    answer_question_plus_streamed,
)
from app.services.chat_service import (
    add_message,
    create_conversation,
    delete_conversation,
    generate_conversation_title,
    get_conversation_for_user,
    get_or_create_conversation,
    list_conversations,
    list_messages,
    recent_history,
    update_conversation,
)
from app.services.usage_service import record_event
from app.services.workspace_service import is_member

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


async def _require_module(session: AsyncSession, user: User, module: str) -> None:
    """要求用户对指定模块有权限（≥read）；admin 绕过。否则 403。

    聊天准入门闸：chat 端点用 "chat"，聊天+ 端点用 "chatplus"。
    与「能否访问某空间数据」（is_member）正交——两者都要过。
    """
    if user.role == "admin":
        return
    from app.services.rbac_service import effective_permissions

    perms = await effective_permissions(session, user=user)
    if perms.get(module, "none") == "none":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无该功能权限")


def _module_for_source(source: str) -> str:
    """会话来源 → RBAC 模块名。"""
    return "chatplus" if source == "chatplus" else "chat"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    # 聊天功能准入（chat 模块权限）+ 空间成员资格（越权校验 SECURITY #4）
    await _require_module(session, current_user, "chat")
    if not await is_member(
        session, workspace_id=body.workspace_id, user_id=current_user.id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")

    conv = await get_or_create_conversation(
        session,
        conversation_id=body.conversation_id,
        workspace_id=body.workspace_id,
        user_id=current_user.id,
    )
    # 先取历史（不含本轮提问），供 Agent 理解上下文
    history = await recent_history(session, conversation_id=conv.id)

    await add_message(
        session, conversation_id=conv.id, role="user", content=body.message
    )

    result = await answer_question(
        session,
        workspace_id=body.workspace_id,
        question=body.message,
        history=history,
    )

    await add_message(
        session,
        conversation_id=conv.id,
        role="assistant",
        content=result.answer,
        sources=result.sources,
    )

    logger.info(
        "audit chat user=%s workspace=%s conversation=%s q_len=%d a_len=%d",
        current_user.id,
        body.workspace_id,
        conv.id,
        len(body.message),
        len(result.answer),
    )

    async def _log_chat() -> None:
        async with SessionLocal() as s:
            await record_event(
                s,
                action="chat",
                user_id=current_user.id,
                workspace_id=body.workspace_id,
                meta={
                    "conversation_id": str(conv.id),
                    "question": body.message,
                    "answer": result.answer,
                },
            )

    background_tasks.add_task(_log_chat)
    return ChatResponse(
        answer=result.answer,
        sources=[SourceRef(**s) for s in result.sources],
        conversation_id=conv.id,
    )


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """SSE 流式对话：先推送 Agent 工作阶段，最后推送答案+来源。"""
    await _require_module(session, current_user, "chat")
    if not await is_member(
        session, workspace_id=body.workspace_id, user_id=current_user.id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")

    is_new_conv = body.conversation_id is None
    conv = await get_or_create_conversation(
        session,
        conversation_id=body.conversation_id,
        workspace_id=body.workspace_id,
        user_id=current_user.id,
        source="chat",
    )
    history = await recent_history(session, conversation_id=conv.id)
    await add_message(
        session, conversation_id=conv.id, role="user", content=body.message
    )

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def gen():
        final: AnswerResult | None = None
        async for item in answer_question_streamed(
            session,
            workspace_id=body.workspace_id,
            question=body.message,
            history=history,
        ):
            if isinstance(item, Stage):
                yield sse("stage", {
                    "stage": item.stage,
                    "message_key": item.message_key,
                    "message_params": item.message_params,
                })
            elif isinstance(item, ThinkingChunk):
                yield sse("thinking", {"text": item.text})
            elif isinstance(item, TokenChunk):
                yield sse("token", {"text": item.text})
            elif isinstance(item, AnswerResult):
                final = item
        if final is None:
            final = AnswerResult(answer="", sources=[], error_key="no_answer")
        # 先发 done，让前端立即收到答案，不阻塞在后续 DB 写入和标题生成
        done_payload: dict = {
            "answer": final.answer,
            "sources": final.sources,
            "conversation_id": str(conv.id),
        }
        if final.error_key:
            done_payload["error_key"] = final.error_key
        yield sse("done", done_payload)
        # 落库助手消息（done 已发，后续延迟不影响用户体验）
        await add_message(
            session,
            conversation_id=conv.id,
            role="assistant",
            content=final.answer,
            sources=final.sources,
        )
        logger.info(
            "audit chat_stream user=%s workspace=%s conversation=%s q_len=%d a_len=%d",
            current_user.id,
            body.workspace_id,
            conv.id,
            len(body.message),
            len(final.answer),
        )
        async with SessionLocal() as audit_session:
            await record_event(
                audit_session,
                action="chat",
                user_id=current_user.id,
                workspace_id=body.workspace_id,
                meta={
                    "conversation_id": str(conv.id),
                    "question": body.message,
                    "answer": final.answer,
                },
            )
        # 新会话：生成标题，写入 DB 后推送 title 事件让前端直接更新侧边栏
        if is_new_conv:
            async with SessionLocal() as bg_session:
                title = await generate_conversation_title(
                    bg_session,
                    conversation_id=conv.id,
                    first_message=body.message,
                )
            if title:
                yield sse("title", {"conversation_id": str(conv.id), "title": title})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=list[ConversationSummary])
async def get_conversations(
    workspace_id: uuid.UUID | None = None,
    source: str = "chat",
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationSummary]:
    # 按会话来源校验对应模块权限（chat / chatplus）
    await _require_module(session, current_user, _module_for_source(source))
    # workspace_id 为空时不按空间过滤（聊天+ 会话不分空间）；传入时校验成员权限
    if workspace_id is not None and not await is_member(
        session, workspace_id=workspace_id, user_id=current_user.id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")
    convs = await list_conversations(
        session, workspace_id=workspace_id, user_id=current_user.id, source=source
    )
    return [ConversationSummary.model_validate(c) for c in convs]


@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
async def new_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationSummary:
    await _require_module(session, current_user, _module_for_source(body.source))
    if not await is_member(
        session, workspace_id=body.workspace_id, user_id=current_user.id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")
    conv = await create_conversation(
        session,
        workspace_id=body.workspace_id,
        user_id=current_user.id,
        source=body.source,
    )
    return ConversationSummary.model_validate(conv)


@router.get("/conversations/{conversation_id}", response_model=ConversationHistory)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationHistory:
    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(conv.source))
    msgs = await list_messages(session, conversation_id=conv.id)
    return ConversationHistory(
        conversation_id=conv.id,
        messages=[MessagePublic.model_validate(m) for m in msgs],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_endpoint(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """删除会话及其所有消息（仅限归属本人）。"""
    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(conv.source))
    ok = await delete_conversation(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
async def patch_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationSummary:
    """更新会话标题或置顶状态。"""
    existing = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(existing.source))
    conv = await update_conversation(
        session,
        conversation_id=conversation_id,
        user_id=current_user.id,
        title=body.title,
        pinned=body.pinned,
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    return ConversationSummary.model_validate(conv)


# ── 聊天+ 扩展端点 ────────────────────────────────────────────────────────────


class ChatPlusAttachment(BaseModel):
    storage_key: str
    filename: str
    size: int = 0


class ChatPlusRequest(BaseModel):
    # 工作区可选：仅当本轮要引用某空间文档时才传（会话本身不绑空间）
    workspace_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    message: str
    skill_ids: list[uuid.UUID] | None = None
    doc_ids: list[uuid.UUID] | None = None
    all_docs: bool = False
    # 附件：携带展示元数据（filename/size）；引擎侧只用 storage_key
    attachments: list[ChatPlusAttachment] | None = None


class ConversationSettingsUpdate(BaseModel):
    active_skill_ids: list[uuid.UUID] | None = None
    doc_filter_ids: list[uuid.UUID] | None = None


class ConversationSettingsPublic(BaseModel):
    conversation_id: uuid.UUID
    active_skill_ids: list[uuid.UUID]
    doc_filter_ids: list[uuid.UUID]


@router.post("/chat/plus/stream")
async def chat_plus_stream(
    body: ChatPlusRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """聊天+ SSE 流式端点：支持 Skill 注入、文档引用、附件、输出文件。

    会话不绑定工作区；仅当本轮传入 workspace_id（引用其文档）时才校验成员权限。
    """
    await _require_module(session, current_user, "chatplus")
    if body.workspace_id is not None and not await is_member(
        session, workspace_id=body.workspace_id, user_id=current_user.id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")

    is_new_conv = body.conversation_id is None
    conv = await get_or_create_conversation(
        session,
        conversation_id=body.conversation_id,
        workspace_id=None,  # 聊天+ 会话不绑定工作区
        user_id=current_user.id,
        source="chatplus",
    )
    history = await recent_history(session, conversation_id=conv.id)
    attachments = [a.model_dump() for a in (body.attachments or [])]
    attachment_keys = [a["storage_key"] for a in attachments]
    await add_message(
        session,
        conversation_id=conv.id,
        role="user",
        content=body.message,
        attachments=attachments,
    )

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def gen():
        final: AnswerResult | None = None
        output_files: list[dict] = []

        try:
            async for item in answer_question_plus_streamed(
                session,
                workspace_id=body.workspace_id,
                conversation_id=conv.id,
                user=current_user,
                question=body.message,
                history=history,
                doc_ids=body.doc_ids,
                all_docs=body.all_docs,
                skill_ids=body.skill_ids,
                attachment_keys=attachment_keys or None,
            ):
                if isinstance(item, Stage):
                    yield sse("stage", {
                        "stage": item.stage,
                        "message_key": item.message_key,
                        "message_params": item.message_params,
                    })
                elif isinstance(item, ThinkingChunk):
                    yield sse("thinking", {"text": item.text})
                elif isinstance(item, TokenChunk):
                    yield sse("token", {"text": item.text})
                elif isinstance(item, AnswerResult):
                    final = item
                elif isinstance(item, OutputFilesResult):
                    output_files = item.files

            if final is None:
                final = AnswerResult(answer="", sources=[], error_key="no_answer")

            done_payload: dict = {
                "answer": final.answer,
                "sources": final.sources,
                "conversation_id": str(conv.id),
            }
            if final.error_key:
                done_payload["error_key"] = final.error_key
            yield sse("done", done_payload)

            if output_files:
                yield sse("output_files", {"files": output_files})

            await add_message(
                session,
                conversation_id=conv.id,
                role="assistant",
                content=final.answer,
                sources=final.sources,
                output_files=output_files,
            )

            if is_new_conv:
                async with SessionLocal() as bg_session:
                    title = await generate_conversation_title(
                        bg_session, conversation_id=conv.id, first_message=body.message
                    )
                if title:
                    yield sse("title", {"conversation_id": str(conv.id), "title": title})

        except Exception:
            logger.exception("plus/stream gen() 内部异常 conv=%s", conv.id)
            yield sse("done", {
                "answer": "",
                "sources": [],
                "conversation_id": str(conv.id),
                "error_key": "engine_unavailable",
            })

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/plus/upload")
async def upload_attachment(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """用户上传附件，返回 storage_key 供聊天+ 请求使用（与工作区解耦）。

    key 由服务端生成（UUID），不含用户可控路径片段（SECURITY #5）。
    """
    import uuid as _uuid

    await _require_module(session, current_user, "chatplus")
    from app.storage.base import get_storage
    data = await file.read()
    key = f"chatplus/uploads/{_uuid.uuid4().hex}"
    storage = get_storage()
    await storage.save(key, data)
    return {"storage_key": key, "filename": file.filename, "size": len(data)}


@router.get("/chat/plus/conversations/{conversation_id}/files")
async def list_conversation_files(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """列出会话工作目录下的所有文件（含 Agent 生成 + 用户上传附件）。

    仅归属当前用户的会话可访问（get_conversation_for_user 已下沉校验）。
    """
    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(conv.source))

    from app.storage.base import get_storage
    storage = get_storage()
    workdir = await storage.resolve_dir(f"chatplus/conv_{conversation_id}")
    files: list[dict] = []
    for entry in sorted(workdir.rglob("*")):
        if not entry.is_file():
            continue
        rel = entry.relative_to(workdir).as_posix()
        # 排除注入的 Skill 附属文件目录（非本会话产物）
        if rel == "skills" or rel.startswith("skills/"):
            continue
        st = entry.stat()
        files.append({
            "filename": rel.rsplit("/", 1)[-1],
            "relpath": rel,
            "size": st.st_size,
            "modified": int(st.st_mtime),
        })
    return files


@router.get("/chat/plus/conversations/{conversation_id}/files/{file_path:path}")
async def download_conversation_file(
    conversation_id: uuid.UUID,
    file_path: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """下载会话工作目录下的某个文件（支持子目录，如 outputs/x.xlsx；带会话归属校验+防穿越）。"""
    from pathlib import PurePosixPath
    from urllib.parse import quote

    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(conv.source))

    # 防穿越：规范化后不得为绝对路径 / 含 .. / 逃出会话目录
    rel = PurePosixPath(file_path)
    if rel.is_absolute() or ".." in rel.parts or not file_path or file_path.endswith("/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法文件路径")

    from app.storage.base import get_storage
    from app.storage.local import StorageError
    storage = get_storage()
    # storage 层 _resolve_within_root 会再次校验落在根目录内（双重防护）
    key = f"chatplus/conv_{conversation_id}/{file_path}"
    try:
        data = await storage.read_bytes(key)
    except (FileNotFoundError, StorageError, IsADirectoryError) as exc:
        # 文件不存在 / 路径越界 / 是目录，均不泄漏细节
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在") from exc

    download_name = rel.name
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(download_name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/conversations/{conversation_id}/settings", response_model=ConversationSettingsPublic)
async def get_conversation_settings(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationSettingsPublic:
    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(conv.source))
    from app.models.chat import ConversationSettings
    settings_obj = await session.get(ConversationSettings, conversation_id)
    if settings_obj is None:
        return ConversationSettingsPublic(
            conversation_id=conversation_id,
            active_skill_ids=[],
            doc_filter_ids=[],
        )
    return ConversationSettingsPublic(
        conversation_id=conversation_id,
        active_skill_ids=list(settings_obj.active_skill_ids or []),
        doc_filter_ids=list(settings_obj.doc_filter_ids or []),
    )


@router.patch(
    "/conversations/{conversation_id}/settings",
    response_model=ConversationSettingsPublic,
)
async def update_conversation_settings(
    conversation_id: uuid.UUID,
    body: ConversationSettingsUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationSettingsPublic:
    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(conv.source))
    from app.models.chat import ConversationSettings
    settings_obj = await session.get(ConversationSettings, conversation_id)
    if settings_obj is None:
        settings_obj = ConversationSettings(conversation_id=conversation_id)
        session.add(settings_obj)
    if body.active_skill_ids is not None:
        settings_obj.active_skill_ids = body.active_skill_ids
    if body.doc_filter_ids is not None:
        settings_obj.doc_filter_ids = body.doc_filter_ids
    await session.commit()
    await session.refresh(settings_obj)
    return ConversationSettingsPublic(
        conversation_id=conversation_id,
        active_skill_ids=list(settings_obj.active_skill_ids or []),
        doc_filter_ids=list(settings_obj.doc_filter_ids or []),
    )
