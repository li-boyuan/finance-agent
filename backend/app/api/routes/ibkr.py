"""IBKR connection + sync routes.

Today we support the self-hosted Client Portal Gateway: user runs IBKR's Java
gateway locally, logs in via browser, and gives us the gateway URL. We probe
it, store the URL in `auth_config`, and let /sync pull positions on demand.

Production OAuth 1.0a is left as a future seam — see services/ibkr.py."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_client_ip
from app.core.audit import log_access
from app.db import get_supabase
from app.services.ibkr import build_client_for_connection
from app.services.ibkr_positions import sync_positions

router = APIRouter()


class IBKRConnectRequest(BaseModel):
    base_url: str = Field(..., description="Gateway base URL, e.g. https://localhost:5000")
    verify_ssl: bool = Field(default=False, description="Gateway uses a self-signed cert by default")


@router.post("/connect")
async def ibkr_connect(
    body: IBKRConnectRequest,
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    """Probe the user's Client Portal Gateway and persist the connection."""
    user_id = user["sub"]
    log_access(user_id, "ibkr_connect", "account_connection", ip_address=ip)

    auth_config = {
        "strategy": "gateway",
        "base_url": body.base_url.rstrip("/"),
        "verify_ssl": body.verify_ssl,
    }

    # Probe with the same auth_config we're about to store. If the gateway
    # isn't running or the user hasn't logged in, the GET /portfolio/accounts
    # call will fail and we bail before writing anything.
    probe_connection = {"auth_config": auth_config, "provider_item_id": None}
    client = build_client_for_connection(probe_connection)
    try:
        accounts = await client.get_accounts()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not reach IBKR Gateway at {body.base_url}: {e}. "
                "Make sure the gateway is running and you've logged in via the browser."
            ),
        )
    finally:
        await client.close()

    if not accounts:
        raise HTTPException(status_code=400, detail="Gateway returned no accounts.")

    account_id = accounts[0].get("accountId") or accounts[0].get("id")

    db = get_supabase()
    existing = (
        db.table("account_connections")
        .select("id")
        .eq("user_id", user_id)
        .eq("provider", "ibkr")
        .execute()
    )
    payload = {
        "user_id": user_id,
        "provider": "ibkr",
        "provider_item_id": account_id,
        "status": "active",
        "auth_config": auth_config,
        "institution_name": "Interactive Brokers",
    }
    if existing.data:
        db.table("account_connections").update(payload).eq(
            "id", existing.data[0]["id"]
        ).execute()
    else:
        db.table("account_connections").insert(payload).execute()

    return {
        "status": "connected",
        "provider": "ibkr",
        "provider_item_id": account_id,
        "accounts_visible": len(accounts),
    }


@router.get("/status")
async def ibkr_status(user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    db = get_supabase()

    result = (
        db.table("account_connections")
        .select("id, provider, provider_item_id, status, last_sync_at, auth_config")
        .eq("user_id", user_id)
        .eq("provider", "ibkr")
        .execute()
    )

    if not result.data:
        return {"connected": False}

    conn = result.data[0]
    auth_config = conn.get("auth_config") or {}
    return {
        "connected": conn["status"] == "active",
        "provider_item_id": conn["provider_item_id"],
        "status": conn["status"],
        "last_sync_at": conn["last_sync_at"],
        "strategy": auth_config.get("strategy"),
        "base_url": auth_config.get("base_url"),
    }


@router.post("/sync")
async def ibkr_sync(
    user: dict = Depends(get_current_user),
    ip: str = Depends(get_client_ip),
):
    """Pull live positions from IBKR and replace this user's IBKR holdings."""
    user_id = user["sub"]
    log_access(user_id, "ibkr_sync", "account_connection", ip_address=ip)

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
    ibkr_account_id = connection["provider_item_id"]
    if not ibkr_account_id:
        raise HTTPException(
            status_code=400,
            detail="Connection has no IBKR account ID — reconnect to refresh.",
        )

    client = build_client_for_connection(connection)
    try:
        result = await sync_positions(
            db, client, user_id, connection["id"], ibkr_account_id
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"IBKR sync failed: {e}")
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
        "auth_config": {},
        "encrypted_access_token": None,
        "encrypted_refresh_token": None,
    }).eq("user_id", user_id).eq("provider", "ibkr").execute()

    return {"status": "disconnected"}
