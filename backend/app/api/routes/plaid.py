from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user

router = APIRouter()


@router.post("/link-token")
async def create_link_token(user: dict = Depends(get_current_user)):
    # TODO Phase 2 — call Plaid /link/token/create with the user's id and
    # the products we want (transactions, investments, liabilities, etc.).
    raise HTTPException(status_code=501, detail="Plaid integration not yet implemented")


class PlaidExchangeRequest(BaseModel):
    public_token: str
    institution_name: str | None = None
    institution_logo_url: str | None = None


@router.post("/exchange")
async def exchange_public_token(
    body: PlaidExchangeRequest,
    user: dict = Depends(get_current_user),
):
    # TODO Phase 2 — exchange public_token for access_token, store encrypted,
    # fetch accounts + initial transactions/holdings, persist.
    raise HTTPException(status_code=501, detail="Plaid integration not yet implemented")


@router.post("/sync")
async def sync_plaid(user: dict = Depends(get_current_user)):
    # TODO Phase 2 — pull transactions/balances/holdings deltas for all
    # active Plaid connections.
    raise HTTPException(status_code=501, detail="Plaid integration not yet implemented")


@router.delete("/disconnect/{connection_id}")
async def disconnect_plaid(
    connection_id: str,
    user: dict = Depends(get_current_user),
):
    # TODO Phase 2 — call Plaid /item/remove, mark connection disconnected,
    # null out encrypted tokens.
    raise HTTPException(status_code=501, detail="Plaid integration not yet implemented")
