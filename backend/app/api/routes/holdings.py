from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.db import get_supabase
from app.services.options import build_occ_symbol, format_option_name
from app.services.portfolio import NON_MARKET_TYPES

router = APIRouter()

MANUAL_ACCOUNT_NAME = "Manual Portfolio"


def get_or_create_manual_account(db, user_id: str) -> str:
    """Find or create the user's 'Manual Portfolio' account for manually entered holdings."""
    existing = (
        db.table("accounts")
        .select("id")
        .eq("user_id", user_id)
        .eq("name", MANUAL_ACCOUNT_NAME)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    created = (
        db.table("accounts")
        .insert({
            "user_id": user_id,
            "name": MANUAL_ACCOUNT_NAME,
            "type": "investment",
            "subtype": "manual",
            "currency": "USD",
        })
        .execute()
    )
    return created.data[0]["id"]


class HoldingCreate(BaseModel):
    # symbol required for market types, optional for assets (we'll synthesize one)
    symbol: str | None = Field(default=None, max_length=40)
    name: str | None = None
    security_type: str = "stock"
    quantity: float = Field(gt=0)
    cost_basis: float = Field(ge=0)
    # For non-market assets (real_estate / vehicle / other): the user's
    # current valuation. Ignored / overwritten for market types.
    current_value: float | None = Field(default=None, ge=0)
    # Option-specific fields. When security_type='option', these build the OCC symbol.
    underlying: str | None = Field(default=None, max_length=6)
    expiry: str | None = None  # ISO date 'YYYY-MM-DD'
    strike: float | None = Field(default=None, gt=0)
    option_type: str | None = None  # 'C' or 'P'


class HoldingUpdate(BaseModel):
    quantity: float | None = Field(default=None, gt=0)
    cost_basis: float | None = Field(default=None, ge=0)
    name: str | None = None
    current_value: float | None = Field(default=None, ge=0)


@router.get("/")
async def list_holdings(user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    db = get_supabase()
    result = (
        db.table("holdings")
        .select("*")
        .eq("user_id", user_id)
        .order("symbol")
        .execute()
    )
    return {"holdings": result.data}


@router.post("/")
async def create_holding(
    body: HoldingCreate,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()
    account_id = get_or_create_manual_account(db, user_id)
    today = date.today().isoformat()
    is_market = body.security_type not in NON_MARKET_TYPES

    if body.security_type == "option":
        # Build OCC symbol from the structured parts.
        missing = [
            f for f, v in [
                ("underlying", body.underlying),
                ("expiry", body.expiry),
                ("strike", body.strike),
                ("option_type", body.option_type),
            ] if v in (None, "")
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"option requires: {', '.join(missing)}",
            )
        try:
            symbol = build_occ_symbol(
                body.underlying, body.expiry, body.strike, body.option_type,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        display_name = format_option_name(symbol)
        current_price = None
    elif is_market:
        if not body.symbol:
            raise HTTPException(
                status_code=400,
                detail=f"symbol is required for security_type='{body.security_type}'",
            )
        symbol = body.symbol.upper().strip()
        display_name = body.name
        current_price = None
    else:
        if not body.name:
            raise HTTPException(
                status_code=400,
                detail=f"name is required for security_type='{body.security_type}'",
            )
        if body.current_value is None:
            raise HTTPException(
                status_code=400,
                detail="current_value is required for non-market assets",
            )
        # Use a synthetic symbol so the unique (account_id, symbol, as_of) index doesn't collide.
        # Prefix with type so it's clear in any direct DB inspection.
        symbol = f"{body.security_type.upper()}:{body.name[:30].upper()}"
        display_name = body.name
        # Store per-unit value. For real_estate / vehicle the user typically has qty=1.
        current_price = body.current_value / body.quantity if body.quantity else 0

    existing = (
        db.table("holdings")
        .select("id")
        .eq("user_id", user_id)
        .eq("account_id", account_id)
        .eq("symbol", symbol)
        .eq("as_of", today)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="A holding with this symbol/name already exists today. Use PUT to update.",
        )

    row = {
        "user_id": user_id,
        "account_id": account_id,
        "symbol": symbol,
        "name": display_name,
        "security_type": body.security_type,
        "quantity": body.quantity,
        "cost_basis": body.cost_basis,
        "currency": "USD",
        "as_of": today,
    }
    if current_price is not None:
        row["current_price"] = current_price
        row["current_value"] = current_price * body.quantity

    result = db.table("holdings").insert(row).execute()
    return result.data[0]


@router.put("/{holding_id}")
async def update_holding(
    holding_id: str,
    body: HoldingUpdate,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()

    update: dict = {}
    if body.quantity is not None:
        update["quantity"] = body.quantity
    if body.cost_basis is not None:
        update["cost_basis"] = body.cost_basis
    if body.name is not None:
        update["name"] = body.name
    if body.current_value is not None:
        # Need quantity to derive per-unit price.
        current = (
            db.table("holdings")
            .select("quantity")
            .eq("user_id", user_id)
            .eq("id", holding_id)
            .execute()
        )
        if not current.data:
            raise HTTPException(status_code=404, detail="Holding not found")
        qty = float(update.get("quantity") or current.data[0]["quantity"])
        update["current_price"] = body.current_value / qty if qty else 0
        update["current_value"] = body.current_value

    if not update:
        return {"updated": False}

    result = (
        db.table("holdings")
        .update(update)
        .eq("user_id", user_id)
        .eq("id", holding_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Holding not found")
    return {"updated": True, "holding": result.data[0]}


@router.delete("/{holding_id}")
async def delete_holding(
    holding_id: str,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    db = get_supabase()
    result = (
        db.table("holdings")
        .delete()
        .eq("user_id", user_id)
        .eq("id", holding_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Holding not found")
    return {"deleted": True}
