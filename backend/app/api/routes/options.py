from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db import get_supabase
from app.services.options_analytics import compute_options_analytics

router = APIRouter()


@router.get("/analytics")
async def options_analytics(user: dict = Depends(get_current_user)):
    db = get_supabase()
    return await compute_options_analytics(db, user["sub"])
