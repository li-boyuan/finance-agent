from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.routes.holdings import NON_MARKET_TYPES
from app.db import get_supabase
from app.services.market_data import get_quotes
from app.services.options import CONTRACT_MULTIPLIER, format_option_name, parse_occ_symbol

router = APIRouter()


@router.get("/summary")
async def portfolio_summary(user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    db = get_supabase()

    holdings = (
        db.table("holdings")
        .select("id, symbol, name, security_type, quantity, cost_basis, current_price, current_value, currency, as_of")
        .eq("user_id", user_id)
        .order("symbol")
        .execute()
    )
    rows = holdings.data or []
    if not rows:
        return {
            "total_value": 0,
            "total_cost": 0,
            "total_return": 0,
            "total_return_pct": 0,
            "today_change": 0,
            "today_change_pct": 0,
            "positions_count": 0,
            "holdings": [],
        }

    market_symbols = sorted({
        r["symbol"] for r in rows
        if (r.get("security_type") or "stock") not in NON_MARKET_TYPES
    })
    quotes = await get_quotes(market_symbols) if market_symbols else {}

    enriched: list[dict] = []
    total_value = 0.0
    total_cost = 0.0
    prev_total_value = 0.0

    for r in rows:
        symbol = r["symbol"]
        sec_type = r.get("security_type") or "stock"
        qty = float(r["quantity"])
        cost_basis = float(r["cost_basis"] or 0)
        is_market = sec_type not in NON_MARKET_TYPES
        is_option = sec_type == "option"
        # Options trade in 100-share contracts; everything else is 1:1.
        multiplier = CONTRACT_MULTIPLIER if is_option else 1
        cost_total = cost_basis * qty * multiplier

        option_meta = parse_occ_symbol(symbol) if is_option else None

        if is_market:
            q = quotes.get(symbol)
            if q:
                price = float(q["price"])
                prev_close = float(q["previous_close"])
                # For options Yahoo's longName is empty — use parsed name.
                display_name = (
                    format_option_name(symbol) if is_option else q["name"]
                )
                quote_available = True
            else:
                # Fall back to stored current_price, then to cost_basis.
                price = float(r.get("current_price") or cost_basis)
                prev_close = price
                display_name = (
                    format_option_name(symbol) if is_option
                    else (r.get("name") or symbol)
                )
                quote_available = False
        else:
            # User-valued asset: use stored current_price (per unit).
            price = float(r.get("current_price") or cost_basis)
            prev_close = price
            display_name = r.get("name") or symbol
            quote_available = False

        value = price * qty * multiplier
        prev_value = prev_close * qty * multiplier
        gain = value - cost_total
        gain_pct = (gain / cost_total * 100) if cost_total else 0.0
        day_change = value - prev_value
        day_change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0

        enriched.append({
            "id": r["id"],
            "symbol": symbol,
            "name": display_name,
            "security_type": sec_type,
            "is_market": is_market,
            "is_option": is_option,
            "option_meta": option_meta,
            "quantity": qty,
            "cost_basis": cost_basis,
            "price": round(price, 4),
            "value": round(value, 2),
            "cost_total": round(cost_total, 2),
            "total_return": round(gain, 2),
            "total_return_pct": round(gain_pct, 2),
            "day_change": round(day_change, 2),
            "day_change_pct": round(day_change_pct, 2),
            "quote_available": quote_available,
        })
        total_value += value
        total_cost += cost_total
        prev_total_value += prev_value

    today_change = total_value - prev_total_value
    today_change_pct = (today_change / prev_total_value * 100) if prev_total_value else 0.0
    total_return = total_value - total_cost
    total_return_pct = (total_return / total_cost * 100) if total_cost else 0.0

    for h in enriched:
        h["allocation_pct"] = round((h["value"] / total_value * 100) if total_value else 0, 2)

    return {
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
        "today_change": round(today_change, 2),
        "today_change_pct": round(today_change_pct, 2),
        "positions_count": len(enriched),
        "holdings": enriched,
    }
