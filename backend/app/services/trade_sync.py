from datetime import datetime, timezone

from app.db import get_supabase
from app.services.ibkr import IBKRClient


async def sync_trades_from_ibkr(
    client: IBKRClient,
    user_id: str,
    broker_connection_id: str,
    days: int = 7,
) -> dict:
    raw_trades = await client.get_trades(days=days)
    db = get_supabase()

    new_count = 0
    skipped = 0

    for raw in raw_trades:
        exec_id = raw.get("execution_id") or raw.get("order_ref")
        if not exec_id:
            continue

        existing = (
            db.table("trade_executions")
            .select("id")
            .eq("execution_id", exec_id)
            .eq("user_id", user_id)
            .execute()
        )
        if existing.data:
            skipped += 1
            continue

        symbol = raw.get("symbol", raw.get("contract", {}).get("symbol", "UNKNOWN"))
        side_raw = raw.get("side", "").upper()
        side = "buy" if side_raw in ("BOT", "BUY", "B") else "sell"
        price = float(raw.get("price", 0))
        quantity = abs(float(raw.get("size", raw.get("shares", 0))))
        fees = abs(float(raw.get("commission", 0)))
        executed_at = raw.get("trade_time", datetime.now(timezone.utc).isoformat())

        trade = find_or_create_trade(
            db, user_id, broker_connection_id, symbol, side, price, quantity, executed_at
        )

        db.table("trade_executions").insert({
            "trade_id": trade["id"],
            "user_id": user_id,
            "execution_id": exec_id,
            "side": side,
            "price": price,
            "quantity": quantity,
            "fees": fees,
            "executed_at": executed_at,
            "raw_data": raw,
        }).execute()

        update_trade_from_executions(db, trade["id"], user_id)
        new_count += 1

    return {"synced": len(raw_trades), "new_executions": new_count, "skipped": skipped}


def find_or_create_trade(
    db, user_id: str, broker_connection_id: str,
    symbol: str, side: str, price: float, quantity: float, executed_at: str,
) -> dict:
    trade_side = "long" if side == "buy" else "short"

    open_trades = (
        db.table("trades")
        .select("*")
        .eq("user_id", user_id)
        .eq("symbol", symbol)
        .eq("side", trade_side)
        .eq("status", "open")
        .execute()
    )

    if open_trades.data:
        return open_trades.data[0]

    result = (
        db.table("trades")
        .insert({
            "user_id": user_id,
            "broker_connection_id": broker_connection_id,
            "symbol": symbol,
            "side": trade_side,
            "status": "open",
            "entry_price": price,
            "quantity": quantity,
            "entry_time": executed_at,
        })
        .execute()
    )
    return result.data[0]


def update_trade_from_executions(db, trade_id: str, user_id: str):
    executions = (
        db.table("trade_executions")
        .select("*")
        .eq("trade_id", trade_id)
        .eq("user_id", user_id)
        .order("executed_at")
        .execute()
    )

    if not executions.data:
        return

    buys = [e for e in executions.data if e["side"] == "buy"]
    sells = [e for e in executions.data if e["side"] == "sell"]

    buy_qty = sum(float(e["quantity"]) for e in buys)
    sell_qty = sum(float(e["quantity"]) for e in sells)
    total_fees = sum(float(e["fees"]) for e in executions.data)

    avg_buy = (
        sum(float(e["price"]) * float(e["quantity"]) for e in buys) / buy_qty
        if buy_qty > 0 else 0
    )
    avg_sell = (
        sum(float(e["price"]) * float(e["quantity"]) for e in sells) / sell_qty
        if sell_qty > 0 else 0
    )

    update = {
        "entry_price": avg_buy if buy_qty > 0 else avg_sell,
        "quantity": max(buy_qty, sell_qty),
        "fees": total_fees,
    }

    if buy_qty > 0 and sell_qty > 0 and abs(buy_qty - sell_qty) < 0.001:
        closed_qty = min(buy_qty, sell_qty)
        pnl = (avg_sell - avg_buy) * closed_qty - total_fees
        pnl_pct = ((avg_sell - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0

        update["status"] = "closed"
        update["exit_price"] = avg_sell
        update["exit_time"] = sells[-1]["executed_at"]
        update["pnl"] = round(pnl, 6)
        update["pnl_percent"] = round(pnl_pct, 4)

    db.table("trades").update(update).eq("id", trade_id).execute()
