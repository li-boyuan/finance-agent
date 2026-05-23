from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db import get_supabase

router = APIRouter()


class ProfileUpdate(BaseModel):
    financial_context: str | None = None
    display_name: str | None = None


@router.get("/")
async def get_profile(user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    db = get_supabase()
    result = (
        db.table("profiles")
        .select("id, email, display_name, financial_context, created_at, updated_at")
        .eq("id", user_id)
        .execute()
    )
    if not result.data:
        email = user.get("email", "")
        created = (
            db.table("profiles")
            .insert({"id": user_id, "email": email})
            .execute()
        )
        return created.data[0]
    return result.data[0]


@router.patch("/")
async def update_profile(
    body: ProfileUpdate,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        return {"updated": False}
    result = (
        db.table("profiles")
        .update(update)
        .eq("id", user_id)
        .execute()
    )
    return {"updated": True, "profile": result.data[0] if result.data else None}
