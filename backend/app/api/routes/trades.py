from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_client_ip
from app.core.audit import log_access

router = APIRouter()


class TradeCreate(BaseModel):
    symbol: str
    side: str
    entry_price: float
    quantity: float
    entry_time: datetime
    notes: str | None = None
    tags: list[str] = []
    setup_type: str | None = None


class TradeClose(BaseModel):
    exit_price: float
    exit_time: datetime


@router.get("/")
async def list_trades(
    status: str | None = Query(None),
    symbol: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "list_trades", "trades", ip_address=ip)
    # TODO: query Supabase
    return {"trades": [], "total": 0}


@router.post("/")
async def create_trade(
    trade: TradeCreate,
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "create_trade", "trades", ip_address=ip)
    # TODO: insert into Supabase
    return {"id": "placeholder", "symbol": trade.symbol}


@router.put("/{trade_id}/close")
async def close_trade(
    trade_id: str,
    body: TradeClose,
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "close_trade", "trades", trade_id, ip_address=ip)
    # TODO: update in Supabase, calculate P&L
    return {"id": trade_id, "status": "closed"}
