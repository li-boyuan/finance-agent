from datetime import date, datetime
from pydantic import BaseModel


class NetWorthSnapshot(BaseModel):
    id: str
    user_id: str
    snapshot_date: date
    assets_total: float
    liabilities_total: float
    net_worth: float
    breakdown: dict | None
    created_at: datetime
