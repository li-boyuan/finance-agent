"""IBKR client + auth-strategy factory.

The Client Portal API supports two very different ways of authenticating:

  - **gateway** (self-hosted): the user runs IBKR's Java Client Portal Gateway
    on their own machine, logs in via browser once a day, and we hit it at
    a user-supplied base URL (usually https://localhost:5000). Session lives
    in a cookie that the gateway sets; we don't manage tokens.

  - **oauth1a** (production): registered IBKR consumers sign every request
    with an RSA key. Not implemented yet — left as a TODO seam so adding it
    is just a new branch in `build_client_for_connection`.

`auth_config` (jsonb on account_connections) carries strategy-specific config.
Opaque secrets (if any) still live in the existing encrypted_* columns.
"""

import logging

import httpx

logger = logging.getLogger("ibkr")


class IBKRClient:
    """Thin wrapper around the Client Portal API endpoints we care about.

    Authentication is the caller's problem: pass a configured httpx.AsyncClient
    (correct base_url, headers, cookies, SSL verification). Use
    `build_client_for_connection` to get one from a stored connection row."""

    def __init__(self, http_client: httpx.AsyncClient, account_id: str | None = None):
        self._client = http_client
        self.account_id = account_id

    async def get_accounts(self) -> list[dict]:
        resp = await self._client.get("/portfolio/accounts")
        resp.raise_for_status()
        return resp.json()

    async def get_positions(self, account_id: str | None = None) -> list[dict]:
        """Returns all positions across all pages.

        IBKR paginates at /portfolio/{acct}/positions/{page}, 30 rows per page."""
        acct = account_id or self.account_id
        if not acct:
            raise ValueError("account_id required (none on client, none passed)")

        positions: list[dict] = []
        page = 0
        while True:
            resp = await self._client.get(f"/portfolio/{acct}/positions/{page}")
            resp.raise_for_status()
            batch = resp.json() or []
            positions.extend(batch)
            if len(batch) < 30:
                break
            page += 1
            if page > 50:
                logger.warning("Bailing out of positions pagination at page 50")
                break
        return positions

    async def tickle(self) -> dict:
        """Keep the gateway session alive. Call before reads if the connection
        has been idle."""
        resp = await self._client.post("/tickle")
        resp.raise_for_status()
        return resp.json()

    async def init_brokerage_session(self) -> None:
        """Best-effort init of the brokerage session. The /iserver/* market-data
        endpoints return nothing until this has been hit at least once."""
        try:
            await self._client.get("/iserver/accounts")
        except Exception:
            logger.debug("iserver/accounts init failed", exc_info=True)

    async def get_market_data_snapshot(self, conids: list, fields: list[str]) -> list[dict]:
        """Snapshot market data (incl. option greeks) for the given conids.

        The CP API primes the subscription on the first request and only fills
        computed fields (greeks) on a subsequent call — callers should request
        twice with a short pause."""
        if not conids:
            return []
        params = {
            "conids": ",".join(str(c) for c in conids),
            "fields": ",".join(fields),
        }
        resp = await self._client.get("/iserver/marketdata/snapshot", params=params)
        resp.raise_for_status()
        return resp.json() or []

    async def close(self):
        await self._client.aclose()


def build_client_for_connection(connection: dict) -> IBKRClient:
    """Construct an IBKRClient from a stored account_connections row.

    Dispatches on `auth_config.strategy`. Raises on unsupported strategy so
    callers fail loudly during the auth-method rollout."""
    auth_config = connection.get("auth_config") or {}
    strategy = auth_config.get("strategy", "gateway")
    account_id = connection.get("provider_item_id")

    if strategy == "gateway":
        base_url = auth_config.get("base_url")
        if not base_url:
            raise ValueError("Gateway connection missing auth_config.base_url")
        verify_ssl = auth_config.get("verify_ssl", False)
        http_client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/v1/api",
            verify=verify_ssl,
            timeout=30.0,
        )
        return IBKRClient(http_client, account_id=account_id)

    if strategy == "oauth1a":
        # Intentionally not implemented. When adding: sign each request with
        # the consumer's RSA key per IBKR's OAuth 1.0a spec, store the
        # consumer_key + access_token_secret reference in auth_config,
        # and keep the live access_token in encrypted_access_token.
        raise NotImplementedError(
            "IBKR OAuth 1.0a not implemented yet. Use the self-hosted "
            "Client Portal Gateway (strategy='gateway') for now."
        )

    raise ValueError(f"Unknown IBKR auth strategy: {strategy!r}")
