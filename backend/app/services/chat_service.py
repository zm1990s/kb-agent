"""对话 service：会话管理 + 落库用户/助手消息。

隔离：会话归属 workspace + user；取会话时校验归属，跨空间/跨用户不可见。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Conversation, Message


async def get_or_create_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID | None,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Conversation:
    """取现有会话（须同 workspace + user），否则新建。"""
    if conversation_id is not None:
        conv = await session.get(Conversation, conversation_id)
        if (
            conv is not None
            and conv.workspace_id == workspace_id
            and conv.user_id == user_id
        ):
            return conv
    conv = Conversation(
        id=uuid.uuid4(), workspace_id=workspace_id, user_id=user_id
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def add_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    sources: list | None = None,
) -> Message:
    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=sources or [],
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def get_conversation_for_user(
    session: AsyncSession, *, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation | None:
    """取会话并校验归属当前用户；否则 None（不泄漏存在性）。"""
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        return None
    return conv


async def list_messages(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
