from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ChatRole = Literal["system", "user", "assistant", "tool"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: ChatRole
    content: str
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    character_id: str | None = None
    user_name: str | None = None
    developer_mode: bool = False
    language: str | None = None
    settings_snapshot: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    message: ChatMessage