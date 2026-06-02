"""Map a Plaid investments/holdings payload into our accounts + holdings.

Each Plaid account becomes an `accounts` row (typed: ira / roth / 401k / 529 /
brokerage), and each holding becomes a `holdings` row under it. Full-replace for
the connection's accounts, mirroring the IBKR strategy.
"""

import logging
from datetime import date

logger = logging.getLogger("plaid.positions")

# Plaid security.type -> our security_type. Anything unmapped (or untickered)
# becomes a user-valued 'other' priced off Plaid's institution_value.
PLAID_SEC_TYPE = {
    "equity": "stock",
    "etf": "etf",
    "mutual fund": "mutual_fund",
    "fixed income": "bond",
    "cash": "cash",
    "money market": "cash",
}

# Plaid account.type -> our accounts.type CHECK vocabulary
# ('depository','credit','investment','retirement','loan','other'). Plaid still
# returns the legacy 'brokerage' for some institutions, which would violate the
# constraint and abort the sync. The rich IRA/Roth/401k/529 detail lives in
# subtype (unconstrained), stored raw.
PLAID_ACCT_TYPE = {
    "investment": "investment",
    "brokerage": "investment",
    "depository": "depository",
    "credit": "credit",
    "loan": "loan",
}


def _account_name(acct: dict) -> str:
    base = acct.get("name") or acct.get("official_name") or "Account"
    mask = acct.get("mask")
    return f"{base} ••{mask}" if mask else base


def sync_plaid_holdings(db, user_id: str, connection_id: str, payload: dict) -> dict:
    accounts = payload.get("accounts", []) or []
    securities = {s["security_id"]: s for s in (payload.get("securities", []) or [])}
    holdings = payload.get("holdings", []) or []

    # One accounts row per Plaid account; map plaid account_id -> our accounts.id.
    acct_id_map: dict[str, str] = {}
    balance_of: dict[str, float | None] = {}
    name_of: dict[str, str] = {}
    for acct in accounts:
        plaid_acct_id = acct["account_id"]
        balance_of[plaid_acct_id] = (acct.get("balances") or {}).get("current")
        name_of[plaid_acct_id] = _account_name(acct)
        row = {
            "user_id": user_id,
            "connection_id": connection_id,
            "provider_account_id": plaid_acct_id,
            "name": _account_name(acct),
            "mask": acct.get("mask"),
            "type": PLAID_ACCT_TYPE.get((acct.get("type") or "").lower(), "investment"),
            "subtype": acct.get("subtype"),
            "currency": ((acct.get("balances") or {}).get("iso_currency_code")) or "USD",
        }
        existing = (
            db.table("accounts")
            .select("id")
            .eq("user_id", user_id)
            .eq("connection_id", connection_id)
            .eq("provider_account_id", plaid_acct_id)
            .execute()
        )
        if existing.data:
            our_id = existing.data[0]["id"]
            db.table("accounts").update(row).eq("id", our_id).execute()
        else:
            our_id = db.table("accounts").insert(row).execute().data[0]["id"]
        acct_id_map[plaid_acct_id] = our_id

    today = date.today().isoformat()
    rows: list[dict] = []
    skipped = 0
    accts_with_holdings: set[str] = set()
    for h in holdings:
        plaid_acct_id = h.get("account_id")
        our_acct = acct_id_map.get(plaid_acct_id)
        qty = float(h.get("quantity") or 0)
        if not our_acct or qty == 0:
            skipped += 1
            continue
        accts_with_holdings.add(plaid_acct_id)
        sec = securities.get(h.get("security_id")) or {}
        ticker = (sec.get("ticker_symbol") or "").upper().strip()
        name = sec.get("name")

        if ticker:
            symbol = ticker
            sec_type = PLAID_SEC_TYPE.get((sec.get("type") or "").lower(), "other")
        else:
            # No public ticker (institutional 401k fund, cash sweep): give it a
            # stable synthetic symbol and value it off Plaid (non-market 'other').
            symbol = f"PLAID:{h.get('security_id')}"
            sec_type = "other"

        cost_total = h.get("cost_basis")
        cost_basis = (float(cost_total) / qty) if (cost_total not in (None, "") and qty) else 0.0

        row = {
            "user_id": user_id,
            "account_id": our_acct,
            "symbol": symbol,
            "name": name,
            "security_type": sec_type,
            "quantity": qty,
            "cost_basis": round(cost_basis, 6),
            "currency": h.get("iso_currency_code") or "USD",
            "as_of": today,
        }
        inst_price = h.get("institution_price")
        inst_value = h.get("institution_value")
        try:
            if inst_value not in (None, ""):
                row["current_value"] = round(float(inst_value), 4)
            if inst_price not in (None, ""):
                row["current_price"] = round(float(inst_price), 6)
            elif "current_value" in row and qty:
                # No price (cash sweep / untickered fund): derive per-unit so the
                # portfolio rollup (which values by current_price) doesn't read $0.
                row["current_price"] = round(row["current_value"] / qty, 6)
        except (TypeError, ValueError):
            pass
        rows.append(row)

    # Balance fallback: when Plaid returns no positions for an account (common
    # with Fidelity — balances available, holdings not), represent the account as
    # a single line valued at its balance so it still counts toward net worth.
    bal_added = 0
    for plaid_acct_id, our_id in acct_id_map.items():
        if plaid_acct_id in accts_with_holdings:
            continue
        bal = balance_of.get(plaid_acct_id)
        if not bal:
            continue
        rows.append({
            "user_id": user_id,
            "account_id": our_id,
            "symbol": f"PLAID:{plaid_acct_id}:BAL",
            "name": f"{name_of.get(plaid_acct_id, 'Account')} balance",
            "security_type": "other",
            "quantity": 1,
            "cost_basis": round(float(bal), 4),
            "current_price": round(float(bal), 6),
            "current_value": round(float(bal), 4),
            "currency": "USD",
            "as_of": today,
        })
        bal_added += 1

    # Full-replace across ALL of this connection's accounts (including any that
    # vanished from this payload), so no stale holdings linger.
    conn_accts = (
        db.table("accounts")
        .select("id")
        .eq("user_id", user_id)
        .eq("connection_id", connection_id)
        .execute()
    )
    all_ids = list({a["id"] for a in (conn_accts.data or [])} | set(acct_id_map.values()))
    if all_ids:
        db.table("holdings").delete().in_("account_id", all_ids).execute()
    if rows:
        db.table("holdings").insert(rows).execute()

    logger.info(
        "Plaid sync: accounts=%d synced=%d (balance-fallback=%d) skipped=%d",
        len(acct_id_map), len(rows), bal_added, skipped,
    )
    return {
        "accounts": len(acct_id_map),
        "synced": len(rows),
        "balance_fallback": bal_added,
        "skipped": skipped,
    }
