"""对话检索路由。仅限所属空间；串起检索→生成→落库。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationHistory,
    MessagePublic,
    SourceRef,
)
from app.services.answer_service import answer_question
from app.services.chat_service import (
    add_message,
    get_conversation_for_user,
    get_or_create_conversation,
    list_messages,
)
from app.services.workspace_service import is_member

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
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
    await add_message(
        session, conversation_id=conv.id, role="user", content=body.message
    )

    result = await answer_question(
        session, workspace_id=body.workspace_id, question=body.message
    )

    await add_message(
        session,
        conversation_id=conv.id,
        role="assistant",
        content=result.answer,
        sources=result.sources,
    )

    return ChatResponse(
        answer=result.answer,
        sources=[SourceRef(**s) for s in result.sources],
        conversation_id=conv.id,
    )


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
