"""定时任务请求/响应 Schema。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScheduledTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    schedule_type: Literal["interval", "daily", "weekly", "monthly"]
    interval_minutes: int | None = Field(default=None, ge=5)
    daily_hour: int | None = Field(default=None, ge=0, le=23)
    daily_minute: int | None = Field(default=None, ge=0, le=59)
    week_day: int | None = Field(default=None, ge=0, le=6)
    month_day: int | None = Field(default=None, ge=1, le=31)
    system_prompt: str | None = None
    initial_message: str = Field(min_length=1)
    skill_ids: list[uuid.UUID] = Field(default_factory=list)
    workspace_id: uuid.UUID | None = None
    locale: str = "zh"


class ScheduledTaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    schedule_type: Literal["interval", "daily", "weekly", "monthly"] | None = None
    interval_minutes: int | None = Field(default=None, ge=5)
    daily_hour: int | None = Field(default=None, ge=0, le=23)
    daily_minute: int | None = Field(default=None, ge=0, le=59)
    week_day: int | None = Field(default=None, ge=0, le=6)
    month_day: int | None = Field(default=None, ge=1, le=31)
    system_prompt: str | None = None
    initial_message: str | None = Field(default=None, min_length=1)
    skill_ids: list[uuid.UUID] | None = None
    workspace_id: uuid.UUID | None = None
    locale: str | None = None


class ScheduledTaskPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    enabled: bool
    schedule_type: str
    interval_minutes: int | None
    daily_hour: int | None
    daily_minute: int | None
    week_day: int | None
    month_day: int | None
    system_prompt: str | None
    initial_message: str
    skill_ids: list[uuid.UUID]
    workspace_id: uuid.UUID | None
    locale: str
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
