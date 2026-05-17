from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db import get_supabase

router = APIRouter()


class ChatMessageRequest(BaseModel):
    conversation_id: str | None = None
    content: str


@router.get("/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    db = get_supabase()
    result = (
        db.table("chat_conversations")
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return {"conversations": result.data}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()
    result = (
        db.table("chat_messages")
        .select("*")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )
    return {"messages": result.data}


@router.post("/messages")
async def send_message(
    body: ChatMessageRequest,
    user: dict = Depends(get_current_user),
):
    # TODO Phase 3 — Anthropic SDK with tool use over the user's financial
    # data. Stream the response, persist user + assistant messages, update
    # conversation.updated_at.
    raise HTTPException(status_code=501, detail="Chat advisor not yet implemented")
