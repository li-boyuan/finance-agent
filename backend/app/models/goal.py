from datetime import date, datetime
from pydantic import BaseModel


class Goal(BaseModel):
    id: str
    user_id: str
    name: str
    goal_type: str
    target_amount: float
    current_amount: float
    target_date: date | None
    linked_account_id: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
