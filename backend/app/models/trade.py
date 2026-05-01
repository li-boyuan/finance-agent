from datetime import datetime
from pydantic import BaseModel


class Trade(BaseModel):
    id: str
    user_id: str
    symbol: str
    side: str
    status: str
    entry_price: float
    exit_price: float | None
    quantity: float
    entry_time: datetime
    exit_time: datetime | None
    pnl: float | None
    pnl_percent: float | None
    fees: float
    notes: str | None
    tags: list[str]
    setup_type: str | None
    created_at: datetime
    updated_at: datetime


class TradeExecution(BaseModel):
    id: str
    trade_id: str
    execution_id: str | None
    side: str
    price: float
    quantity: float
    fees: float
    executed_at: datetime
    raw_data: dict | None
