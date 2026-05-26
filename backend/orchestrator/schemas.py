import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    tokens_used: int | None
    created_at: datetime


class SessionHistoryResponse(BaseModel):
    session_id: uuid.UUID
    agent_slug: str | None
    messages: list[ChatMessageResponse]
    created_at: datetime
