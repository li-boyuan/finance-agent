import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.security import decrypt_token, encrypt_token
from app.db import get_supabase
from app.services import plaid as plaid_client
from app.services.plaid_positions import sync_plaid_holdings

router = APIRouter()
logger = logging.getLogger("plaid.route")


def _require_plaid():
    if not plaid_client.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Plaid is not configured (set PLAID_CLIENT_ID / PLAID_SECRET).",
        )


def _plaid_connection(db, user_id: str, active_only: bool = True) -> dict | None:
    q = (
        db.table("account_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("provider", "plaid")
    )
    if active_only:
        q = q.eq("status", "active")
    res = q.execute()
    return res.data[0] if res.data else None


async def _sync_connection(db, user_id: str, conn: dict) -> dict:
    enc = (conn.get("auth_config") or {}).get("access_token_enc")
    if not enc:
        raise HTTPException(status_code=400, detail="Plaid connection missing access token.")
    access_token = decrypt_token(enc.encode())
    try:
        payload = await plaid_client.get_investments_holdings(access_token)
    except plaid_client.PlaidError as e:
        raise HTTPException(status_code=502, detail=str(e))
    result = sync_plaid_holdings(db, user_id, conn["id"], payload)
    db.table("account_connections").update(
        {"last_sync_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", conn["id"]).execute()
    return result


@router.post("/link-token")
async def create_link_token(user: dict = Depends(get_current_user)):
    _require_plaid()
    try:
        token = await plaid_client.create_link_token(user["sub"])
    except plaid_client.PlaidError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"link_token": token}


class PlaidExchangeRequest(BaseModel):
    public_token: str
    institution_name: str | None = None


@router.post("/exchange")
async def exchange_public_token(
    body: PlaidExchangeRequest,
    user: dict = Depends(get_current_user),
):
    _require_plaid()
    user_id = user["sub"]
    db = get_supabase()
    try:
        ex = await plaid_client.exchange_public_token(body.public_token)
    except plaid_client.PlaidError as e:
        raise HTTPException(status_code=502, detail=str(e))

    auth_config = {
        "strategy": "plaid",
        "item_id": ex["item_id"],
        "institution_name": body.institution_name,
        "access_token_enc": encrypt_token(ex["access_token"]).decode(),
    }
    payload = {
        "user_id": user_id,
        "provider": "plaid",
        "provider_item_id": ex["item_id"],
        "status": "active",
        "auth_config": auth_config,
    }
    # Reuse any prior Plaid connection (even a disconnected one) so reconnecting
    # keeps the same connection_id — otherwise the old accounts/holdings orphan
    # and double-count. MVP: one Plaid item per user.
    existing = _plaid_connection(db, user_id, active_only=False)
    if existing:
        db.table("account_connections").update(payload).eq("id", existing["id"]).execute()
        conn_id = existing["id"]
    else:
        conn_id = db.table("account_connections").insert(payload).execute().data[0]["id"]

    result = await _sync_connection(db, user_id, {"id": conn_id, "auth_config": auth_config})
    return {"status": "connected", "institution": body.institution_name, **result}


@router.post("/sync")
async def sync_plaid(user: dict = Depends(get_current_user)):
    _require_plaid()
    db = get_supabase()
    conn = _plaid_connection(db, user["sub"])
    if not conn:
        raise HTTPException(status_code=404, detail="No active Plaid connection.")
    return await _sync_connection(db, user["sub"], conn)


@router.get("/status")
async def plaid_status(user: dict = Depends(get_current_user)):
    db = get_supabase()
    conn = _plaid_connection(db, user["sub"])
    if not conn:
        return {"connected": False, "configured": plaid_client.is_configured()}
    ac = conn.get("auth_config") or {}
    return {
        "connected": True,
        "configured": plaid_client.is_configured(),
        "connection_id": conn["id"],
        "institution_name": ac.get("institution_name"),
        "last_sync_at": conn.get("last_sync_at"),
    }


@router.delete("/disconnect/{connection_id}")
async def disconnect_plaid(connection_id: str, user: dict = Depends(get_current_user)):
    db = get_supabase()
    res = (
        db.table("account_connections")
        .select("*")
        .eq("user_id", user["sub"])
        .eq("id", connection_id)
        .eq("provider", "plaid")
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Connection not found.")
    conn = res.data[0]
    enc = (conn.get("auth_config") or {}).get("access_token_enc")
    if enc and plaid_client.is_configured():
        try:
            await plaid_client.remove_item(decrypt_token(enc.encode()))
        except Exception:
            logger.warning("Plaid item remove failed; disconnecting locally", exc_info=True)
    # Drop the stored token; keep already-synced accounts/holdings.
    new_cfg = {k: v for k, v in (conn.get("auth_config") or {}).items() if k != "access_token_enc"}
    db.table("account_connections").update(
        {"status": "disconnected", "auth_config": new_cfg}
    ).eq("id", connection_id).execute()
    return {"disconnected": True}
