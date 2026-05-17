import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, get_client_ip
from app.core.audit import log_access
from app.core.security import encrypt_token, decrypt_token
from app.db import get_supabase
from app.services.ibkr import (
    get_authorize_url,
    exchange_code_for_tokens,
    refresh_access_token,
    IBKRClient,
)
from app.services.trade_sync import sync_trades_from_ibkr

router = APIRouter()


@router.get("/auth-url")
async def get_ibkr_auth_url(
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "get_ibkr_auth_url", "account_connection", ip_address=ip)
    state = secrets.token_urlsafe(32)
    url = get_authorize_url(state)
    return {"url": url, "state": state}


class IBKRCallbackRequest(BaseModel):
    code: str
    state: str


@router.post("/callback")
async def ibkr_callback(
    body: IBKRCallbackRequest,
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "ibkr_callback", "account_connection", ip_address=ip)

    tokens = await exchange_code_for_tokens(body.code)

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)

    client = IBKRClient(access_token)
    try:
        accounts = await client.get_accounts()
    finally:
        await client.close()

    account_id = accounts[0]["accountId"] if accounts else None

    db = get_supabase()

    existing = (
        db.table("account_connections")
        .select("id")
        .eq("user_id", user_id)
        .eq("provider", "ibkr")
        .execute()
    )
    if existing.data:
        db.table("account_connections").update({
            "encrypted_access_token": encrypt_token(access_token).decode("latin-1"),
            "encrypted_refresh_token": encrypt_token(refresh_token).decode("latin-1"),
            "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
            "provider_item_id": account_id,
            "status": "active",
            "last_sync_at": None,
        }).eq("id", existing.data[0]["id"]).execute()
        connection_id = existing.data[0]["id"]
    else:
        result = db.table("account_connections").insert({
            "user_id": user_id,
            "provider": "ibkr",
            "encrypted_access_token": encrypt_token(access_token).decode("latin-1"),
            "encrypted_refresh_token": encrypt_token(refresh_token).decode("latin-1"),
            "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
            "provider_item_id": account_id,
            "status": "active",
        }).execute()
        connection_id = result.data[0]["id"]

    return {"status": "connected", "provider": "ibkr", "provider_item_id": account_id}


@router.get("/status")
async def ibkr_status(
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()

    result = (
        db.table("account_connections")
        .select("id, provider, provider_item_id, status, last_sync_at")
        .eq("user_id", user_id)
        .eq("provider", "ibkr")
        .execute()
    )

    if not result.data:
        return {"connected": False}

    conn = result.data[0]
    return {
        "connected": conn["status"] == "active",
        "provider_item_id": conn["provider_item_id"],
        "status": conn["status"],
        "last_sync_at": conn["last_sync_at"],
    }


@router.post("/sync")
async def sync_trades(
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "sync_trades", "account_connection", ip_address=ip)

    db = get_supabase()
    conn = (
        db.table("account_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("provider", "ibkr")
        .eq("status", "active")
        .execute()
    )

    if not conn.data:
        raise HTTPException(status_code=404, detail="No active IBKR connection")

    connection = conn.data[0]
    access_token = decrypt_token(connection["encrypted_access_token"].encode("latin-1"))

    if connection.get("token_expires_at"):
        expires_at = datetime.fromisoformat(connection["token_expires_at"])
        if expires_at < datetime.now(timezone.utc):
            refresh_tok = decrypt_token(connection["encrypted_refresh_token"].encode("latin-1"))
            tokens = await refresh_access_token(refresh_tok)
            access_token = tokens["access_token"]
            new_refresh = tokens.get("refresh_token", refresh_tok)
            db.table("account_connections").update({
                "encrypted_access_token": encrypt_token(access_token).decode("latin-1"),
                "encrypted_refresh_token": encrypt_token(new_refresh).decode("latin-1"),
                "token_expires_at": (
                    datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))
                ).isoformat(),
            }).eq("id", connection["id"]).execute()

    client = IBKRClient(access_token)
    try:
        result = await sync_trades_from_ibkr(
            client, user_id, connection["id"], days=7
        )
    finally:
        await client.close()

    db.table("account_connections").update({
        "last_sync_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", connection["id"]).execute()

    return result


@router.delete("/disconnect")
async def disconnect_ibkr(
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    user_id = user["sub"]
    log_access(user_id, "disconnect_ibkr", "account_connection", ip_address=ip)

    db = get_supabase()
    db.table("account_connections").update({
        "status": "disconnected",
        "encrypted_access_token": None,
        "encrypted_refresh_token": None,
    }).eq("user_id", user_id).eq("provider", "ibkr").execute()

    return {"status": "disconnected"}
