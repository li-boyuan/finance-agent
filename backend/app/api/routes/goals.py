from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db import get_supabase

router = APIRouter()


@router.get("/")
async def list_goals(user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    db = get_supabase()
    result = (
        db.table("goals")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )
    return {"goals": result.data}
