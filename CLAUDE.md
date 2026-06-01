# Finance Agent — Claude Context

Personal finance advisor app (chat + portfolio dashboard) built for the owner's own use, not multi-tenant SaaS. Stack: Next.js 14 (frontend) + FastAPI (backend) + Supabase (Postgres + auth) + Anthropic Claude (chat with tool use) + Yahoo Finance quotes.

## What's shipped

- **Auth + chat**: streaming chat with Claude Sonnet 4.6, conversation persistence, free-form "About you" context panel, SSE pipeline with markdown rendering.
- **Portfolio dashboard** at `/dashboard/portfolio`: live quotes (5-min cache), allocation donut, per-position table, stocks/ETFs/crypto/options/real estate/vehicles/other.
- **Chat tool use**: Claude can call `get_portfolio_summary` and `list_holdings` to reason over real positions during chat. UI shows tool-call pills.
- **IBKR live sync** via self-hosted Client Portal Gateway: `/dashboard/holdings` has a "Connect IBKR" panel; sync pulls positions and replaces the IBKR account's holdings (full-replace strategy, not incremental).
- **Options support**: full OCC symbol round-trip, long + short with correct P&L math, grouped under their underlying ticker on both the portfolio dashboard and the holdings manager.

## Architecture quick map

- `backend/app/services/portfolio.py` — single source of truth for portfolio rollup. All UIs and chat tools route through `compute_portfolio_summary`. Don't duplicate enrichment logic anywhere else.
- `backend/app/services/chat.py` — Anthropic streaming + tool-use loop (max 5 iterations).
- `backend/app/services/chat_tools.py` — tool definitions + executor. Add new tools here.
- `backend/app/services/ibkr.py` — strategy factory (`build_client_for_connection`). Gateway implemented; OAuth 1.0a left as an explicit `NotImplementedError` seam.
- `backend/app/services/ibkr_positions.py` — maps IBKR positions to `holdings` rows. Options are parsed out of `contractDesc`'s bracketed OCC suffix (IBKR doesn't populate structured strike/expiry on the gateway).
- `backend/app/services/options.py` — OCC build/parse + `CONTRACT_MULTIPLIER = 100`.
- `frontend/components/portfolio/` — shared grouped-by-underlying table (`GroupedHoldingsTable.tsx`, optional `onDelete` adds an actions column) + grouping helpers/types (`grouping.ts`). One implementation, used by both dashboards.
- `frontend/app/dashboard/portfolio/page.tsx` — portfolio dashboard: donut + shared grouped table (read-only).
- `frontend/app/dashboard/holdings/page.tsx` — holdings manager: add form + IBKR panel + the shared grouped table with a Delete column. Reads the enriched `/api/portfolio/summary` (not raw `/api/holdings/`).
- `frontend/app/dashboard/holdings/IBKRConnect.tsx` — connect + sync UI.
- `supabase/migrations/` — apply in order. Latest: `005_account_auth_config.sql` (jsonb auth config on `account_connections`).

## Working conventions

- **Small, focused commits** with detailed bodies. Each logical change is its own commit; don't bundle a refactor with a feature.
- **No comments unless WHY is non-obvious.** Skip "this does X" comments. Keep "this avoids issue Y" comments.
- **No backward-compat shims** for code only the owner runs. Just change it and update the README.
- **Don't add features the task didn't ask for.** A bug fix doesn't need surrounding cleanup.
- **Trust internal code.** No defensive try/except, no input validation, except at system boundaries (user input, external APIs like IBKR/Yahoo).
- **Frontend typecheck**: `cd frontend && npx tsc --noEmit` before committing.
- **Backend syntax check**: `python3 -c "import ast; ast.parse(open('path.py').read())"` for quick smoke.

## Local dev

```bash
# Backend (terminal 1)
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend (terminal 2)
cd frontend
npm run dev

# IBKR Gateway (terminal 3, only if syncing IBKR)
cd ~/ibkr-gateway   # wherever clientportal.gw was unzipped
./bin/run.sh root/conf.yaml
# Then https://localhost:5001 (or 5000), log in via browser
```

## Gotchas

- **macOS AirPlay Receiver squats on port 5000.** Either turn off AirPlay Receiver in System Settings, or change `listenPort` in gateway's `root/conf.yaml` (the owner currently runs on 5001).
- **IBKR session expires after ~6 min idle** unless something pings `/tickle`. Sync auto-tickles but if the browser session goes stale, sync will 502 — log in again at `https://localhost:5001`.
- **IBKR gateway returns empty `strike`/`expirationDate`/`putOrCall`** on at least the current version. Real data is in the bracketed suffix of `contractDesc`. `IBKR_BRACKET_OCC_RE` in `ibkr_positions.py` parses it.
- **Don't confuse "IB Gateway" with "Client Portal API Gateway"** — different products, different protocols. We use Client Portal (HTTPS, port 5000).
- **IBKR sync is full-replace** for the IBKR-account holdings. Manual holdings on other accounts are never touched.
- **Short positions** are stored with negative quantity. Percentages use `abs(denominator)` in `portfolio.py` so the sign comes from the numerator and reflects position direction. The manual add/edit form and `HoldingCreate`/`HoldingUpdate` accept negative quantities (no `gt=0` bound) so hand-entered shorts match synced ones.

## Open follow-ups (in rough priority)

1. **Time-series snapshots** — write daily rollup to `net_worth_snapshots` (table already exists in schema) + add a trend chart on `/dashboard/portfolio`. Cron via Supabase or a simple GitHub Action / Vercel cron.
2. **Multi-IBKR-account support** — currently uses `accounts[0]` from the gateway. Real users have margin + IRA + paper.
3. **Plaid integration** for Fidelity + bank spending. Drop into the same `account_connections` table; `auth_config = {"strategy": "plaid", ...}`.
4. **IBKR OAuth 1.0a** — replaces `NotImplementedError` in `services/ibkr.py`. 2-4 week IBKR approval blocker; only worth doing if going SaaS.

## Roadmap status (matches README)

- v1 chat advisor ✅
- v2a portfolio dashboard ✅
- v2b chat tool use ✅
- v2c IBKR live sync ✅
- v2d Plaid ⏳ next
- v3 analytics / time series ⏳
- v4 SaaS polish, v5 power features, v6 tax ⏳
