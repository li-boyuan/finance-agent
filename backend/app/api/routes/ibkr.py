from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, get_client_ip
from app.core.audit import log_access

router = APIRouter()


class IBKRConnectRequest(BaseModel):
    authorization_code: str


@router.post("/connect")
async def connect_ibkr(
    body: IBKRConnectRequest,
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "connect_ibkr", "broker_connection", ip_address=ip)
    # TODO: exchange auth code for tokens via IBKR OAuth
    # TODO: encrypt and store tokens
    return {"status": "connected", "broker": "ibkr"}


@router.post("/sync")
async def sync_trades(
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "sync_trades", "broker_connection", ip_address=ip)
    # TODO: fetch recent trades from IBKR and upsert
    return {"synced": 0, "new_trades": 0}


@router.delete("/disconnect")
async def disconnect_ibkr(
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "disconnect_ibkr", "broker_connection", ip_address=ip)
    # TODO: remove broker connection and wipe tokens
    return {"status": "disconnected"}
