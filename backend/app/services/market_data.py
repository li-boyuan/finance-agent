import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("market_data")

YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Symbol -> (timestamp, payload). 5-minute TTL.
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 300

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FinanceAgent/0.1)",
    "Accept": "application/json",
}


async def get_quote(symbol: str) -> dict[str, Any] | None:
    """Return {symbol, name, currency, price, previous_close, day_change, day_change_pct}
    or None if the symbol can't be fetched."""
    symbol = symbol.upper().strip()
    now = time.time()

    cached = _cache.get(symbol)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    url = YAHOO_QUOTE_URL.format(symbol=symbol)
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(url, params={"interval": "1d", "range": "2d"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("Failed to fetch quote for %s: %s", symbol, e)
        return None

    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = float(meta["regularMarketPrice"])
        prev_close = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
        day_change = price - prev_close
        day_change_pct = (day_change / prev_close * 100) if prev_close else 0.0
        payload = {
            "symbol": meta.get("symbol", symbol),
            "name": meta.get("longName") or meta.get("shortName") or symbol,
            "currency": meta.get("currency", "USD"),
            "price": round(price, 4),
            "previous_close": round(prev_close, 4),
            "day_change": round(day_change, 4),
            "day_change_pct": round(day_change_pct, 4),
        }
        _cache[symbol] = (now, payload)
        return payload
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning("Malformed quote response for %s: %s", symbol, e)
        return None


async def get_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch multiple quotes; missing ones are simply absent from the result."""
    out: dict[str, dict[str, Any]] = {}
    for s in symbols:
        q = await get_quote(s)
        if q:
            out[q["symbol"]] = q
    return out
