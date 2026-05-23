from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    accounts,
    auth,
    budgets,
    chat,
    goals,
    ibkr,
    plaid,
    profile,
    trades,
    transactions,
)
from app.config import settings

app = FastAPI(title="Finance Agent API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(budgets.router, prefix="/api/budgets", tags=["budgets"])
app.include_router(goals.router, prefix="/api/goals", tags=["goals"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(plaid.router, prefix="/api/plaid", tags=["plaid"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(ibkr.router, prefix="/api/ibkr", tags=["ibkr"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
