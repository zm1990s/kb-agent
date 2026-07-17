"""M3-U1：conversations / messages 表映射与约束。"""

import uuid

import pytest
from sqlalchemy import text

from app.models.auth import User, Workspace
from app.models.chat import Conversation, Message

pytestmark = pytest.mark.asyncio


async def _ws_user(session):
    ws = Workspace(id=uuid.uuid4(), name="ws")
    user = User(
        id=uuid.uuid4(), email=f"{uuid.uuid4().hex[:8]}@company.com",
        password_hash="x", role="user",
    )
    session.add_all([ws, user])
    await session.commit()
    return ws, user


async def test_conversation_message_roundtrip(db_session):
    ws, user = await _ws_user(db_session)
    conv = Conversation(id=uuid.uuid4(), workspace_id=ws.id, user_id=user.id)
    db_session.add(conv)
    await db_session.commit()

    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        role="assistant",
        content="答案",
        sources=[{"doc_id": str(uuid.uuid4()), "title": "a"}],
    )
    db_session.add(msg)
    await db_session.commit()
    assert msg.sources[0]["title"] == "a"


async def test_message_role_check(db_session):
    ws, user = await _ws_user(db_session)
    conv = Conversation(id=uuid.uuid4(), workspace_id=ws.id, user_id=user.id)
    db_session.add(conv)
    await db_session.commit()
    with pytest.raises(Exception):  # noqa: B017,PT011  # CHECK 违约
        await db_session.execute(
            text(
                "INSERT INTO messages (id, conversation_id, role, content) "
                "VALUES (uuid_generate_v4(), :c, 'system', 'x')"
            ),
            {"c": str(conv.id)},
        )
        await db_session.commit()
