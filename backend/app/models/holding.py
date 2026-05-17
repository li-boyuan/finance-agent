from datetime import date, datetime
from pydantic import BaseModel


class Holding(BaseModel):
    id: str
    user_id: str
    account_id: str
    symbol: str
    name: str | None
    cusip: str | None
    isin: str | None
    security_type: str | None
    quantity: float
    cost_basis: float | None
    current_price: float | None
    current_value: float | None
    currency: str
    as_of: date
    created_at: datetime
    updated_at: datetime
