"""对话检索路由。仅限所属空间；串起检索→生成→落库。"""

import asyncio
import json
import logging
import time
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
    ConversationExportRequest,
    ConversationExportToLibraryRequest,
    ConversationHistory,
    ConversationSummary,
    ConversationUpdate,
    MessagePublic,
    SaveFileToLibrary,
    SourceRef,
)
from app.schemas.document import DocumentUploadAccepted
from app.services.answer_service import (
    AnswerResult,
    answer_question,
)
from app.services.chat_generation import (
    _END as _GEN_END,
)
from app.services.chat_generation import (
    GenerationInProgress,
    list_active,
    list_active_details,
    request_cancel,
    start_chat_generation,
    start_generation,
    subscribe,
    unsubscribe,
)
from app.services.chat_service import (
    add_message,
    create_conversation,
    delete_conversation,
    get_conversation_for_user,
    get_or_create_conversation,
    list_conversations,
    list_messages,
    recent_history,
    update_conversation,
)
from app.services.settings_service import get_max_upload_mb
from app.services.usage_service import record_event
from app.services.workspace_service import is_member, locate_workspace_by_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _generation_meta(state) -> dict:
    # elapsed_seconds 基于服务器单调时钟，前端据此以本机时钟反推锚点，
    # 免疫客户端/服务端墙钟偏移（详见 list_active_details 注释）。
    return {
        "conversation_id": str(state.conversation_id),
        "started_at": state.started_at_epoch,
        "elapsed_seconds": max(0.0, time.monotonic() - state.started_at),
    }


async def _relay(sub):
    """把订阅到的生成事件转发为 SSE；断连只退订，不动生成任务。

    sub = (state, queue, catchup)：先补发 catchup（已累积答案 + 终态事件），
    再从队列读实时事件，直到 _END。

    事件间隙每 10s 发一个 SSE 注释心跳（`: ping`）：既保活连接，又强制刷出
    被代理/uvicorn 缓冲的响应体——否则重连后若正处于两个 thinking 块之间的
    思考间隙，累积的 catchup 会被缓冲住、直到生成结束才一次性放出（表现为
    「切走返回后 thinking 不再实时更新」）。
    """
    state, queue, catchup = sub
    try:
        for event, data in catchup:
            yield _sse(event, data)
        # catchup 之后立即发一次心跳，破开缓冲、让已补发内容立刻抵达客户端
        yield ": ping\n\n"
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=10)
            except TimeoutError:
                yield ": ping\n\n"  # 空闲心跳，保活并 flush
                continue
            if item is _GEN_END:
                break
            event, data = item
            yield _sse(event, data)
    finally:
        unsubscribe(state, queue)


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
    # workspace_id=None 时自动定位；有明确空间时校验成员资格
    if body.workspace_id is None:
        target_ws: uuid.UUID | list[uuid.UUID] = await locate_workspace_by_query(
            session, user=current_user, query=body.message
        )
    else:
        if not await is_member(session, workspace_id=body.workspace_id, user_id=current_user.id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")
        target_ws = body.workspace_id

    # 会话绑定单个空间（取第一个或指定值）。
    # 自动定位无可访问空间时返回 []，须安全取值避免 [][0] IndexError（否则 500 且不记日志）。
    if isinstance(target_ws, list):
        conv_ws = target_ws[0] if target_ws else None
    else:
        conv_ws = target_ws
    conv = await get_or_create_conversation(
        session,
        conversation_id=body.conversation_id,
        workspace_id=conv_ws if conv_ws else None,
        user_id=current_user.id,
    )
    # 先取历史（不含本轮提问），供 Agent 理解上下文
    history = await recent_history(session, conversation_id=conv.id)

    await add_message(
        session, conversation_id=conv.id, role="user", content=body.message
    )

    if not target_ws:
        result = AnswerResult(answer="", sources=[], error_key="no_docs")
    else:
        result = await answer_question(
            session,
            workspace_id=target_ws,
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
        conv_ws,
        conv.id,
        len(body.message),
        len(result.answer),
    )

    # 自动定位可能命中多个空间，workspace_id 列只记首个；meta 保留完整归因
    ws_all = [str(w) for w in target_ws] if isinstance(target_ws, list) else [str(target_ws)]

    async def _log_chat() -> None:
        async with SessionLocal() as s:
            await record_event(
                s,
                action="chat",
                user_id=current_user.id,
                workspace_id=conv_ws,
                meta={
                    "conversation_id": str(conv.id),
                    "question": body.message,
                    "answer": result.answer,
                    "workspaces": ws_all,
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
    """SSE 流式对话：生成跑在 detached 任务里（断连不中止），本请求只订阅转发。

    对齐聊天+：切走菜单不再掐断生成，返回时可经 GET /chat/stream/{id} 重连续看。
    """
    await _require_module(session, current_user, "chat")
    if body.workspace_id is None:
        target_ws: uuid.UUID | list[uuid.UUID] = await locate_workspace_by_query(
            session, user=current_user, query=body.message
        )
    else:
        if not await is_member(session, workspace_id=body.workspace_id, user_id=current_user.id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")
        target_ws = body.workspace_id

    # 自动定位无可访问空间时返回 []，须安全取值避免 [][0] IndexError（否则 500 且不记日志）。
    if isinstance(target_ws, list):
        conv_ws = target_ws[0] if target_ws else None
    else:
        conv_ws = target_ws
    # 自动定位可能命中多个空间，workspace_id 列只记首个；meta 保留完整归因
    ws_all = [str(w) for w in target_ws] if isinstance(target_ws, list) else [str(target_ws)]
    is_new_conv = body.conversation_id is None
    conv = await get_or_create_conversation(
        session,
        conversation_id=body.conversation_id,
        workspace_id=conv_ws if conv_ws else None,
        user_id=current_user.id,
        source="chat",
    )
    history = await recent_history(session, conversation_id=conv.id)
    await add_message(
        session, conversation_id=conv.id, role="user", content=body.message
    )

    # 空间为空 / 无归属空间也照常起任务：answer_question_streamed 内部产出 no_docs
    try:
        start_chat_generation(
            conversation_id=conv.id,
            user_id=current_user.id,
            is_new_conv=is_new_conv,
            question=body.message,
            history=history,
            workspace_id=target_ws,
            conv_ws=conv_ws,
            ws_all=ws_all,
        )
    except GenerationInProgress:
        raise HTTPException(status.HTTP_409_CONFLICT, "该会话正在生成中") from None

    sub = subscribe(conv.id, current_user.id)
    if sub is None:  # 理论上不会发生（刚 start）；兜底
        raise HTTPException(status.HTTP_404_NOT_FOUND, "生成任务不存在")

    async def _relay_with_meta():
        yield _sse("meta", _generation_meta(sub[0]))
        async for chunk in _relay(sub):
            yield chunk

    return StreamingResponse(
        _relay_with_meta(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            # 显式声明 identity，阻止 Next.js rewrites 代理对 SSE 做 gzip——
            # gzip 会攒够压缩块才输出，导致重连流事件被缓冲、直到生成结束才一次性
            # 解出（表现为「切走返回后 thinking 不再实时更新」）。
            "Content-Encoding": "identity",
        },
    )


@router.get("/chat/stream/{conversation_id}")
async def chat_reconnect(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """重连正在跑（或刚跑完、终态保留窗口内）的普通对话生成流。

    先补发已累积答案，再接实时增量。非 owner / 不存在 → 404。
    """
    await _require_module(session, current_user, "chat")
    sub = subscribe(conversation_id, current_user.id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "没有进行中的生成")

    async def _relay_with_meta():
        yield _sse("meta", _generation_meta(sub[0]))
        async for chunk in _relay(sub):
            yield chunk

    return StreamingResponse(
        _relay_with_meta(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            # 显式声明 identity，阻止 Next.js rewrites 代理对 SSE 做 gzip——
            # gzip 会攒够压缩块才输出，导致重连流事件被缓冲、直到生成结束才一次性
            # 解出（表现为「切走返回后 thinking 不再实时更新」）。
            "Content-Encoding": "identity",
        },
    )


@router.get("/chat/active")
async def chat_active(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """当前用户正在生成中的普通对话会话（侧边栏指示器 + 重连恢复计时）。"""
    await _require_module(session, current_user, "chat")
    return {
        "conversation_ids": [
            str(cid) for cid in list_active(current_user.id, source="chat")
        ],
        "generations": list_active_details(current_user.id, source="chat"),
    }


@router.post("/chat/stop/{conversation_id}")
async def chat_stop(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """停止按钮：取消该会话的生成；不在跑 / 非 owner → 404。"""
    await _require_module(session, current_user, "chat")
    if not request_cancel(conversation_id, current_user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "没有进行中的生成")
    return {"ok": True}


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


@router.post("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: uuid.UUID,
    body: ConversationExportRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """导出对话为 Word 或 Markdown 文件（直接下载）。"""
    from urllib.parse import quote

    from app.services.conversation_export_service import build_export

    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(conv.source))

    msgs = await list_messages(session, conversation_id=conv.id)
    title = conv.title or "对话记录"
    data, mime, filename = build_export(
        title,
        [MessagePublic.model_validate(m) for m in msgs],
        body.format,
        message_ids=body.message_ids,
    )
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/conversations/{conversation_id}/export-to-library",
    response_model=None,
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_conversation_to_library(
    conversation_id: uuid.UUID,
    body: ConversationExportToLibraryRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """导出对话并存入文档库（同普通上传，走 AI 分类流程）。"""
    from app.schemas.document import DocumentUploadAccepted
    from app.services.conversation_export_service import build_export
    from app.services.document_service import upload_document
    from app.services.folder_service import get_folder_in_workspace
    from app.services.workspace_service import get_ws_role
    from app.tasks.worker import enqueue_classification

    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(conv.source))

    # 目标空间写权限
    role = await get_ws_role(session, workspace_id=body.workspace_id, user_id=current_user.id)
    if role not in ("owner", "editor") and not current_user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权写入该空间")

    # 目录归属校验
    if body.folder_id is not None:
        folder = await get_folder_in_workspace(
            session, folder_id=body.folder_id, workspace_id=body.workspace_id
        )
        if folder is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "目录不存在")

    msgs = await list_messages(session, conversation_id=conv.id)
    title = conv.title or "对话记录"
    data, mime, filename = build_export(
        title,
        [MessagePublic.model_validate(m) for m in msgs],
        body.format,
        message_ids=body.message_ids,
    )

    doc, task = await upload_document(
        session,
        workspace_id=body.workspace_id,
        filename=filename,
        mime_type=mime,
        data=data,
        uploaded_by=current_user.id,
        folder_id=body.folder_id,
    )
    if task:
        enqueue_classification(task.id)
    return DocumentUploadAccepted(id=doc.id, status=doc.status, task_id=task.id if task else None)


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
    # 交互模式：开时向 system 注入 ask-user 协议，让模型可弹选项让用户澄清（瞬时，不落库）
    interactive: bool = False
    # 读取原始文件：开时把选中文档的原始文件拷进工作目录供 Claude 直接读全文
    # （不再注入截断的 content_text 摘录）；关时维持现状（瞬时，不落库）
    use_original_docs: bool = False
    # 附件：携带展示元数据（filename/size）；引擎侧只用 storage_key
    attachments: list[ChatPlusAttachment] | None = None
    # 引擎覆盖：空字符串或不传则跟随 Default Agent Engine；可选 "claude_cli" / "codex"
    engine_override: str = ""


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
    attachment_names = {a["storage_key"]: a["filename"] for a in attachments}
    for _k in attachment_keys:
        if not _k.startswith("chatplus/uploads/"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法附件引用")
    await add_message(
        session,
        conversation_id=conv.id,
        role="user",
        content=body.message,
        attachments=attachments,
    )

    # 生成跑在 detached 任务里（断连不中止）；本请求只订阅并转发其事件。
    try:
        start_generation(
            conversation_id=conv.id,
            user_id=current_user.id,
            is_new_conv=is_new_conv,
            question=body.message,
            history=history,
            workspace_id=body.workspace_id,
            doc_ids=body.doc_ids,
            all_docs=body.all_docs,
            skill_ids=body.skill_ids,
            attachment_keys=attachment_keys or None,
            attachment_names=attachment_names or None,
            interactive=body.interactive,
            use_original_docs=body.use_original_docs,
            engine_override=body.engine_override or "",
        )
    except GenerationInProgress:
        raise HTTPException(status.HTTP_409_CONFLICT, "该会话正在生成中") from None

    sub = subscribe(conv.id, current_user.id)
    if sub is None:  # 理论上不会发生（刚 start）；兜底
        raise HTTPException(status.HTTP_404_NOT_FOUND, "生成任务不存在")

    async def _relay_with_meta():
        # 首发 meta 事件带上 conversation_id：新会话在 done 之前断流也能重连。
        yield _sse("meta", _generation_meta(sub[0]))
        async for chunk in _relay(sub):
            yield chunk

    return StreamingResponse(
        _relay_with_meta(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            # 显式声明 identity，阻止 Next.js rewrites 代理对 SSE 做 gzip——
            # gzip 会攒够压缩块才输出，导致重连流事件被缓冲、直到生成结束才一次性
            # 解出（表现为「切走返回后 thinking 不再实时更新」）。
            "Content-Encoding": "identity",
        },
    )


@router.get("/chat/plus/stream/{conversation_id}")
async def chat_plus_reconnect(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """重连正在跑（或刚跑完、处于终态保留窗口）的生成流。

    先补发已累积答案，再接实时增量。非 owner / 不存在 → 404。
    """
    await _require_module(session, current_user, "chatplus")
    sub = subscribe(conversation_id, current_user.id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "没有进行中的生成")

    async def _relay_with_meta():
        yield _sse("meta", _generation_meta(sub[0]))
        async for chunk in _relay(sub):
            yield chunk

    return StreamingResponse(
        _relay_with_meta(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            # 显式声明 identity，阻止 Next.js rewrites 代理对 SSE 做 gzip——
            # gzip 会攒够压缩块才输出，导致重连流事件被缓冲、直到生成结束才一次性
            # 解出（表现为「切走返回后 thinking 不再实时更新」）。
            "Content-Encoding": "identity",
        },
    )


@router.get("/chat/plus/active")
async def chat_plus_active(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """当前用户正在生成中的会话 id 列表（侧边栏指示器轮询用）。"""
    await _require_module(session, current_user, "chatplus")
    generations = list_active_details(current_user.id)
    return {
        "conversation_ids": [str(cid) for cid in list_active(current_user.id)],
        "generations": generations,
    }


@router.post("/chat/plus/stop/{conversation_id}")
async def chat_plus_stop(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """停止按钮：取消该会话的生成；不在跑 / 非 owner → 404。"""
    await _require_module(session, current_user, "chatplus")
    if not request_cancel(conversation_id, current_user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "没有进行中的生成")
    return {"ok": True}


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
    _max_mb = await get_max_upload_mb(session)
    if len(data) > _max_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"文件超过 {_max_mb} MB 限制")
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

    from app.services.answer_service_plus import _is_noise
    from app.storage.base import get_storage
    storage = get_storage()
    workdir = await storage.resolve_dir(f"chatplus/conv_{conversation_id}")
    files: list[dict] = []
    for entry in sorted(workdir.rglob("*")):
        if not entry.is_file():
            continue
        rel = entry.relative_to(workdir).as_posix()
        # 排除注入目录（skills/、context/）与编程/依赖临时文件（node_modules 等），
        # 复用输出文件 diff 的同一套噪声判定，保持面板与成果文件列表一致。
        if _is_noise(rel):
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


# 可保存进文档库的成果文件后缀（常见可归档文档格式；与前端白名单保持一致）
_SAVEABLE_DOC_SUFFIXES = (
    ".md", ".markdown", ".txt", ".csv",
    ".pdf", ".png", ".jpg", ".jpeg",
    ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
)


@router.post(
    "/chat/plus/conversations/{conversation_id}/files/{file_path:path}/save-to-library",
    response_model=DocumentUploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def save_conversation_file_to_library(
    conversation_id: uuid.UUID,
    file_path: str,
    body: SaveFileToLibrary,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentUploadAccepted:
    """把聊天+ 会话工作目录里的成果文件保存进文档库（选空间+目录）。

    读取会话文件字节，复用普通上传的入库路径（storage.save→Document→归类任务）。
    需：会话属主 + chatplus 准入 + 目标空间写权限（owner/editor）。
    """
    import mimetypes
    from pathlib import PurePosixPath

    from app.services.document_service import upload_document
    from app.services.folder_service import get_folder_in_workspace
    from app.services.workspace_service import get_ws_role
    from app.storage.base import get_storage
    from app.storage.local import StorageError
    from app.tasks.worker import enqueue_classification

    # 会话归属校验（不泄漏存在性）+ 聊天+ 准入
    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    await _require_module(session, current_user, _module_for_source(conv.source))

    # 目标空间写权限（全局 admin 或 owner/editor）
    role = await get_ws_role(
        session, workspace_id=body.workspace_id, user_id=current_user.id
    )
    if role not in ("owner", "editor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要空间管理员或编辑权限")

    # 防穿越：规范化后不得为绝对路径 / 含 .. / 空 / 目录（保留子目录 relpath）
    rel = PurePosixPath(file_path)
    if rel.is_absolute() or ".." in rel.parts or not file_path or file_path.endswith("/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法文件路径")

    # 格式白名单：仅常见可归档文档格式可保存
    if not rel.name.lower().endswith(_SAVEABLE_DOC_SUFFIXES):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该文件格式不支持保存到文档库")

    # 目录归属校验（若指定）
    if body.folder_id is not None:
        folder = await get_folder_in_workspace(
            session, folder_id=body.folder_id, workspace_id=body.workspace_id
        )
        if folder is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "目录不存在")

    # 读取会话文件字节（storage 层再次校验落在根目录内）
    storage = get_storage()
    key = f"chatplus/conv_{conversation_id}/{file_path}"
    try:
        data = await storage.read_bytes(key)
    except (FileNotFoundError, StorageError, IsADirectoryError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在") from exc

    mime_type = mimetypes.guess_type(rel.name)[0] or "application/octet-stream"
    # 复用普通上传入库路径：拷贝字节到新文档 storage_key，触发异步归类
    doc, task = await upload_document(
        session,
        workspace_id=body.workspace_id,
        filename=rel.name,
        mime_type=mime_type,
        data=data,
        uploaded_by=current_user.id,
        folder_id=body.folder_id,
    )
    enqueue_classification(task.id)
    logger.info(
        "audit chatplus_save_to_library user=%s conversation=%s ws=%s doc=%s file=%s",
        current_user.id, conversation_id, body.workspace_id, doc.id, rel.name,
    )
    return DocumentUploadAccepted(id=doc.id, status=doc.status, task_id=task.id)


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
