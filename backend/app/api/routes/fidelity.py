import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db import get_supabase
from app.services.fidelity_csv import import_fidelity_csv

router = APIRouter()
logger = logging.getLogger("fidelity.route")


class FidelityImportRequest(BaseModel):
    csv: str
    commit: bool = False


@router.post("/import")
async def import_positions(
    body: FidelityImportRequest,
    user: dict = Depends(get_current_user),
):
    """Import a Fidelity 'Portfolio Positions' CSV. commit=False previews the
    matched/skipped breakdown without writing; commit=True full-replaces the
    matched accounts' holdings."""
    if not body.csv.strip():
        raise HTTPException(status_code=400, detail="Empty CSV.")
    db = get_supabase()
    try:
        return import_fidelity_csv(db, user["sub"], body.csv, commit=body.commit)
    except Exception as e:
        logger.exception("Fidelity import failed")
        raise HTTPException(status_code=400, detail=f"Could not parse Fidelity CSV: {e}")
