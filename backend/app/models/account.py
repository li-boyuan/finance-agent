from datetime import datetime
from pydantic import BaseModel


class AccountConnection(BaseModel):
    id: str
    user_id: str
    provider: str
    provider_item_id: str | None
    institution_name: str | None
    institution_logo_url: str | None
    status: str
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime


class Account(BaseModel):
    id: str
    user_id: str
    connection_id: str | None
    provider_account_id: str | None
    name: str
    official_name: str | None
    mask: str | None
    type: str
    subtype: str | None
    currency: str
    current_balance: float | None
    available_balance: float | None
    credit_limit: float | None
    is_active: bool
    is_hidden: bool
    created_at: datetime
    updated_at: datetime
