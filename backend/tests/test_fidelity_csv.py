"""Parser tests for the Fidelity Positions CSV importer.

Runnable with pytest or directly: `python tests/test_fidelity_csv.py`
(no pytest dependency required). Uses synthetic data only.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.fidelity_csv import (  # noqa: E402
    _last4,
    _num,
    import_fidelity_csv,
    parse_fidelity_csv,
)
from app.services.options import parse_occ_symbol  # noqa: E402

HEADER = (
    "Account Number,Account Name,Symbol,Description,Quantity,Last Price,"
    "Last Price Change,Current Value,Today's Gain/Loss Dollar,"
    "Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,"
    "Percent Of Account,Cost Basis Total,Average Cost Basis,Type"
)


def _row(acct, name, symbol, desc, qty="", lastpx="", curval="", costtot="", avgcost="", typ="Cash"):
    f = [""] * 16
    f[0], f[1], f[2], f[3] = acct, name, symbol, desc
    f[4], f[5], f[7] = qty, lastpx, curval
    f[13], f[14], f[15] = costtot, avgcost, typ
    return ",".join(f) + ","  # Fidelity emits a trailing comma per row


SAMPLE = "\n".join([
    HEADER,
    _row("99990001", "TEST ROTH", "SPAXX**", "HELD IN MONEY MARKET", curval="$100.00"),
    _row("99990001", "TEST ROTH", "AAPL", "APPLE INC", "10", "$200.00", "$2000.00", "$1500.00", "$150.00"),
    _row("99990001", "TEST ROTH", "VOO", "VANGUARD S&P 500 ETF", "5", "$400.00", "$2000.00", "$1800.00", "$360.00"),
    _row("99990001", "TEST ROTH", " -AAPL260116C150", "AAPL JAN 16 2026 $150 CALL", "2", "$10.00", "$2000.00", "$2000.00", "$9.00"),
    _row("99990001", "TEST ROTH", " -AAPL260116C200", "AAPL JAN 16 2026 $200 CALL", "-2", "$3.00", "-$600.00", "$1400.00", "$7.00", "Margin"),
    _row("12345", "TEST 401K", "", "BROKERAGELINK", "5000.00", "$1.00", "$5000.00", "$5000.00", "$1.00", ""),
    _row("88880002", "TEST 529", "NH2040000", "NH PORTFOLIO 2040", "100.5", "$50.00", "$5025.00", "$4000.00", "$39.80"),
    _row("88880002", "TEST 529", "Pending activity", "", curval="-$25.00"),
    '"Disclaimer text that should be ignored, with a comma."',
    "",
    '"Date downloaded Jun-02-2026 12:18 a.m ET"',
])


def _by_symbol(holdings):
    return {h["symbol"]: h for h in holdings}


def test_num():
    assert _num("$1,234.50") == 1234.50
    assert _num("-$14,800.00") == -14800.0
    assert _num("+6.15%") == 6.15
    assert _num("($1,234.50)") == -1234.50  # accounting-style negative
    assert _num("--") is None
    assert _num("") is None
    assert _num(None) is None


def test_last4():
    assert _last4("244170623") == "0623"
    assert _last4("11355") == "1355"
    assert _last4("ROTH IRA ••0623") == "0623"
    assert _last4("Manual Portfolio") is None


def test_groups_and_skips():
    groups = {g["account_number"]: g for g in parse_fidelity_csv(SAMPLE)}
    # Three accounts; disclaimer / blank / date lines ignored.
    assert set(groups) == {"99990001", "88880002", "12345"}
    assert groups["12345"]["umbrella"] is True


def test_stock_etf_and_cost_basis():
    g = {x["account_number"]: x for x in parse_fidelity_csv(SAMPLE)}["99990001"]
    h = _by_symbol(g["holdings"])
    assert h["AAPL"]["security_type"] == "stock"
    assert abs(h["AAPL"]["cost_basis"] - 150.0) < 1e-9  # 1500 / 10
    assert h["VOO"]["security_type"] == "etf"            # "ETF" in description
    assert abs(h["VOO"]["cost_basis"] - 360.0) < 1e-9
    assert h["FID:CASH:SPAXX"]["security_type"] == "other"
    assert h["FID:CASH:SPAXX"]["current_value"] == 100.0


def test_options_occ_and_short_basis():
    g = {x["account_number"]: x for x in parse_fidelity_csv(SAMPLE)}["99990001"]
    h = _by_symbol(g["holdings"])

    long_call = h["AAPL260116C00150000"]
    assert long_call["security_type"] == "option"
    assert long_call["quantity"] == 2
    # 2000 / (2 * 100) = 10.0 per share
    assert abs(long_call["cost_basis"] - 10.0) < 1e-9
    parsed = parse_occ_symbol(long_call["symbol"])
    assert parsed == {"underlying": "AAPL", "expiry": "2026-01-16", "strike": 150.0, "option_type": "C"}

    short_call = h["AAPL260116C00200000"]
    assert short_call["quantity"] == -2
    # Basis stored positive (1400 / (2*100) = 7.0); portfolio re-signs via qty.
    assert abs(short_call["cost_basis"] - 7.0) < 1e-9


def test_untickered_fund_and_pending():
    g = {x["account_number"]: x for x in parse_fidelity_csv(SAMPLE)}["88880002"]
    h = _by_symbol(g["holdings"])
    fund = h["NH2040000"]
    assert fund["security_type"] == "other"
    assert fund["quantity"] == 1
    assert fund["current_value"] == 5025.0
    assert fund["cost_basis"] == 4000.0   # preserves the gain
    assert h["FID:PENDING"]["current_value"] == -25.0


def test_blank_last_price_backderives_value():
    # A market row with no Last Price must keep its Fidelity value, not fall to
    # cost basis (Yahoo can't quote OCC options, so this is the common option case).
    csv = "\n".join([
        HEADER,
        _row("99990001", "T", "AMC", "AMC ENTERTAINMENT", "10", "", "$500.00", "$300.00", "$30.00"),
        _row("99990001", "T", " -AMC260116P5", "AMC PUT", "-1", "", "-$200.00", "$100.00", "$1.00"),
    ])
    h = _by_symbol(parse_fidelity_csv(csv)[0]["holdings"])
    assert abs(h["AMC"]["current_price"] - 50.0) < 1e-9          # 500 / 10
    assert abs(h["AMC260116P00005000"]["current_price"] - 2.0) < 1e-9  # -200 / (-1*100)


# ── Minimal in-memory Supabase stub for importer (matching/dedupe) tests ──
class _Res:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, store, name):
        self.store, self.name = store, name
        self._del, self._ins, self._in = False, None, None

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, _col, ids):
        self._in = ids
        return self

    def delete(self):
        self._del = True
        return self

    def insert(self, rows):
        self._ins = rows
        return self

    def execute(self):
        if self.name == "holdings" and self._del:
            self.store["holdings"] = [h for h in self.store["holdings"] if h["account_id"] not in (self._in or [])]
            return _Res([])
        if self.name == "holdings" and self._ins is not None:
            self.store["holdings"].extend(self._ins)
            return _Res(self._ins)
        return _Res(self.store.get(self.name, []))


class _FakeDB:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _FakeTable(self.store, name)


def _db(accounts):
    return _FakeDB({
        "accounts": accounts,
        "account_connections": [{"id": "c1", "provider": "plaid"}],
        "holdings": [],
    })


def test_import_ambiguous_plaid_last4_skipped():
    # Two linked accounts share last-4 -> ambiguous, skip instead of overwrite.
    db = _db([
        {"id": "a1", "name": "ROTH ••1234", "mask": "1234", "connection_id": "c1"},
        {"id": "a2", "name": "TRAD ••1234", "mask": "1234", "connection_id": "c1"},
    ])
    csv = "\n".join([HEADER, _row("99991234", "ROTH", "AAPL", "APPLE", "10", "$200.00", "$2000.00", "$1500.00", "$150.00")])
    res = import_fidelity_csv(db, "u", csv, commit=True)
    assert res["total_imported"] == 0
    assert res["skipped"] and "ambiguous" in res["skipped"][0]["reason"]
    assert db.store["holdings"] == []


def test_import_two_csv_accounts_same_last4_skips_second():
    db = _db([{"id": "a1", "name": "ROTH ••1234", "mask": "1234", "connection_id": "c1"}])
    csv = "\n".join([
        HEADER,
        _row("11111234", "ROTH", "AAPL", "APPLE", "10", "$200.00", "$2000.00", "$1500.00", "$150.00"),
        _row("22221234", "OTHER", "MSFT", "MICROSOFT", "5", "$400.00", "$2000.00", "$1800.00", "$360.00"),
    ])
    res = import_fidelity_csv(db, "u", csv, commit=True)
    assert len(res["matched"]) == 1
    assert any("also ends in 1234" in s["reason"] for s in res["skipped"])
    # Only the first account's holding was written under a1.
    assert {h["symbol"] for h in db.store["holdings"]} == {"AAPL"}


def test_import_dedupe_merges_cost_basis():
    db = _db([{"id": "a1", "name": "ROTH ••1234", "mask": "1234", "connection_id": "c1"}])
    csv = "\n".join([
        HEADER,
        _row("99991234", "ROTH", "AAPL", "APPLE", "10", "$200.00", "$2000.00", "$1500.00", "$150.00"),
        _row("99991234", "ROTH", "AAPL", "APPLE", "5", "$200.00", "$1000.00", "$1000.00", "$200.00"),
    ])
    import_fidelity_csv(db, "u", csv, commit=True)
    aapl = [h for h in db.store["holdings"] if h["symbol"] == "AAPL"]
    assert len(aapl) == 1
    assert aapl[0]["quantity"] == 15
    # Combined basis = (1500 + 1000) / 15 = 166.6667, not the first lot's 150.
    assert abs(aapl[0]["cost_basis"] - (2500 / 15)) < 1e-4


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
