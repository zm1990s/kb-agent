"""Resource request/response schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    type: Literal["url", "html"]
    url: str | None = None

    @model_validator(mode="after")
    def url_required_for_url_type(self) -> "ResourceCreate":
        if self.type == "url" and not self.url:
            raise ValueError("url is required when type is 'url'")
        return self


class ResourceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    url: str | None = None


class ResourcePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    type: str
    url: str | None
    created_by: uuid.UUID | None = None
    created_by_email: str | None = None
    created_at: datetime
