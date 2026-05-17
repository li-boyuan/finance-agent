from datetime import datetime
from pydantic import BaseModel


class ChatConversation(BaseModel):
    id: str
    user_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    id: str
    conversation_id: str
    user_id: str
    role: str
    content: str | None
    tool_calls: list[dict] | None
    tool_call_id: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    created_at: datetime
