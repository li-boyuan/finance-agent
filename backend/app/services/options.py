import re
from datetime import date as date_cls

# Standard US equity option contract multiplier — 100 shares per contract.
# Index options can differ but we treat all as 100 for MVP.
CONTRACT_MULTIPLIER = 100

OCC_RE = re.compile(r"^([A-Z]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


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
    m = OCC_RE.match(occ)
    if not m:
        return None
    underlying, yy, mm, dd, otype, strike_raw = m.groups()
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
