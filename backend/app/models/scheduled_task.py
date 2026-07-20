"""定时任务 ORM 模型。"""

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_hour: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    daily_minute: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    initial_message: Mapped[str] = mapped_column(Text, nullable=False)
    skill_ids: Mapped[list] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=False, server_default="{}")
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, server_default="zh")
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default="NOW()")
