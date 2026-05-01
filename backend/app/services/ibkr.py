import httpx

from app.config import settings
from app.core.security import encrypt_token, decrypt_token

IBKR_AUTH_URL = "https://www.interactivebrokers.com/authorize"
IBKR_TOKEN_URL = "https://api.interactivebrokers.com/v1/api/oauth/token"
IBKR_BASE_URL = "https://api.interactivebrokers.com/v1/api"


def get_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.ibkr_client_id,
        "redirect_uri": settings.ibkr_redirect_uri,
        "scope": "readonly",
        "state": state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{IBKR_AUTH_URL}?{qs}"


async def exchange_code_for_tokens(code: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            IBKR_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.ibkr_client_id,
                "client_secret": settings.ibkr_client_secret,
                "redirect_uri": settings.ibkr_redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            IBKR_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.ibkr_client_id,
                "client_secret": settings.ibkr_client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()


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

    async def get_trades(self, days: int = 7) -> list[dict]:
        resp = await self._client.get(
            "/iserver/account/trades",
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
