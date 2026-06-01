"""Sync IBKR positions into the holdings table.

Strategy: full replace. Each sync deletes all holdings on the user's IBKR
`accounts` row and re-inserts from the live snapshot. Simple, idempotent,
and cleanly handles closed positions. Manual holdings (other accounts) are
never touched.

IBKR's position payload uses different field names across gateway versions;
we read defensively, try multiple field aliases, and surface skipped rows
in the sync response so unknown shapes can be diagnosed without grepping
logs.
"""

import asyncio
import logging
import re
from datetime import date, datetime

from app.services.ibkr import IBKRClient
from app.services.options import build_occ_symbol

logger = logging.getLogger("ibkr.positions")

IBKR_ACCOUNT_NAME = "IBKR Portfolio"
MAX_SKIPPED_SAMPLES = 5

# IBKR Client Portal market-data field codes for option model greeks. If a future
# gateway version changes these, the diagnostic log in _fetch_greeks shows the
# raw snapshot so the mapping can be corrected.
GREEK_FIELDS = {
    "7308": "delta",
    "7309": "gamma",
    "7310": "theta",
    "7311": "vega",
    "7283": "iv",  # implied vol — may arrive as a "%"-suffixed string
}


async def _fetch_greeks(client: IBKRClient, conids: list) -> dict[str, dict]:
    """Best-effort conid -> {delta, gamma, ...}. Returns {} on any failure;
    greeks are optional and positions still sync without them."""
    conids = [c for c in conids if c]
    if not conids:
        return {}
    await client.init_brokerage_session()
    fields = list(GREEK_FIELDS.keys())
    try:
        # First call primes the subscription; the second returns computed values.
        await client.get_market_data_snapshot(conids, fields)
        await asyncio.sleep(0.6)
        snap = await client.get_market_data_snapshot(conids, fields)
    except Exception:
        logger.warning("Greeks snapshot failed; syncing without greeks", exc_info=True)
        return {}

    if snap:
        logger.info("Greeks snapshot sample (verify field codes): %s", snap[0])

    result: dict[str, dict] = {}
    for row in snap:
        conid = str(row.get("conid") or "")
        if not conid:
            continue
        g: dict[str, float] = {}
        for code, name in GREEK_FIELDS.items():
            v = row.get(code)
            if v in (None, ""):
                continue
            try:
                g[name] = float(str(v).rstrip("%"))
            except (TypeError, ValueError):
                continue
        if g:
            result[conid] = g
    return result


def get_or_create_ibkr_account(db, user_id: str, connection_id: str, ibkr_account_id: str | None) -> str:
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


def _first(raw: dict, *keys: str) -> str:
    """Return the first non-empty value from raw[k] for k in keys, as a string."""
    for k in keys:
        v = raw.get(k)
        if v not in (None, "", 0):
            return str(v)
    return ""


def _map_security_type(raw: dict) -> str | None:
    """Map IBKR's assetClass/secType to our vocabulary. Returns None to skip."""
    asset_class = _first(raw, "assetClass", "secType", "secTypeFull", "instrumentClass").upper()
    if asset_class in ("STK", "STOCK"):
        return "stock"  # IBKR doesn't split STK vs ETF; quote fetcher treats them the same
    if asset_class in ("OPT", "OPTION", "FOP"):
        return "option"
    if asset_class in ("BOND", "FIXED", "BAG"):
        return "bond"
    if asset_class in ("FUND", "MUTUAL"):
        return "mutual_fund"
    if asset_class == "CASH":
        return "cash"
    return None  # FUT, WAR, CFD, CRYPTO, etc.


def _normalize_expiry(raw_value: str) -> str | None:
    """Coerce IBKR's many expiry formats into ISO 'YYYY-MM-DD'. Returns None
    if unparseable."""
    if not raw_value:
        return None
    s = str(raw_value).strip()
    # YYYYMMDD (most common)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    # YYYY-MM-DD
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    # YYYYMMDDHHMMSS (sometimes appears as a timestamp prefix)
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    # "MMM DD 'YY" or "MMM DD YYYY" — try a few formats
    for fmt in ("%b %d '%y", "%b %d %Y", "%d %b %Y", "%d-%b-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# IBKR's contractDesc embeds a fully-qualified OCC symbol in brackets:
#   "MSTR   JUN2027 500 C [MSTR  270617C00500000 100]"
# The bracketed form is space-padded but otherwise standard OCC plus a
# trailing contract multiplier. We parse this first since it carries the
# exact expiry date (vs. the human-readable prefix which only has month/year).
IBKR_BRACKET_OCC_RE = re.compile(
    r"\[\s*([A-Z0-9]{1,6})\s+(\d{6})([CP])(\d{8})\s+\d+\s*\]"
)

# Compact OCC form, e.g. "AAPL240126C00200000"
OCC_LIKE_RE = re.compile(r"^([A-Z0-9]{1,6})\s*(\d{6})([CP])(\d{8})$")

# Human-readable fallback, e.g. "AAPL JAN 26 '24 200 Call"
CONTRACT_DESC_OPT_RE = re.compile(
    r"^([A-Z]{1,6})\s+([A-Za-z]{3})\s+(\d{1,2})\s+'?(\d{2,4})\s+([\d.]+)\s+(C|P|Call|Put)",
    re.IGNORECASE,
)


def _try_parse_option_from_desc(desc: str) -> tuple[str | None, str | None, float | None, str | None]:
    """Returns (underlying, expiry_iso, strike, C/P) or all-None if unparseable."""
    if not desc:
        return None, None, None, None
    desc = desc.strip()

    # Preferred: IBKR's bracketed OCC — most precise, always has the day.
    m = IBKR_BRACKET_OCC_RE.search(desc)
    if m:
        u, yymmdd, cp, strike_raw = m.groups()
        return (
            u.upper(),
            f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}",
            int(strike_raw) / 1000.0,
            cp.upper(),
        )

    # Standalone compact OCC.
    m = OCC_LIKE_RE.match(desc.replace(" ", ""))
    if m:
        u, yymmdd, cp, strike_raw = m.groups()
        return (
            u.upper(),
            f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}",
            int(strike_raw) / 1000.0,
            cp.upper(),
        )

    # Human-readable fallback.
    m = CONTRACT_DESC_OPT_RE.match(desc)
    if m:
        u, mon, day, yr, strike, cp = m.groups()
        try:
            year = int(yr)
            if year < 100:
                year += 2000
            d = datetime.strptime(f"{mon} {int(day)} {year}", "%b %d %Y").date()
            return u.upper(), d.isoformat(), float(strike), cp[0].upper()
        except ValueError:
            pass
    return None, None, None, None


def _build_symbol_and_name(raw: dict, sec_type: str) -> tuple[str | None, str | None]:
    """Derive (symbol, display_name). For options we build an OCC symbol so the
    rest of the pipeline (quote fetcher, formatter, chat tools) needs zero
    IBKR-specific code."""
    if sec_type == "option":
        underlying = _first(raw, "undSym", "underSymbol", "underlyingSymbol", "ticker", "symbol").upper().strip()
        expiry = _normalize_expiry(_first(raw, "expirationDate", "lastTradingDay", "maturityDate", "expiry", "expiryDate"))
        strike_raw = raw.get("strike") or raw.get("strikePrice") or 0
        try:
            strike = float(strike_raw or 0)
        except (TypeError, ValueError):
            strike = 0
        put_or_call = _first(raw, "putOrCall", "right", "callPut", "optionType").upper()[:1]

        # Fallback: parse from contractDesc if structured fields are missing.
        if not (underlying and expiry and strike and put_or_call in ("C", "P")):
            u2, e2, s2, pc2 = _try_parse_option_from_desc(_first(raw, "contractDesc", "description", "displayName"))
            underlying = underlying or (u2 or "")
            expiry = expiry or e2
            strike = strike or (s2 or 0)
            put_or_call = put_or_call if put_or_call in ("C", "P") else (pc2 or "")

        if not (underlying and expiry and strike and put_or_call in ("C", "P")):
            return None, _first(raw, "contractDesc", "description") or None

        try:
            symbol = build_occ_symbol(underlying, expiry, strike, put_or_call)
        except ValueError as e:
            logger.warning("Built OCC symbol failed: %s — raw=%s", e, raw)
            return None, _first(raw, "contractDesc", "description") or None
        return symbol, None  # name gets formatted downstream from the OCC symbol

    ticker = _first(raw, "ticker", "symbol").upper().strip()
    if not ticker:
        ticker = (raw.get("contractDesc") or "").split()[0].upper() if raw.get("contractDesc") else ""
    if not ticker:
        return None, None
    return ticker, raw.get("name") or raw.get("contractDesc")


def map_position_to_holding(
    raw: dict,
    user_id: str,
    account_id: str,
    greeks_by_conid: dict[str, dict] | None = None,
) -> dict | None:
    """Map one IBKR position row → a holdings insert dict. Returns None to skip."""
    sec_type = _map_security_type(raw)
    if not sec_type:
        return None

    qty = float(raw.get("position") or 0)
    if qty == 0:
        return None  # closed positions sometimes linger in the API response

    symbol, display_name = _build_symbol_and_name(raw, sec_type)
    if not symbol:
        return None

    # IBKR's `avgCost` is per-share for stocks but per-contract for options
    # (already multiplied by 100). Normalize back to per-unit.
    avg_cost = float(raw.get("avgCost") or raw.get("avgPrice") or 0)
    if sec_type == "option" and avg_cost:
        avg_cost = avg_cost / 100.0

    row = {
        "user_id": user_id,
        "account_id": account_id,
        "symbol": symbol,
        "name": display_name,
        "security_type": sec_type,
        # Preserve sign: shorts are negative. Portfolio math (value, cost,
        # return) propagates the sign naturally — a short option's value is
        # the liability, cost is the credit received.
        "quantity": qty,
        "cost_basis": round(avg_cost, 6),
        "currency": (raw.get("currency") or "USD").upper(),
        "as_of": date.today().isoformat(),
    }
    if sec_type == "option" and greeks_by_conid:
        g = greeks_by_conid.get(str(raw.get("conid")))
        if g:
            row["greeks"] = g
    return row


def _slim_for_diagnostics(raw: dict) -> dict:
    """Pick the fields most useful for diagnosing a skipped row."""
    keys = (
        "assetClass", "secType", "ticker", "symbol", "contractDesc", "description",
        "position", "avgCost", "currency",
        "undSym", "underSymbol", "strike", "strikePrice",
        "expirationDate", "lastTradingDay", "maturityDate",
        "putOrCall", "right", "callPut",
        "conid",
    )
    return {k: raw.get(k) for k in keys if k in raw}


async def sync_positions(
    db,
    client: IBKRClient,
    user_id: str,
    connection_id: str,
    ibkr_account_id: str,
) -> dict:
    """Replace the user's IBKR holdings with the current snapshot.

    Returns {synced, skipped, options_seen, skipped_samples, account_id}."""
    account_id = get_or_create_ibkr_account(db, user_id, connection_id, ibkr_account_id)

    # IBKR's positions endpoint is lazy — first call may return partial data.
    try:
        await client.tickle()
    except Exception:
        logger.debug("Tickle failed; continuing", exc_info=True)

    raw_positions = await client.get_positions(ibkr_account_id)
    logger.info("IBKR returned %d total positions", len(raw_positions))

    # Pull model greeks for option positions (best-effort) so the options
    # analytics page can show delta-adjusted exposure.
    option_conids = [
        raw.get("conid")
        for raw in raw_positions
        if _map_security_type(raw) == "option" and raw.get("conid")
    ]
    greeks_by_conid = await _fetch_greeks(client, option_conids)
    if option_conids:
        logger.info(
            "Greeks: requested %d option conids, got %d", len(option_conids), len(greeks_by_conid)
        )

    rows: list[dict] = []
    skipped = 0
    options_seen = 0
    greeks_seen = 0
    skipped_samples: list[dict] = []

    for raw in raw_positions:
        sec_type = _map_security_type(raw)
        if sec_type == "option":
            options_seen += 1
            logger.info("Option row: %s", _slim_for_diagnostics(raw))

        mapped = map_position_to_holding(raw, user_id, account_id, greeks_by_conid)
        if mapped:
            if mapped.get("greeks"):
                greeks_seen += 1
            rows.append(mapped)
        else:
            skipped += 1
            if len(skipped_samples) < MAX_SKIPPED_SAMPLES:
                skipped_samples.append(_slim_for_diagnostics(raw))

    db.table("holdings").delete().eq("account_id", account_id).execute()
    if rows:
        db.table("holdings").insert(rows).execute()

    logger.info(
        "Sync complete: synced=%d, skipped=%d, options_seen=%d",
        len(rows), skipped, options_seen,
    )

    return {
        "synced": len(rows),
        "skipped": skipped,
        "options_seen": options_seen,
        "greeks_seen": greeks_seen,
        "skipped_samples": skipped_samples,
        "account_id": account_id,
    }
