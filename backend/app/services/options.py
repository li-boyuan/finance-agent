import re
from datetime import date as date_cls

# Standard US equity option contract multiplier — 100 shares per contract.
# Index options can differ but we treat all as 100 for MVP.
CONTRACT_MULTIPLIER = 100

# An OSI option symbol's tail is fixed-width: YYMMDD (6) + C/P (1) + strike (8)
# = 15 chars. The root precedes it. We parse from the right so any root length
# works — including adjusted-option roots that carry a trailing digit from a
# corporate action (e.g. "GME1").
_OCC_TAIL_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
_OCC_ROOT_RE = re.compile(r"^[A-Z][A-Z0-9]{0,5}$")


def build_occ_symbol(underlying: str, expiry: str, strike: float, option_type: str) -> str:
    """Build an OCC-format option symbol.

    underlying: ticker (e.g. 'AAPL')
    expiry: ISO date 'YYYY-MM-DD'
    strike: decimal dollars (e.g. 200.0)
    option_type: 'C' or 'P'
    """
    underlying = underlying.upper().strip()
    if not underlying or len(underlying) > 6:
        raise ValueError(f"Invalid underlying: {underlying}")
    option_type = option_type.upper().strip()
    if option_type not in ("C", "P"):
        raise ValueError(f"Invalid option type: {option_type}")
    expiry_dt = date_cls.fromisoformat(expiry)
    yy = expiry_dt.strftime("%y")
    mm = expiry_dt.strftime("%m")
    dd = expiry_dt.strftime("%d")
    strike_padded = f"{int(round(strike * 1000)):08d}"
    return f"{underlying}{yy}{mm}{dd}{option_type}{strike_padded}"


def parse_occ_symbol(occ: str) -> dict | None:
    occ = (occ or "").strip().upper()
    if len(occ) < 16:  # 1-char root + 15-char tail minimum
        return None
    root, tail = occ[:-15], occ[-15:]
    tm = _OCC_TAIL_RE.match(tail)
    if not tm or not _OCC_ROOT_RE.match(root):
        return None
    yy, mm, dd, otype, strike_raw = tm.groups()
    # Strip the trailing adjustment digit so adjusted options group under their
    # base underlying (e.g. GME1 -> GME).
    underlying = root.rstrip("0123456789") or root
    return {
        "underlying": underlying,
        "expiry": f"20{yy}-{mm}-{dd}",
        "strike": int(strike_raw) / 1000.0,
        "option_type": "C" if otype == "C" else "P",
    }


def format_option_name(occ: str) -> str:
    """Human-readable option name from OCC symbol. Returns the OCC if unparseable."""
    parsed = parse_occ_symbol(occ)
    if not parsed:
        return occ
    expiry_dt = date_cls.fromisoformat(parsed["expiry"])
    type_label = "Call" if parsed["option_type"] == "C" else "Put"
    strike = parsed["strike"]
    strike_str = f"${strike:.0f}" if strike == int(strike) else f"${strike:.2f}"
    return (
        f"{parsed['underlying']} "
        f"{expiry_dt.strftime('%b %-d').replace(' 0', ' ')} "
        f"'{expiry_dt.strftime('%y')} "
        f"{strike_str} {type_label}"
    )
