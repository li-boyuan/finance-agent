import json
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db import get_supabase
from app.services.chat import stream_chat

logger = logging.getLogger("chat.route")

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
    user_id = user["sub"]
    db = get_supabase()

    conv_id = body.conversation_id
    if conv_id:
        existing = (
            db.table("chat_conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("id", conv_id)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        title = body.content[:60].strip() or "New conversation"
        created = (
            db.table("chat_conversations")
            .insert({"user_id": user_id, "title": title})
            .execute()
        )
        conv_id = created.data[0]["id"]

    prior = (
        db.table("chat_messages")
        .select("role, content")
        .eq("conversation_id", conv_id)
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )

    profile = (
        db.table("profiles")
        .select("financial_context")
        .eq("id", user_id)
        .execute()
    )
    financial_context = (
        profile.data[0].get("financial_context") if profile.data else None
    )

    db.table("chat_messages").insert({
        "conversation_id": conv_id,
        "user_id": user_id,
        "role": "user",
        "content": body.content,
    }).execute()

    async def event_stream() -> AsyncIterator[bytes]:
        yield f"data: {json.dumps({'type': 'conversation', 'conversation_id': conv_id})}\n\n".encode()

        full_text = ""
        usage_info: dict = {}
        try:
            async for evt in stream_chat(user_id, prior.data, body.content, financial_context):
                if evt["type"] == "text":
                    yield f"data: {json.dumps(evt)}\n\n".encode()
                elif evt["type"] in ("tool_use_start", "tool_use_done"):
                    yield f"data: {json.dumps(evt)}\n\n".encode()
                elif evt["type"] == "done":
                    full_text = evt["content"]
                    usage_info = evt
                    yield f"data: {json.dumps({'type': 'done'})}\n\n".encode()
        except Exception as e:
            logger.exception("Chat stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n".encode()
            return

        tool_calls = usage_info.get("tool_calls") or None
        db.table("chat_messages").insert({
            "conversation_id": conv_id,
            "user_id": user_id,
            "role": "assistant",
            "content": full_text,
            "tool_calls": tool_calls,
            "model": usage_info.get("model"),
            "input_tokens": usage_info.get("input_tokens"),
            "output_tokens": usage_info.get("output_tokens"),
            "cached_tokens": usage_info.get("cached_input_tokens"),
        }).execute()

        db.table("chat_conversations").update({
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", conv_id).execute()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
