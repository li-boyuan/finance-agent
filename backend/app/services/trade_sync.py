from app.services.ibkr import IBKRClient


async def sync_trades_from_ibkr(
    client: IBKRClient,
    account_id: str,
    user_id: str,
) -> dict:
    raw_trades = await client.get_trades(account_id)

    new_count = 0
    for raw in raw_trades:
        # TODO: check if execution already exists (dedup by execution_id)
        # TODO: upsert into trade_executions
        # TODO: group executions into trades (by symbol + time window)
        new_count += 1

    return {"synced": len(raw_trades), "new_trades": new_count}
