import logging

from app.db import get_supabase
from app.services.portfolio import (
    compute_portfolio_summary,
    holdings_for_llm,
    summarize_for_llm,
)

logger = logging.getLogger("chat.tools")

# Friendly labels surfaced in the UI while a tool runs.
TOOL_LABELS: dict[str, str] = {
    "get_portfolio_summary": "Looking up your portfolio…",
    "list_holdings": "Loading your holdings…",
}

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "get_portfolio_summary",
        "description": (
            "Get a high-level snapshot of the user's investment portfolio: "
            "total value, total cost basis, total return (absolute and %), "
            "today's change, allocation broken down by security type "
            "(stock, etf, crypto, option, real_estate, vehicle, other), "
            "and the top 10 holdings by current value. Use this whenever the "
            "user asks how their portfolio is doing, how much they're up or "
            "down, what their biggest positions are, or what their allocation "
            "looks like. Prefer this over list_holdings when the question is "
            "about totals or top positions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_holdings",
        "description": (
            "Return every position the user holds with full detail: symbol, "
            "name, security type, quantity, cost basis, current price, "
            "current value, total return, today's change, and allocation %. "
            "Use this when the user asks about specific positions, a security "
            "type that may not be in the top 10 (e.g. \"how's my crypto?\"), "
            "or anything that needs the full list. For high-level totals "
            "prefer get_portfolio_summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


async def execute_tool(user_id: str, tool_name: str, tool_input: dict) -> dict:
    """Run a tool and return its JSON-serializable result. Errors are returned
    as {'error': str} so the model can react gracefully."""
    db = get_supabase()
    try:
        if tool_name == "get_portfolio_summary":
            summary = await compute_portfolio_summary(db, user_id)
            return summarize_for_llm(summary)
        if tool_name == "list_holdings":
            summary = await compute_portfolio_summary(db, user_id)
            return holdings_for_llm(summary)
        return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logger.exception("Tool %s failed", tool_name)
        return {"error": f"Tool {tool_name} failed: {e}"}
