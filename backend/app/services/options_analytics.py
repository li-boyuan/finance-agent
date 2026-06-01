"""Options analytics: delta-adjusted exposure, theta, expiration calendar, a
risk-shock scenario, margin usage, and an aggressiveness scorecard.

Builds on compute_portfolio_summary (single source of truth for enrichment).
Greeks (delta/gamma/theta/vega) come from IBKR model values stored on the holding
at sync time; margin comes from the IBKR account summary stored on the accounts
row. Both degrade gracefully if migrations 006/007 aren't applied or the IBKR
sync hasn't run — the calendar, moneyness, and assignment flags still work from
data we always have.
"""

from datetime import date as date_cls

from app.services.market_data import get_quotes
from app.services.options import CONTRACT_MULTIPLIER
from app.services.portfolio import compute_portfolio_summary

NEAR_EXPIRY_DTE = 7
ASSIGNMENT_RISK_DTE = 21

# Risk shock: underlyings -10%, IV +10 points (a typical risk-off move).
SCENARIO_MOVE_PCT = 0.10
SCENARIO_IV_POINTS = 10

RATINGS = ["conservative", "moderate", "aggressive", "high"]


def _rate(value: float | None, t1: float, t2: float, t3: float) -> str | None:
    """Bucket a value into a 4-level rating. None passes through."""
    if value is None:
        return None
    if value < t1:
        return "conservative"
    if value < t2:
        return "moderate"
    if value < t3:
        return "aggressive"
    return "high"


def _worst(ratings: list[str | None]) -> str | None:
    idx = [RATINGS.index(r) for r in ratings if r in RATINGS]
    return RATINGS[max(idx)] if idx else None


def _empty(today: str) -> dict:
    return {
        "as_of": today,
        "has_greeks": False,
        "totals": {
            "option_value": 0, "leg_count": 0, "near_expiry": 0, "assignment_risk": 0,
            "net_delta_dollars": 0, "theta_day": 0, "net_vega": 0, "scenario_pl": 0,
        },
        "underlyings": [],
        "expirations": [],
        "flags": [],
        "margin": None,
        "scenario": {"move_pct": -SCENARIO_MOVE_PCT, "iv_points": SCENARIO_IV_POINTS,
                     "pl": 0, "pl_pct_nlv": None, "partial": False},
        "indicators": [],
        "overall_rating": None,
    }


async def compute_options_analytics(db, user_id: str) -> dict:
    today = date_cls.today()
    summary = await compute_portfolio_summary(db, user_id)
    holdings = summary.get("holdings", [])
    options = [h for h in holdings if h.get("is_option") and h.get("option_meta")]
    if not options:
        return _empty(today.isoformat())

    # Greeks live on holdings.greeks (migration 006); margin lives on
    # accounts.balances (migration 007). Both fetched here (not in
    # compute_portfolio_summary) and wrapped so core paths never depend on the
    # new columns and this degrades gracefully if a migration isn't applied.
    greeks_by_id: dict = {}
    option_ids = [h["id"] for h in options]
    try:
        gres = db.table("holdings").select("id, greeks").in_("id", option_ids).execute()
        greeks_by_id = {row["id"]: (row.get("greeks") or {}) for row in (gres.data or [])}
    except Exception:
        greeks_by_id = {}

    balances: dict | None = None
    try:
        ares = db.table("accounts").select("balances").eq("user_id", user_id).execute()
        for row in (ares.data or []):
            if row.get("balances"):
                balances = row["balances"]
                break
    except Exception:
        balances = None

    underlyings = sorted({h["option_meta"]["underlying"] for h in options})
    quotes = await get_quotes(underlyings)
    spot_of = {u: (quotes.get(u) or {}).get("price") for u in underlyings}

    # Shares held outright per ticker contribute delta 1.0 each.
    stock_shares: dict[str, float] = {}
    for h in holdings:
        if h.get("is_market") and not h.get("is_option"):
            stock_shares[h["symbol"]] = stock_shares.get(h["symbol"], 0.0) + h["quantity"]

    legs: list[dict] = []
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

        # IBKR greeks are long-contract, per-share; multiplying by signed qty
        # gives the position's exposure (short call -> negative delta; short
        # option -> positive theta). mult = qty * 100 (shares per contract).
        g = greeks_by_id.get(h["id"]) or {}
        delta, gamma, theta_ps, vega = g.get("delta"), g.get("gamma"), g.get("theta"), g.get("vega")
        mult = qty * CONTRACT_MULTIPLIER
        share_delta = (delta * mult) if delta is not None else None
        share_gamma = (gamma * mult) if gamma is not None else None
        theta_day = (theta_ps * mult) if theta_ps is not None else None
        pos_vega = (vega * mult) if vega is not None else None  # $ per +1 vol pt

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
            "intrinsic_value": round(intrinsic_ps * mult, 2) if intrinsic_ps is not None else None,
            "extrinsic_value": round(extrinsic_ps * mult, 2) if extrinsic_ps is not None else None,
            "value": h["value"],
            "delta": round(delta, 4) if delta is not None else None,
            "share_delta": round(share_delta, 1) if share_delta is not None else None,
            "share_gamma": share_gamma,
            "pos_vega": pos_vega,
            "theta_day": round(theta_day, 2) if theta_day is not None else None,
            "assignment_risk": bool(is_short and itm and dte is not None and dte <= ASSIGNMENT_RISK_DTE),
            "near_expiry": bool(dte is not None and dte <= NEAR_EXPIRY_DTE),
            "total_return_pct": h["total_return_pct"],
        })

    # Per-underlying aggregation. Net delta needs every leg's delta to be
    # meaningful, so we only report it once at least one leg has a delta and mark
    # it partial if some are still missing.
    agg: dict[str, dict] = {
        u: {"option_value": 0.0, "leg_count": 0, "delta_sum": 0.0, "legs_with_delta": 0,
            "theta_sum": 0.0, "legs_with_theta": 0, "gamma_sum": 0.0, "vega_sum": 0.0}
        for u in underlyings
    }
    for leg in legs:
        a = agg[leg["underlying"]]
        a["option_value"] += leg["value"]
        a["leg_count"] += 1
        if leg["share_delta"] is not None:
            a["delta_sum"] += leg["share_delta"]
            a["legs_with_delta"] += 1
        if leg["theta_day"] is not None:
            a["theta_sum"] += leg["theta_day"]
            a["legs_with_theta"] += 1
        if leg["share_gamma"] is not None:
            a["gamma_sum"] += leg["share_gamma"]
        if leg["pos_vega"] is not None:
            a["vega_sum"] += leg["pos_vega"]

    underlying_rows = []
    for u, a in agg.items():
        spot = spot_of.get(u)
        stk = stock_shares.get(u, 0.0)
        any_delta = a["legs_with_delta"] > 0
        net_share_delta = (a["delta_sum"] + stk) if any_delta else None
        delta_dollars = (net_share_delta * spot) if (net_share_delta is not None and spot is not None) else None

        # Shock P&L: -10% price (delta + gamma convexity) and +10 IV pts (vega).
        scenario_pl = None
        if delta_dollars is not None and spot is not None:
            d_s = -SCENARIO_MOVE_PCT * spot
            scenario_pl = (
                net_share_delta * d_s                 # directional
                + 0.5 * a["gamma_sum"] * d_s * d_s    # convexity
                + a["vega_sum"] * SCENARIO_IV_POINTS  # vol spike
            )

        underlying_rows.append({
            "underlying": u,
            "spot": round(spot, 2) if spot is not None else None,
            "stock_shares": stk,
            "option_value": round(a["option_value"], 2),
            "leg_count": a["leg_count"],
            "net_share_delta": round(net_share_delta, 1) if net_share_delta is not None else None,
            "delta_dollars": round(delta_dollars, 2) if delta_dollars is not None else None,
            "theta_day": round(a["theta_sum"], 2) if a["legs_with_theta"] else None,
            "net_vega": round(a["vega_sum"], 2),
            "scenario_pl": round(scenario_pl, 2) if scenario_pl is not None else None,
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

    # Portfolio rollups.
    net_delta_dollars = sum(r["delta_dollars"] for r in underlying_rows if r["delta_dollars"] is not None)
    net_vega = sum(leg["pos_vega"] for leg in legs if leg["pos_vega"] is not None)
    theta_day = sum(leg["theta_day"] for leg in legs if leg["theta_day"] is not None)
    scenario_pl = sum(r["scenario_pl"] for r in underlying_rows if r["scenario_pl"] is not None)
    greeks_complete = all(leg["delta"] is not None for leg in legs)

    # Margin + aggressiveness scorecard (account-relative; needs IBKR balances).
    nlv = (balances or {}).get("net_liquidation")
    maint = (balances or {}).get("maint_margin")
    gross = (balances or {}).get("gross_position_value")
    top_delta = max((abs(r["delta_dollars"]) for r in underlying_rows if r["delta_dollars"] is not None), default=None)

    margin_util = (maint / nlv) if (maint is not None and nlv) else None
    leverage = (gross / nlv) if (gross is not None and nlv) else None
    concentration = (top_delta / nlv) if (top_delta is not None and nlv) else None
    shock_pct = (abs(scenario_pl) / nlv) if (nlv and scenario_pl) else None

    indicators = [
        {"key": "margin_util", "label": "Margin utilization",
         "value": round(margin_util, 4) if margin_util is not None else None,
         "display": f"{margin_util * 100:.0f}%" if margin_util is not None else "—",
         "rating": _rate(margin_util, 0.25, 0.50, 0.75)},
        {"key": "leverage", "label": "Leverage (gross / NLV)",
         "value": round(leverage, 2) if leverage is not None else None,
         "display": f"{leverage:.1f}×" if leverage is not None else "—",
         "rating": _rate(leverage, 1.5, 3.0, 5.0)},
        {"key": "concentration", "label": "Top-name Δ$ / NLV",
         "value": round(concentration, 4) if concentration is not None else None,
         "display": f"{concentration * 100:.0f}%" if concentration is not None else "—",
         "rating": _rate(concentration, 0.25, 0.50, 1.0)},
        {"key": "shock_loss", "label": "−10% shock loss / NLV",
         "value": round(shock_pct, 4) if shock_pct is not None else None,
         "display": f"{shock_pct * 100:.0f}%" if shock_pct is not None else "—",
         "rating": _rate(shock_pct, 0.10, 0.25, 0.50)},
    ]
    overall_rating = _worst([i["rating"] for i in indicators])

    margin = None
    if balances and nlv is not None:
        margin = {
            "net_liquidation": nlv,
            "excess_liquidity": balances.get("excess_liquidity"),
            "buying_power": balances.get("buying_power"),
            "maint_margin": maint,
            "gross_position_value": gross,
            "margin_util": round(margin_util, 4) if margin_util is not None else None,
            "leverage": round(leverage, 2) if leverage is not None else None,
            "as_of": balances.get("as_of"),
        }

    return {
        "as_of": today.isoformat(),
        "has_greeks": any(leg["delta"] is not None for leg in legs),
        "totals": {
            "option_value": round(sum(leg["value"] for leg in legs), 2),
            "leg_count": len(legs),
            "near_expiry": sum(1 for leg in legs if leg["near_expiry"]),
            "assignment_risk": sum(1 for leg in legs if leg["assignment_risk"]),
            "net_delta_dollars": round(net_delta_dollars, 2),
            "theta_day": round(theta_day, 2),
            "net_vega": round(net_vega, 2),
            "scenario_pl": round(scenario_pl, 2),
        },
        "underlyings": underlying_rows,
        "expirations": expirations,
        "flags": flags,
        "margin": margin,
        "scenario": {
            "move_pct": -SCENARIO_MOVE_PCT,
            "iv_points": SCENARIO_IV_POINTS,
            "pl": round(scenario_pl, 2),
            "pl_pct_nlv": round(shock_pct, 4) if shock_pct is not None else None,
            "partial": not greeks_complete,
        },
        "indicators": indicators,
        "overall_rating": overall_rating,
    }
