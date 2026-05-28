"""Sync IBKR positions into the holdings table.

Strategy: full replace. Each sync deletes all holdings on the user's IBKR
`accounts` row and re-inserts from the live snapshot. Simple, idempotent,
and cleanly handles closed positions. Manual holdings (other accounts) are
never touched.

IBKR's position payload uses different field names across gateway versions;
we read defensively and skip rows we can't interpret rather than blowing up
the whole sync.
"""

import logging
from datetime import date

from app.services.ibkr import IBKRClient
from app.services.options import build_occ_symbol

logger = logging.getLogger("ibkr.positions")

IBKR_ACCOUNT_NAME = "IBKR Portfolio"


def get_or_create_ibkr_account(db, user_id: str, connection_id: str, ibkr_account_id: str | None) -> str:
    """Find or create the user's IBKR `accounts` row. Holdings hang off this."""
    existing = (
        db.table("accounts")
        .select("id")
        .eq("user_id", user_id)
        .eq("connection_id", connection_id)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    created = (
        db.table("accounts")
        .insert({
            "user_id": user_id,
            "connection_id": connection_id,
            "provider_account_id": ibkr_account_id,
            "name": IBKR_ACCOUNT_NAME,
            "type": "investment",
            "subtype": "brokerage",
            "currency": "USD",
        })
        .execute()
    )
    return created.data[0]["id"]


def _map_security_type(raw: dict) -> str | None:
    """IBKR uses `assetClass` (STK/OPT/FUT/...) and sometimes `secType`.
    Map to our holdings.security_type vocabulary. Returns None to skip."""
    asset_class = (raw.get("assetClass") or raw.get("secType") or "").upper()
    if asset_class == "STK":
        # IBKR doesn't split STK vs ETF — leave as 'stock' and let the user
        # edit if it matters. Quote fetcher treats them the same.
        return "stock"
    if asset_class == "OPT":
        return "option"
    if asset_class in ("BOND", "FIXED"):
        return "bond"
    if asset_class in ("FUND", "MUTUAL"):
        return "mutual_fund"
    if asset_class == "CASH":
        return "cash"
    return None  # FUT, WAR, CFD, etc. — skip until we model them


def _build_symbol_and_name(raw: dict, sec_type: str) -> tuple[str | None, str | None]:
    """Derive (symbol, display_name). For options, produce an OCC symbol so the
    rest of the system (parse_occ_symbol, format_option_name, quote fetcher)
    works without any IBKR-specific branching."""
    if sec_type == "option":
        underlying = (raw.get("undSym") or raw.get("ticker") or "").upper().strip()
        # IBKR returns expiry as YYYYMMDD string or `expirationDate` ISO.
        expiry_raw = str(raw.get("expirationDate") or raw.get("lastTradingDay") or "")
        if len(expiry_raw) == 8 and expiry_raw.isdigit():
            expiry = f"{expiry_raw[:4]}-{expiry_raw[4:6]}-{expiry_raw[6:8]}"
        elif len(expiry_raw) == 10 and expiry_raw[4] == "-":
            expiry = expiry_raw
        else:
            return None, raw.get("contractDesc")
        strike = float(raw.get("strike") or 0)
        put_or_call = (raw.get("putOrCall") or "").upper()[:1]  # 'C' or 'P'
        if not underlying or not strike or put_or_call not in ("C", "P"):
            return None, raw.get("contractDesc")
        try:
            symbol = build_occ_symbol(underlying, expiry, strike, put_or_call)
        except ValueError:
            return None, raw.get("contractDesc")
        return symbol, None  # name gets formatted by portfolio service

    ticker = (raw.get("ticker") or raw.get("contractDesc") or "").strip().upper()
    if not ticker:
        return None, None
    return ticker, raw.get("name") or raw.get("contractDesc")


def map_position_to_holding(raw: dict, user_id: str, account_id: str) -> dict | None:
    """Map one IBKR position row → a holdings insert dict. Returns None to skip."""
    sec_type = _map_security_type(raw)
    if not sec_type:
        return None

    qty = float(raw.get("position") or 0)
    if qty == 0:
        return None  # closed positions sometimes linger in the API response

    symbol, display_name = _build_symbol_and_name(raw, sec_type)
    if not symbol:
        logger.info("Skipping position with no derivable symbol: %s", raw.get("contractDesc"))
        return None

    # IBKR's `avgCost` is per-share for stocks but per-contract for options
    # (already multiplied by 100). Normalize back to per-unit so our
    # cost_basis stays in the same units as the manual-entry flow.
    avg_cost = float(raw.get("avgCost") or 0)
    if sec_type == "option" and avg_cost:
        avg_cost = avg_cost / 100.0

    return {
        "user_id": user_id,
        "account_id": account_id,
        "symbol": symbol,
        "name": display_name,
        "security_type": sec_type,
        "quantity": abs(qty),  # shorts represented as negative; we just track magnitude for v1
        "cost_basis": round(avg_cost, 6),
        "currency": (raw.get("currency") or "USD").upper(),
        "as_of": date.today().isoformat(),
    }


async def sync_positions(
    db,
    client: IBKRClient,
    user_id: str,
    connection_id: str,
    ibkr_account_id: str,
) -> dict:
    """Replace the user's IBKR holdings with the current snapshot.

    Returns {synced, skipped, account_id}."""
    account_id = get_or_create_ibkr_account(db, user_id, connection_id, ibkr_account_id)

    # IBKR's positions endpoint is lazy — first call kicks off the snapshot
    # and may return partial data. Tickling first is a documented workaround.
    try:
        await client.tickle()
    except Exception:
        logger.debug("Tickle failed; continuing", exc_info=True)

    raw_positions = await client.get_positions(ibkr_account_id)
    rows: list[dict] = []
    skipped = 0
    for raw in raw_positions:
        mapped = map_position_to_holding(raw, user_id, account_id)
        if mapped:
            rows.append(mapped)
        else:
            skipped += 1

    # Full replace: delete then insert. Only touches this IBKR account's rows.
    db.table("holdings").delete().eq("account_id", account_id).execute()
    if rows:
        db.table("holdings").insert(rows).execute()

    return {
        "synced": len(rows),
        "skipped": skipped,
        "account_id": account_id,
    }
