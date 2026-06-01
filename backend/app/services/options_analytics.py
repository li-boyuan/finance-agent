"""Options analytics: delta-adjusted exposure, expiration calendar, risk flags.

Builds on compute_portfolio_summary (single source of truth for enrichment).
Delta comes from IBKR model greeks stored on the holding at sync time; the
calendar, moneyness, intrinsic/extrinsic split, and assignment-risk flags are
derived from data we already have (strike/expiry/type/qty + underlying spot).
"""

from datetime import date as date_cls

from app.services.market_data import get_quotes
from app.services.options import CONTRACT_MULTIPLIER
from app.services.portfolio import compute_portfolio_summary

NEAR_EXPIRY_DTE = 7
ASSIGNMENT_RISK_DTE = 21


def _empty(today: str) -> dict:
    return {
        "as_of": today,
        "has_greeks": False,
        "totals": {"option_value": 0, "leg_count": 0, "near_expiry": 0, "assignment_risk": 0},
        "underlyings": [],
        "expirations": [],
        "flags": [],
    }


async def compute_options_analytics(db, user_id: str) -> dict:
    today = date_cls.today()
    summary = await compute_portfolio_summary(db, user_id)
    holdings = summary.get("holdings", [])
    options = [h for h in holdings if h.get("is_option") and h.get("option_meta")]
    if not options:
        return _empty(today.isoformat())

    # Greeks live on the holdings.greeks jsonb column (migration 006), populated
    # by the IBKR sync. Fetched here rather than in compute_portfolio_summary so
    # the core portfolio path doesn't depend on the column — and so this degrades
    # gracefully (no delta) if the migration hasn't been applied yet.
    greeks_by_id: dict = {}
    option_ids = [h["id"] for h in options]
    try:
        gres = db.table("holdings").select("id, greeks").in_("id", option_ids).execute()
        greeks_by_id = {row["id"]: (row.get("greeks") or {}) for row in (gres.data or [])}
    except Exception:
        greeks_by_id = {}

    underlyings = sorted({h["option_meta"]["underlying"] for h in options})
    quotes = await get_quotes(underlyings)
    spot_of = {u: (quotes.get(u) or {}).get("price") for u in underlyings}

    # Shares held outright per ticker contribute delta 1.0 each.
    stock_shares: dict[str, float] = {}
    for h in holdings:
        if h.get("is_market") and not h.get("is_option"):
            stock_shares[h["symbol"]] = stock_shares.get(h["symbol"], 0.0) + h["quantity"]

    legs: list[dict] = []
    has_greeks = False
    for h in options:
        m = h["option_meta"]
        u = m["underlying"]
        strike = float(m["strike"])
        otype = m["option_type"]
        expiry = m["expiry"]
        qty = h["quantity"]
        spot = spot_of.get(u)
        try:
            dte = (date_cls.fromisoformat(expiry) - today).days
        except ValueError:
            dte = None

        intrinsic_ps = None
        itm = False
        if spot is not None:
            intrinsic_ps = max(0.0, spot - strike) if otype == "C" else max(0.0, strike - spot)
            itm = intrinsic_ps > 0
        extrinsic_ps = (h["price"] - intrinsic_ps) if intrinsic_ps is not None else None

        # IBKR delta is the long-contract delta; multiplying by signed qty gives
        # the position's directional exposure (short call -> negative, etc.).
        delta = (greeks_by_id.get(h["id"]) or {}).get("delta")
        if delta is not None:
            has_greeks = True
        share_delta = (delta * qty * CONTRACT_MULTIPLIER) if delta is not None else None

        is_short = qty < 0
        legs.append({
            "symbol": h["symbol"],
            "name": h["name"],
            "underlying": u,
            "option_type": otype,
            "strike": strike,
            "expiry": expiry,
            "dte": dte,
            "quantity": qty,
            "is_short": is_short,
            "spot": round(spot, 2) if spot is not None else None,
            "moneyness": ("ITM" if itm else "OTM") if spot is not None else None,
            "intrinsic_value": round(intrinsic_ps * qty * CONTRACT_MULTIPLIER, 2) if intrinsic_ps is not None else None,
            "extrinsic_value": round(extrinsic_ps * qty * CONTRACT_MULTIPLIER, 2) if extrinsic_ps is not None else None,
            "value": h["value"],
            "delta": delta,
            "share_delta": round(share_delta, 1) if share_delta is not None else None,
            "assignment_risk": bool(is_short and itm and dte is not None and dte <= ASSIGNMENT_RISK_DTE),
            "near_expiry": bool(dte is not None and dte <= NEAR_EXPIRY_DTE),
            "total_return_pct": h["total_return_pct"],
        })

    # Per-underlying aggregation. Net delta needs every leg's delta to be
    # meaningful, so we only report it once at least one leg has greeks and mark
    # it partial if some are missing.
    agg: dict[str, dict] = {
        u: {"option_value": 0.0, "leg_count": 0, "delta_sum": 0.0, "legs_with_delta": 0}
        for u in underlyings
    }
    for leg in legs:
        a = agg[leg["underlying"]]
        a["option_value"] += leg["value"]
        a["leg_count"] += 1
        if leg["share_delta"] is not None:
            a["delta_sum"] += leg["share_delta"]
            a["legs_with_delta"] += 1

    underlying_rows = []
    for u, a in agg.items():
        spot = spot_of.get(u)
        stk = stock_shares.get(u, 0.0)
        any_delta = a["legs_with_delta"] > 0
        net_share_delta = (a["delta_sum"] + stk) if any_delta else None
        delta_dollars = (net_share_delta * spot) if (net_share_delta is not None and spot is not None) else None
        underlying_rows.append({
            "underlying": u,
            "spot": round(spot, 2) if spot is not None else None,
            "stock_shares": stk,
            "option_value": round(a["option_value"], 2),
            "leg_count": a["leg_count"],
            "net_share_delta": round(net_share_delta, 1) if net_share_delta is not None else None,
            "delta_dollars": round(delta_dollars, 2) if delta_dollars is not None else None,
            "delta_partial": any_delta and a["legs_with_delta"] < a["leg_count"],
        })
    underlying_rows.sort(
        key=lambda r: abs(r["delta_dollars"] or 0) or abs(r["option_value"]),
        reverse=True,
    )

    # Expiration calendar.
    exp_map: dict[str, dict] = {}
    for leg in legs:
        em = exp_map.setdefault(
            leg["expiry"],
            {"expiry": leg["expiry"], "dte": leg["dte"], "leg_count": 0, "net_value": 0.0, "underlyings": set()},
        )
        em["leg_count"] += 1
        em["net_value"] += leg["value"]
        em["underlyings"].add(leg["underlying"])
    expirations = sorted(
        (
            {
                "expiry": em["expiry"],
                "dte": em["dte"],
                "leg_count": em["leg_count"],
                "net_value": round(em["net_value"], 2),
                "underlyings": sorted(em["underlyings"]),
            }
            for em in exp_map.values()
        ),
        key=lambda e: e["expiry"],
    )

    flags = sorted(
        [leg for leg in legs if leg["assignment_risk"] or leg["near_expiry"]],
        key=lambda leg: (leg["dte"] if leg["dte"] is not None else 9999),
    )

    return {
        "as_of": today.isoformat(),
        "has_greeks": has_greeks,
        "totals": {
            "option_value": round(sum(leg["value"] for leg in legs), 2),
            "leg_count": len(legs),
            "near_expiry": sum(1 for leg in legs if leg["near_expiry"]),
            "assignment_risk": sum(1 for leg in legs if leg["assignment_risk"]),
        },
        "underlyings": underlying_rows,
        "expirations": expirations,
        "flags": flags,
    }
