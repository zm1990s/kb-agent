"""对话 service：会话管理 + 落库用户/助手消息。

隔离：会话归属 workspace + user；取会话时校验归属，跨空间/跨用户不可见。
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Workspace
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
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "空间不存在")
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


async def recent_history(
    session: AsyncSession, *, conversation_id: uuid.UUID, max_turns: int = 6
) -> list[tuple[str, str]]:
    """取会话最近 max_turns 条消息，按时间正序返回 (role, content)，供 Agent 上下文。"""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(max_turns)
    )
    result = await session.execute(stmt)
    msgs = list(result.scalars().all())
    msgs.reverse()
    return [(m.role, m.content) for m in msgs]


async def create_conversation(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "空间不存在")
    conv = Conversation(id=uuid.uuid4(), workspace_id=workspace_id, user_id=user_id)
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def list_conversations(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> list[Conversation]:
    """列出当前用户在某空间的会话（置顶优先，然后按创建时间倒序）。"""
    stmt = (
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.user_id == user_id,
        )
        .order_by(Conversation.pinned.desc(), Conversation.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """删除会话及其所有消息；校验归属，不匹配返回 False。"""
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        return False
    await session.delete(conv)
    await session.commit()
    return True


async def update_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str | None = None,
    pinned: bool | None = None,
) -> Conversation | None:
    """更新会话标题或置顶状态；校验归属，不匹配返回 None。"""
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        return None
    if title is not None:
        conv.title = title[:200]
    if pinned is not None:
        conv.pinned = pinned
    await session.commit()
    await session.refresh(conv)
    return conv


async def generate_conversation_title(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    first_message: str,
) -> None:
    """用 LLM 为会话生成简短标题（后台任务，失败静默）。"""
    from app.engine.base import get_chat_engine
    from app.services.settings_service import (
        TASK_HEADERS_TITLE_KEY,
        TITLE_PROMPT_KEY,
        get_prompt,
        get_task_headers,
    )

    try:
        headers = await get_task_headers(session, TASK_HEADERS_TITLE_KEY)
        engine = await get_chat_engine(session, extra_headers=headers)
        prompt_tpl = await get_prompt(session, TITLE_PROMPT_KEY)
        prompt = prompt_tpl.format(message=first_message[:500])
        result = await engine.complete(prompt)
        title = result.text.strip().strip('"').strip("'").strip("《》【】")[:100]
        if title:
            conv = await session.get(Conversation, conversation_id)
            if conv is not None and not conv.title:
                conv.title = title
                await session.commit()
    except Exception:
        pass  # 标题生成失败不影响对话
