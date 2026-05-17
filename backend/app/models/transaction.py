from datetime import date, datetime
from pydantic import BaseModel


class Transaction(BaseModel):
    id: str
    user_id: str
    account_id: str
    provider_transaction_id: str | None
    amount: float
    currency: str
    transaction_date: date
    posted_at: datetime | None
    merchant_name: str | None
    description: str | None
    category_primary: str | None
    category_detailed: str | None
    is_pending: bool
    is_excluded_from_budget: bool
    notes: str | None
    tags: list[str]
    raw_data: dict | None
    created_at: datetime
    updated_at: datetime
