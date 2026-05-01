from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_client_ip
from app.core.audit import log_access
from app.db import get_supabase

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


class TradeUpdate(BaseModel):
    notes: str | None = None
    tags: list[str] | None = None
    setup_type: str | None = None


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

    db = get_supabase()
    query = db.table("trades").select("*", count="exact").eq("user_id", user_id)

    if status:
        query = query.eq("status", status)
    if symbol:
        query = query.ilike("symbol", f"%{symbol}%")

    result = query.order("entry_time", desc=True).range(offset, offset + limit - 1).execute()

    return {"trades": result.data, "total": result.count}


@router.get("/stats")
async def trade_stats(
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()

    all_trades = (
        db.table("trades")
        .select("status, pnl, entry_time")
        .eq("user_id", user_id)
        .execute()
    )

    trades = all_trades.data or []
    closed = [t for t in trades if t["status"] == "closed"]
    winners = [t for t in closed if t.get("pnl") and float(t["pnl"]) > 0]

    total_pnl = sum(float(t["pnl"]) for t in closed if t.get("pnl"))
    win_rate = (len(winners) / len(closed) * 100) if closed else 0

    today = datetime.now().strftime("%Y-%m-%d")
    today_trades = [t for t in closed if t.get("entry_time", "").startswith(today)]
    today_pnl = sum(float(t["pnl"]) for t in today_trades if t.get("pnl"))

    return {
        "total_trades": len(trades),
        "closed_trades": len(closed),
        "open_trades": len(trades) - len(closed),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "today_pnl": round(today_pnl, 2),
    }


@router.get("/{trade_id}")
async def get_trade(
    trade_id: str,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()

    result = (
        db.table("trades")
        .select("*")
        .eq("id", trade_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Trade not found")

    executions = (
        db.table("trade_executions")
        .select("*")
        .eq("trade_id", trade_id)
        .eq("user_id", user_id)
        .order("executed_at")
        .execute()
    )

    trade = result.data[0]
    trade["executions"] = executions.data
    return trade


@router.post("/")
async def create_trade(
    trade: TradeCreate,
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "create_trade", "trades", ip_address=ip)

    db = get_supabase()
    result = (
        db.table("trades")
        .insert({
            "user_id": user_id,
            "symbol": trade.symbol.upper(),
            "side": trade.side,
            "status": "open",
            "entry_price": trade.entry_price,
            "quantity": trade.quantity,
            "entry_time": trade.entry_time.isoformat(),
            "notes": trade.notes,
            "tags": trade.tags,
            "setup_type": trade.setup_type,
        })
        .execute()
    )

    return result.data[0]


@router.put("/{trade_id}")
async def update_trade(
    trade_id: str,
    body: TradeUpdate,
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "update_trade", "trades", trade_id, ip_address=ip)

    db = get_supabase()

    update = {}
    if body.notes is not None:
        update["notes"] = body.notes
    if body.tags is not None:
        update["tags"] = body.tags
    if body.setup_type is not None:
        update["setup_type"] = body.setup_type

    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = (
        db.table("trades")
        .update(update)
        .eq("id", trade_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Trade not found")

    return result.data[0]


@router.put("/{trade_id}/close")
async def close_trade(
    trade_id: str,
    body: TradeClose,
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "close_trade", "trades", trade_id, ip_address=ip)

    db = get_supabase()

    trade_result = (
        db.table("trades")
        .select("*")
        .eq("id", trade_id)
        .eq("user_id", user_id)
        .eq("status", "open")
        .execute()
    )

    if not trade_result.data:
        raise HTTPException(status_code=404, detail="Open trade not found")

    trade = trade_result.data[0]
    entry = float(trade["entry_price"])
    exit_p = body.exit_price
    qty = float(trade["quantity"])
    fees = float(trade.get("fees", 0))

    if trade["side"] == "long":
        pnl = (exit_p - entry) * qty - fees
    else:
        pnl = (entry - exit_p) * qty - fees

    pnl_pct = ((exit_p - entry) / entry * 100) if entry > 0 else 0
    if trade["side"] == "short":
        pnl_pct = -pnl_pct

    result = (
        db.table("trades")
        .update({
            "status": "closed",
            "exit_price": exit_p,
            "exit_time": body.exit_time.isoformat(),
            "pnl": round(pnl, 6),
            "pnl_percent": round(pnl_pct, 4),
        })
        .eq("id", trade_id)
        .execute()
    )

    return result.data[0]


@router.delete("/{trade_id}")
async def delete_trade(
    trade_id: str,
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "delete_trade", "trades", trade_id, ip_address=ip)

    db = get_supabase()
    db.table("trade_executions").delete().eq("trade_id", trade_id).eq("user_id", user_id).execute()
    db.table("trades").delete().eq("id", trade_id).eq("user_id", user_id).execute()

    return {"deleted": True}
