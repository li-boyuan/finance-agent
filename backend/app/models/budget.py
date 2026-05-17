from datetime import date, datetime
from pydantic import BaseModel


class Budget(BaseModel):
    id: str
    user_id: str
    name: str
    category: str
    amount: float
    period: str
    start_date: date
    is_active: bool
    created_at: datetime
    updated_at: datetime
