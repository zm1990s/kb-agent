"""提示词历史版本 ORM 模型（append-only）。"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PromptHistory(Base):
    __tablename__ = "prompt_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
