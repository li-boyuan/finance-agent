from collections import defaultdict

from app.services.market_data import get_quotes
from app.services.options import (
    CONTRACT_MULTIPLIER,
    format_option_name,
    parse_occ_symbol,
)

# Asset types whose value comes from the user, not a market feed.
NON_MARKET_TYPES = {"real_estate", "vehicle", "other"}


def _empty_summary() -> dict:
    return {
        "total_value": 0,
        "total_cost": 0,
        "total_return": 0,
        "total_return_pct": 0,
        "today_change": 0,
        "today_change_pct": 0,
        "positions_count": 0,
        "by_tax_treatment": {},
        "holdings": [],
    }


def _tax_treatment(provider: str, subtype: str | None, name: str | None) -> str:
    """Map an account to a tax bucket. Plaid subtypes are imperfect (a 401k
    self-directed 'BrokerageLink' is labeled 'brokerage'; a DAF is 'brokerage'),
    so we also sniff the account name."""
    s = (subtype or "").lower()
    nm = (name or "").lower()
    if "giving" in nm or "charitable" in nm:
        return "charitable"  # donor-advised fund — gifted, excluded from net worth
    if s in ("roth", "hsa"):
        return "tax_free"
    if s == "529":
        return "education"
    if s in ("401k", "403b", "ira", "retirement") or "brokeragelink" in nm:
        return "tax_deferred"
    return "taxable"


async def compute_portfolio_summary(db, user_id: str) -> dict:
    """Fetch holdings, enrich with live quotes, return rollup + per-position rows."""
    holdings = (
        db.table("holdings")
        .select(
            "id, symbol, name, security_type, quantity, cost_basis, "
            "current_price, current_value, currency, as_of, account_id"
        )
        .eq("user_id", user_id)
        .order("symbol")
        .execute()
    )
    rows = holdings.data or []
    if not rows:
        return _empty_summary()

    # Tag each holding with its account source + tax treatment. The DAF
    # (charitable) is excluded from net worth per the owner's choice.
    accts = (
        db.table("accounts").select("id, name, subtype, connection_id").eq("user_id", user_id).execute().data or []
    )
    providers = {
        c["id"]: c.get("provider")
        for c in (db.table("account_connections").select("id, provider").eq("user_id", user_id).execute().data or [])
    }
    account_meta: dict[str, dict] = {}
    for a in accts:
        provider = providers.get(a.get("connection_id")) or "manual"
        account_meta[a["id"]] = {
            "account": a.get("name"),
            "provider": provider,
            "tax_treatment": _tax_treatment(provider, a.get("subtype"), a.get("name")),
        }

    rows = [
        r for r in rows
        if account_meta.get(r.get("account_id"), {}).get("tax_treatment") != "charitable"
    ]
    if not rows:
        return _empty_summary()

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
                # Yahoo's longName is empty for options — use parsed name.
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
        day_change = value - prev_value
        # Percentages reflect *position* direction, not security direction.
        # For shorts (qty < 0): a stock rising hurts the position, so the
        # percentage goes negative. Use abs() in the denominators to keep
        # the sign coming from the numerator only.
        gain_pct = (gain / abs(cost_total) * 100) if cost_total else 0.0
        day_change_pct = (day_change / abs(prev_value) * 100) if prev_value else 0.0
        is_short = qty < 0
        meta = account_meta.get(r.get("account_id"), {})

        enriched.append({
            "id": r["id"],
            "symbol": symbol,
            "name": display_name,
            "security_type": sec_type,
            "is_market": is_market,
            "is_option": is_option,
            "is_short": is_short,
            "option_meta": option_meta,
            "account": meta.get("account"),
            "provider": meta.get("provider", "manual"),
            "tax_treatment": meta.get("tax_treatment", "taxable"),
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

    by_tax: dict[str, float] = {}
    for h in enriched:
        h["allocation_pct"] = round((h["value"] / total_value * 100) if total_value else 0, 2)
        bucket = h.get("tax_treatment") or "taxable"
        by_tax[bucket] = by_tax.get(bucket, 0.0) + h["value"]

    return {
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
        "today_change": round(today_change, 2),
        "today_change_pct": round(today_change_pct, 2),
        "positions_count": len(enriched),
        "by_tax_treatment": {k: round(v, 2) for k, v in by_tax.items()},
        "holdings": enriched,
    }


def summarize_for_llm(summary: dict, top_n: int = 10) -> dict:
    """Compact, LLM-friendly view of the portfolio: rollup numbers, breakdown
    by security_type, and top-N holdings by value. Drops UUIDs and internal flags."""
    holdings = summary.get("holdings", [])
    total_value = summary.get("total_value", 0) or 0

    by_type: dict[str, dict] = defaultdict(lambda: {"value": 0.0, "count": 0})
    for h in holdings:
        bucket = by_type[h["security_type"]]
        bucket["value"] += h["value"]
        bucket["count"] += 1

    allocation_by_type = sorted(
        (
            {
                "security_type": st,
                "value": round(b["value"], 2),
                "positions_count": b["count"],
                "allocation_pct": round((b["value"] / total_value * 100) if total_value else 0, 2),
            }
            for st, b in by_type.items()
        ),
        key=lambda x: x["value"],
        reverse=True,
    )

    # Sort by exposure (abs value) so big short positions don't drop off the list.
    top = sorted(holdings, key=lambda h: abs(h["value"]), reverse=True)[:top_n]
    top_holdings = [
        {
            "symbol": h["symbol"],
            "name": h["name"],
            "security_type": h["security_type"],
            "is_short": h.get("is_short", False),
            "quantity": h["quantity"],
            "value": h["value"],
            "allocation_pct": h["allocation_pct"],
            "total_return": h["total_return"],
            "total_return_pct": h["total_return_pct"],
            "day_change_pct": h["day_change_pct"],
        }
        for h in top
    ]

    return {
        "total_value": summary["total_value"],
        "total_cost": summary["total_cost"],
        "total_return": summary["total_return"],
        "total_return_pct": summary["total_return_pct"],
        "today_change": summary["today_change"],
        "today_change_pct": summary["today_change_pct"],
        "positions_count": summary["positions_count"],
        "allocation_by_type": allocation_by_type,
        "top_holdings": top_holdings,
    }


def holdings_for_llm(summary: dict) -> dict:
    """Full per-position list, formatted for an LLM consumer."""
    return {
        "positions_count": summary["positions_count"],
        "total_value": summary["total_value"],
        "holdings": [
            {
                "symbol": h["symbol"],
                "name": h["name"],
                "security_type": h["security_type"],
                "quantity": h["quantity"],
                "cost_basis": h["cost_basis"],
                "price": h["price"],
                "value": h["value"],
                "cost_total": h["cost_total"],
                "total_return": h["total_return"],
                "total_return_pct": h["total_return_pct"],
                "day_change": h["day_change"],
                "day_change_pct": h["day_change_pct"],
                "allocation_pct": h["allocation_pct"],
                "live_quote": h["quote_available"],
            }
            for h in summary.get("holdings", [])
        ],
    }
