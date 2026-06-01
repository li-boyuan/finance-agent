import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db import get_supabase
from app.services.net_worth import get_net_worth_history, snapshot_net_worth
from app.services.portfolio import compute_portfolio_summary

router = APIRouter()
logger = logging.getLogger("portfolio.route")


@router.get("/summary")
async def portfolio_summary(user: dict = Depends(get_current_user)):
    db = get_supabase()
    summary = await compute_portfolio_summary(db, user["sub"])
    # Opportunistically record today's net-worth snapshot so the trend chart
    # fills in just by visiting the dashboard. Idempotent per day, best-effort.
    try:
        await snapshot_net_worth(db, user["sub"], summary)
    except Exception:
        logger.warning("net-worth snapshot failed", exc_info=True)
    return summary


@router.post("/snapshot")
async def create_snapshot(user: dict = Depends(get_current_user)):
    """Record today's net-worth snapshot. Idempotent per day; for a daily cron."""
    return await snapshot_net_worth(get_supabase(), user["sub"])


@router.get("/history")
async def net_worth_history(days: int = 365, user: dict = Depends(get_current_user)):
    return await get_net_worth_history(get_supabase(), user["sub"], days)
