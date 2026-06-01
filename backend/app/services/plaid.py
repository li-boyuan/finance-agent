"""Thin async Plaid REST client (httpx, no SDK dependency).

Every request carries client_id + secret in the JSON body, per Plaid's API.
Base URL is selected by PLAID_ENV (sandbox / development / production).
We only use the pieces we need: Link token, public-token exchange, investments
holdings, and item removal.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger("plaid")

_HOSTS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


def _base_url() -> str:
    return _HOSTS.get(settings.plaid_env, _HOSTS["sandbox"])


def is_configured() -> bool:
    return bool(settings.plaid_client_id and settings.plaid_secret)


async def _post(path: str, payload: dict) -> dict:
    body = {
        "client_id": settings.plaid_client_id,
        "secret": settings.plaid_secret,
        **payload,
    }
    async with httpx.AsyncClient(base_url=_base_url(), timeout=30.0) as client:
        resp = await client.post(path, json=body)
        if resp.status_code >= 400:
            # Surface Plaid's structured error (error_code/message) to the caller.
            try:
                err = resp.json()
            except Exception:
                err = {"error_message": resp.text}
            raise PlaidError(resp.status_code, err)
        return resp.json()


class PlaidError(Exception):
    def __init__(self, status: int, body: dict):
        self.status = status
        self.body = body
        msg = body.get("error_message") or body.get("error_code") or str(body)
        super().__init__(f"Plaid {status}: {msg}")


async def create_link_token(user_id: str) -> str:
    data = await _post(
        "/link/token/create",
        {
            "client_name": "Finance Agent",
            "user": {"client_user_id": user_id},
            "products": ["investments"],
            "country_codes": ["US"],
            "language": "en",
        },
    )
    return data["link_token"]


async def exchange_public_token(public_token: str) -> dict:
    """Returns {access_token, item_id}."""
    return await _post("/item/public_token/exchange", {"public_token": public_token})


async def get_investments_holdings(access_token: str) -> dict:
    """Returns {accounts, holdings, securities, item}."""
    return await _post("/investments/holdings/get", {"access_token": access_token})


async def remove_item(access_token: str) -> dict:
    return await _post("/item/remove", {"access_token": access_token})
