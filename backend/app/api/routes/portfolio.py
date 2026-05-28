from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db import get_supabase
from app.services.portfolio import compute_portfolio_summary

router = APIRouter()


@router.get("/summary")
async def portfolio_summary(user: dict = Depends(get_current_user)):
    return await compute_portfolio_summary(get_supabase(), user["sub"])
