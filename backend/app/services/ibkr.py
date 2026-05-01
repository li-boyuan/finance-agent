import httpx

from app.config import settings
from app.core.security import encrypt_token, decrypt_token


IBKR_BASE_URL = "https://api.ibkr.com/v1/api"


class IBKRClient:
    def __init__(self, access_token: str):
        self._token = access_token
        self._client = httpx.AsyncClient(
            base_url=IBKR_BASE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def get_accounts(self) -> list[dict]:
        resp = await self._client.get("/portfolio/accounts")
        resp.raise_for_status()
        return resp.json()

    async def get_trades(self, account_id: str, days: int = 7) -> list[dict]:
        resp = await self._client.get(
            f"/iserver/account/trades",
            params={"days": days},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_positions(self, account_id: str) -> list[dict]:
        resp = await self._client.get(
            f"/portfolio/{account_id}/positions/0",
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()
