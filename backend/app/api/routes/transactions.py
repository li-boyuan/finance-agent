from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db import get_supabase

router = APIRouter()


@router.get("/")
async def list_transactions(
    account_id: str | None = None,
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()
    query = (
        db.table("transactions")
        .select("*")
        .eq("user_id", user_id)
    )
    if account_id:
        query = query.eq("account_id", account_id)
    if category:
        query = query.eq("category_primary", category)
    result = (
        query.order("transaction_date", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return {"transactions": result.data, "limit": limit, "offset": offset}
