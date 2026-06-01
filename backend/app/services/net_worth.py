"""Net-worth time series: daily snapshots + history.

A snapshot is the portfolio's net market value for a day (consistent with the
dashboard's "Total Value"): net_worth = sum of signed holding values, split into
assets (longs) and liabilities (shorts), with a per-security-type breakdown.

Idempotent per (user, date): the table has a unique index on
(user_id, snapshot_date), so we upsert — one row per day, updated to the latest
value, race-safe, no new migration.
"""

from collections import defaultdict
from datetime import date as date_cls, timedelta

from app.services.portfolio import compute_portfolio_summary


async def snapshot_net_worth(db, user_id: str, summary: dict | None = None) -> dict:
    """Record (insert or update) today's net-worth snapshot."""
    if summary is None:
        summary = await compute_portfolio_summary(db, user_id)
    holdings = summary.get("holdings", [])

    assets = round(sum(h["value"] for h in holdings if h["value"] > 0), 4)
    liabilities = round(-sum(h["value"] for h in holdings if h["value"] < 0), 4)
    net_worth = round(summary.get("total_value", 0) or 0, 4)

    by_type: dict[str, float] = defaultdict(float)
    for h in holdings:
        by_type[h["security_type"]] += h["value"]
    breakdown = {
        "by_type": {k: round(v, 2) for k, v in by_type.items()},
        "positions_count": summary.get("positions_count", 0),
    }

    today = date_cls.today().isoformat()
    row = {
        "user_id": user_id,
        "snapshot_date": today,
        "assets_total": assets,
        "liabilities_total": liabilities,
        "net_worth": net_worth,
        "breakdown": breakdown,
    }
    # Unique index on (user_id, snapshot_date) makes this idempotent + race-safe.
    db.table("net_worth_snapshots").upsert(row, on_conflict="user_id,snapshot_date").execute()

    return {
        "snapshot_date": today,
        "assets_total": assets,
        "liabilities_total": liabilities,
        "net_worth": net_worth,
    }


async def get_net_worth_history(db, user_id: str, days: int = 365) -> dict:
    """Net-worth series for the last `days`, ascending by date (deduped per day)."""
    cutoff = (date_cls.today() - timedelta(days=max(days, 1))).isoformat()
    res = (
        db.table("net_worth_snapshots")
        .select("snapshot_date, assets_total, liabilities_total, net_worth")
        .eq("user_id", user_id)
        .gte("snapshot_date", cutoff)
        .order("snapshot_date")
        .execute()
    )
    by_date: dict[str, dict] = {}
    for r in res.data or []:
        by_date[r["snapshot_date"]] = r  # last write for a date wins
    history = [
        {
            "date": d,
            "net_worth": float(by_date[d]["net_worth"]),
            "assets_total": float(by_date[d]["assets_total"]),
            "liabilities_total": float(by_date[d]["liabilities_total"]),
        }
        for d in sorted(by_date)
    ]
    return {"history": history}
