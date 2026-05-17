from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db import get_supabase

router = APIRouter()


@router.get("/")
async def list_accounts(
    include_hidden: bool = False,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()
    query = (
        db.table("accounts")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_active", True)
    )
    if not include_hidden:
        query = query.eq("is_hidden", False)
    result = query.order("type").execute()
    return {"accounts": result.data}


@router.get("/{account_id}")
async def get_account(
    account_id: str,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()
    result = (
        db.table("accounts")
        .select("*")
        .eq("user_id", user_id)
        .eq("id", account_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Account not found")
    return result.data[0]
