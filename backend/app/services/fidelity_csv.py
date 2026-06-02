"""Import a Fidelity "Portfolio Positions" CSV into accounts + holdings.

Plaid only exposes Fidelity *balances* (no positions) for these account types,
so per-position detail comes from Fidelity's own CSV export. Rows are matched to
the existing Plaid-linked accounts by the last 4 digits of the account number,
and that account's holdings are full-replaced (mirroring the IBKR/Plaid sync).

CSV accounts that don't match a linked account are skipped and reported, never
auto-created — this avoids double-counting the 401(k) umbrella, which Fidelity
exports as a single "BROKERAGELINK" lump that already equals the sum of the
detailed BrokerageLink sleeves (the linked sub-accounts).
"""

import csv
import io
import logging
import re
from datetime import date

from app.services.options import CONTRACT_MULTIPLIER, build_occ_symbol

logger = logging.getLogger("fidelity.csv")

# Fidelity's compact option symbol, e.g. " -BMNR280121C65" -> BMNR 2028-01-21 $65
# Call. Leading space + dash, root (letters), YYMMDD, C/P, strike (int or decimal).
_FID_OPTION_RE = re.compile(r"^\s*-([A-Za-z]+)(\d{6})([CP])(\d+(?:\.\d+)?)$")
# A tradable ticker we can get live Yahoo quotes for (1-5 letters, optional .class).
_TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")


def _num(s: str | None) -> float | None:
    """Parse a Fidelity money/number cell. Handles $, commas, +/-, accounting
    parens, and the '--' / 'n/a' / blank placeholders -> None."""
    if s is None:
        return None
    t = s.strip().replace("$", "").replace(",", "").replace("%", "").replace("+", "")
    if t in ("", "--", "n/a", "N/A"):
        return None
    if t.startswith("(") and t.endswith(")"):  # accounting-style negative
        t = "-" + t[1:-1]
    try:
        return float(t)
    except ValueError:
        return None


def _last4(s: str | None) -> str | None:
    digits = re.sub(r"\D", "", s or "")
    return digits[-4:] if len(digits) >= 4 else None


def _market_price(last_price: float | None, current_value: float | None,
                  qty: float | None, mult: int) -> float | None:
    """Per-unit price for a market holding. Yahoo can't quote OCC option symbols,
    so the stored price is the fallback the rollup values by — back-derive it from
    Fidelity's current_value when Last Price is blank (mirrors the Plaid/IBKR
    mappers) so a quote-less position isn't valued at cost basis."""
    if last_price is not None:
        return last_price
    if current_value is not None and qty:
        return current_value / (qty * mult)
    return None


def _merge_lot(ex: dict, h: dict) -> None:
    """Fold a duplicate same-symbol lot into ex, combining totals correctly (a
    plain quantity sum would keep only the first lot's per-share basis/value)."""
    if ex["security_type"] == "other":  # qty stays 1; sum value + cost directly
        ev = (ex.get("current_value") or 0.0) + (h.get("current_value") or 0.0)
        ex["current_value"] = ev
        ex["current_price"] = ev
        ex["cost_basis"] = (ex.get("cost_basis") or 0.0) + (h.get("cost_basis") or 0.0)
        return
    mult = CONTRACT_MULTIPLIER if ex["security_type"] == "option" else 1
    q1, q2 = ex["quantity"], h["quantity"]
    cost = (ex.get("cost_basis") or 0.0) * abs(q1) * mult + (h.get("cost_basis") or 0.0) * abs(q2) * mult
    nq = q1 + q2
    ex["quantity"] = nq
    ex["cost_basis"] = (cost / (abs(nq) * mult)) if nq else 0.0
    ex["current_value"] = (ex.get("current_value") or 0.0) + (h.get("current_value") or 0.0)
    # current_price unchanged: same symbol, same day -> same Last Price.


def _classify(
    symbol: str, desc: str, qty: float | None, last_price: float | None,
    current_value: float | None, cost_total: float | None, avg_cost: float | None,
) -> dict | None:
    """Map one CSV row to a holding dict (sans account_id/user_id/as_of), or None."""
    symbol = (symbol or "").strip()
    desc = (desc or "").strip()
    up_desc = desc.upper()

    opt = _FID_OPTION_RE.match(symbol)
    if opt:
        if not qty:
            return None
        root, ymd, cp, strike = opt.groups()
        expiry = f"20{ymd[0:2]}-{ymd[2:4]}-{ymd[4:6]}"
        occ = build_occ_symbol(root, expiry, float(strike), cp)
        # Store a positive per-share basis; portfolio re-derives signed cost from
        # quantity. abs(cost_total)/(abs(qty)*100) reconstructs Fidelity's total
        # exactly (avg_cost is only rounded to cents).
        if cost_total is not None and qty:
            cost_basis = abs(cost_total) / (abs(qty) * CONTRACT_MULTIPLIER)
        else:
            cost_basis = avg_cost or 0.0
        return {
            "symbol": occ, "name": desc or occ, "security_type": "option",
            "quantity": qty, "cost_basis": cost_basis,
            "current_price": _market_price(last_price, current_value, qty, CONTRACT_MULTIPLIER),
            "current_value": current_value,
        }

    is_cash = symbol.endswith("**") or "MONEY MARKET" in up_desc
    is_pending = symbol.lower() == "pending activity"

    if not is_cash and not is_pending and _TICKER_RE.match(symbol):
        if not qty:
            return None
        sec_type = "etf" if "ETF" in up_desc else "stock"
        if cost_total is not None and qty:
            cost_basis = abs(cost_total) / abs(qty)
        else:
            cost_basis = avg_cost or 0.0
        return {
            "symbol": symbol, "name": desc or symbol, "security_type": sec_type,
            "quantity": qty, "cost_basis": cost_basis,
            "current_price": _market_price(last_price, current_value, qty, 1),
            "current_value": current_value,
        }

    # Everything else — cash sweep, pending activity, untickered 529/401k funds —
    # becomes a non-market 'other' line valued exactly at its current value, with
    # the cost basis preserved so gains still show. qty=1 keeps value ==
    # current_value with no price*qty rounding drift.
    if current_value is None:
        return None
    if is_cash:
        clean = symbol.rstrip("*") or "CASH"
        name, out_symbol = f"Cash — {clean}", f"FID:CASH:{clean}"
    elif is_pending:
        name, out_symbol = "Pending activity", "FID:PENDING"
    else:
        name = desc or symbol or "Fidelity holding"
        out_symbol = symbol or f"FID:{name[:24]}"
    return {
        "symbol": out_symbol, "name": name, "security_type": "other",
        "quantity": 1, "cost_basis": cost_total if cost_total is not None else current_value,
        "current_price": current_value, "current_value": current_value,
    }


def parse_fidelity_csv(text: str) -> list[dict]:
    """Group parsed positions by Fidelity account number. Returns
    [{account_number, account_name, holdings, value, umbrella}]."""
    groups: dict[str, dict] = {}
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 8 or not (r[0] or "").strip().isdigit():
            continue  # header, blank, disclaimer, and "Date downloaded" lines
        acct_num = r[0].strip()
        g = groups.setdefault(acct_num, {
            "account_number": acct_num, "account_name": (r[1] or "").strip(),
            "holdings": [], "value": 0.0, "umbrella": False,
        })
        symbol, desc = r[2], r[3]
        # The 401(k) umbrella lump is a single line with no symbol and desc
        # "BROKERAGELINK" — flag it so we can explain the skip clearly.
        if not (symbol or "").strip() and desc.strip().upper() == "BROKERAGELINK":
            g["umbrella"] = True
        h = _classify(
            symbol, desc, _num(r[4]), _num(r[5]), _num(r[7]),
            _num(r[13]) if len(r) > 13 else None,
            _num(r[14]) if len(r) > 14 else None,
        )
        if h:
            g["holdings"].append(h)
            g["value"] += h.get("current_value") or 0.0
    return list(groups.values())


def import_fidelity_csv(db, user_id: str, text: str, commit: bool = True) -> dict:
    """Parse + (optionally) write. With commit=False, returns the same matched /
    skipped breakdown without touching the database (preview)."""
    groups = parse_fidelity_csv(text)

    accts = (
        db.table("accounts").select("id, name, mask, connection_id")
        .eq("user_id", user_id).execute().data or []
    )
    providers = {
        c["id"]: c.get("provider")
        for c in (db.table("account_connections").select("id, provider").eq("user_id", user_id).execute().data or [])
    }
    # Match only Plaid-linked (Fidelity) accounts, by the last-4 mask. Bucket by
    # last-4 so an ambiguous match (two linked accounts ending in the same 4
    # digits) is detected and skipped rather than silently overwriting.
    buckets: dict[str, list[dict]] = {}
    for a in accts:
        if providers.get(a.get("connection_id")) != "plaid":
            continue
        key = _last4(a.get("mask")) or _last4(a.get("name"))
        if key:
            buckets.setdefault(key, []).append(a)

    today = date.today().isoformat()
    matched: list[dict] = []
    skipped: list[dict] = []
    insert_rows: list[dict] = []
    replace_ids: list[str] = []
    used_ids: set[str] = set()

    def _skip(g: dict, reason: str) -> None:
        skipped.append({
            "account": g["account_name"], "account_number": g["account_number"],
            "value": round(g["value"], 2), "holdings": len(g["holdings"]),
            "reason": reason,
        })

    for g in groups:
        l4 = _last4(g["account_number"])
        cands = buckets.get(l4, [])
        if len(cands) != 1:
            if g["umbrella"]:
                _skip(g, "401(k) umbrella — its detail is already imported under "
                          "the BrokerageLink sleeves; skipped to avoid double-counting.")
            elif len(cands) > 1:
                _skip(g, f"ambiguous — {len(cands)} linked accounts end in {l4}; skipped")
            else:
                _skip(g, "no matching linked account (connect it via Plaid first)")
            continue
        acct = cands[0]
        if acct["id"] in used_ids:
            _skip(g, f"another CSV account also ends in {l4}; skipped to avoid double-counting")
            continue
        used_ids.add(acct["id"])

        # Dedupe within the account by symbol (defensive vs the unique index).
        by_symbol: dict[str, dict] = {}
        for h in g["holdings"]:
            ex = by_symbol.get(h["symbol"])
            if ex:
                _merge_lot(ex, h)
            else:
                by_symbol[h["symbol"]] = dict(h)

        replace_ids.append(acct["id"])
        for h in by_symbol.values():
            insert_rows.append({
                "user_id": user_id, "account_id": acct["id"],
                "symbol": h["symbol"], "name": h["name"],
                "security_type": h["security_type"],
                "quantity": round(h["quantity"], 8),
                "cost_basis": round(h["cost_basis"], 6) if h["cost_basis"] is not None else None,
                "current_price": round(h["current_price"], 6) if h["current_price"] is not None else None,
                "current_value": round(h["current_value"], 4) if h["current_value"] is not None else None,
                "currency": "USD", "as_of": today,
            })
        matched.append({
            "account": acct["name"], "account_number": g["account_number"],
            "holdings": len(by_symbol), "value": round(g["value"], 2),
        })

    # Only delete when we have replacement rows to insert, so a parse that yields
    # nothing can never empty an account. (delete+insert isn't a single
    # transaction — same accepted pattern as the Plaid/IBKR syncs; reversible by
    # re-importing.)
    wrote = bool(commit and replace_ids and insert_rows)
    if wrote:
        db.table("holdings").delete().in_("account_id", replace_ids).execute()
        db.table("holdings").insert(insert_rows).execute()

    logger.info(
        "Fidelity CSV import: matched=%d skipped=%d rows=%d commit=%s",
        len(matched), len(skipped), len(insert_rows), commit,
    )
    return {
        "committed": wrote,
        "as_of": today,
        "total_imported": len(insert_rows),
        "matched": sorted(matched, key=lambda m: -m["value"]),
        "skipped": skipped,
    }
