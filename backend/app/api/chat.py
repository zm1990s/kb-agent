"""对话检索路由。仅限所属空间；串起检索→生成→落库。"""

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
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


async def _require_chat(session: AsyncSession, user: User) -> None:
    """要求用户有 chat 模块权限（≥read）；admin 绕过。否则 403。

    注意：这是「能否使用聊天功能」的准入门闸，与「能否访问某空间数据」
    （is_member）正交——两者都要过。
    """
    if user.role == "admin":
        return
    from app.services.rbac_service import effective_permissions

    perms = await effective_permissions(session, user=user)
    if perms.get("chat", "none") == "none":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无聊天功能权限")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    # 聊天功能准入（chat 模块权限）+ 空间成员资格（越权校验 SECURITY #4）
    await _require_chat(session, current_user)
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
    await _require_chat(session, current_user)
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
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationSummary]:
    await _require_chat(session, current_user)
    if not await is_member(
        session, workspace_id=workspace_id, user_id=current_user.id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")
    convs = await list_conversations(
        session, workspace_id=workspace_id, user_id=current_user.id
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
    await _require_chat(session, current_user)
    if not await is_member(
        session, workspace_id=body.workspace_id, user_id=current_user.id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")
    conv = await create_conversation(
        session, workspace_id=body.workspace_id, user_id=current_user.id
    )
    return ConversationSummary.model_validate(conv)


@router.get("/conversations/{conversation_id}", response_model=ConversationHistory)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationHistory:
    await _require_chat(session, current_user)
    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=current_user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
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
    await _require_chat(session, current_user)
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
    await _require_chat(session, current_user)
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
