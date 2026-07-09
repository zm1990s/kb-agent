"""对话检索路由。仅限所属空间；串起检索→生成→落库。"""

import json
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
    MessagePublic,
    SourceRef,
)
from app.services.answer_service import (
    AnswerResult,
    Stage,
    answer_question,
    answer_question_streamed,
)
from app.services.chat_service import (
    add_message,
    create_conversation,
    get_conversation_for_user,
    get_or_create_conversation,
    list_conversations,
    list_messages,
    recent_history,
)
from app.services.usage_service import record_event
from app.services.workspace_service import is_member

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    # 仅限所属空间（越权校验 SECURITY #4）
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

    async def _log_chat() -> None:
        async with SessionLocal() as s:
            await record_event(
                s,
                action="chat",
                user_id=current_user.id,
                workspace_id=body.workspace_id,
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
                yield sse("stage", {"stage": item.stage, "message": item.message})
            elif isinstance(item, AnswerResult):
                final = item
        if final is None:
            final = AnswerResult(answer="（无响应）", sources=[])
        # 落库助手消息
        await add_message(
            session,
            conversation_id=conv.id,
            role="assistant",
            content=final.answer,
            sources=final.sources,
        )
        yield sse(
            "done",
            {
                "answer": final.answer,
                "sources": final.sources,
                "conversation_id": str(conv.id),
            },
        )

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
