# Finance Agent

AI personal finance advisor. Chat with Claude over your real financial situation, link bank and investment accounts (coming), and get plain-language guidance on budgeting, debt, investing, and major money decisions.

> Status: **Phase 1 complete + portfolio dashboard live + chat tool use + IBKR live sync + options analytics shipped.** Public surface (landing, sign-up / sign-in, streaming chat) ships with a cohesive light-themed UI. Portfolio dashboard tracks stocks / ETFs / crypto / **options** (full OCC support, long + short) / real estate / vehicles / other assets — live quotes via Yahoo Finance, manual valuation for non-market assets. The portfolio dashboard rolls holdings up by underlying ticker into collapsible summaries you expand to the individual legs — adjusted options (e.g. `GME1` → `GME`) and related instruments (e.g. a 2× leveraged ETF aliased to its underlying) group under the base ticker; shorts are marked and contribute correctly to P&L math. Claude can read your portfolio in chat (`get_portfolio_summary`, `list_holdings`) with live tool-call indicators. IBKR positions sync via the self-hosted Client Portal Gateway, and an Options page surfaces delta-adjusted exposure (from IBKR model greeks), an expiration calendar, and assignment-risk flags. Fidelity accounts (IRA / Roth / 529 / brokerage) import via Plaid. Next milestone: bank/spending sync + tax-aware analytics.

## Architecture

```
┌─────────────────────────────────────┐
│  Next.js 14 (Vercel)                │
│  - Supabase Auth (email / password) │
│  - Chat UI w/ streaming + markdown  │
│  - Portfolio dashboard + holdings   │
│  - About-you context panel          │
└──────────────┬──────────────────────┘
               │ HTTPS
┌──────────────▼──────────────────────┐
│  FastAPI (Railway)                  │
│  - JWT validation (Supabase)        │
│  - Chat SSE endpoint                │
│  - Holdings CRUD + portfolio rollup │
│  - Yahoo Finance quote cache (5min) │
│  - Plaid / IBKR account sync        │
│  - Audit logging                    │
└──────┬────────────────────┬─────────┘
       │                    │
┌──────▼──────────┐  ┌──────▼─────────┐
│  Supabase (PG)  │  │  Anthropic     │
│  - RLS on all   │  │  - Claude      │
│    user data    │  │    Sonnet 4.6  │
│  - Auth         │  │  - Streaming   │
│  - Fernet-enc.  │  │  - Prompt      │
│    tokens       │  │    caching     │
└─────────────────┘  └────────────────┘
```

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Next.js 14 (App Router) | UI, auth flow, chat experience |
| Backend | FastAPI (Python) | API, chat orchestration, account sync |
| LLM | Anthropic Claude Sonnet 4.6 | Conversational advisor + tool use (v2) |
| Database | Supabase (PostgreSQL) | Data storage, auth, RLS |
| Cache | Upstash Redis | Rate limiting, real-time state |
| Hosting | Vercel + Railway | Frontend + backend |
| Auth | Supabase Auth | Email / password (Clerk a future option) |

## Project Structure

```
finance-agent/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, route registration
│   │   ├── config.py               # Pydantic settings from .env
│   │   ├── db.py                   # Supabase client singleton
│   │   ├── core/
│   │   │   ├── security.py         # Fernet token encryption, JWT verify (HS256 + JWKS)
│   │   │   └── audit.py            # Structured access logging
│   │   ├── api/
│   │   │   ├── deps.py             # Auth dependency (Supabase JWT)
│   │   │   └── routes/
│   │   │       ├── auth.py         # /api/auth/me
│   │   │       ├── profile.py      # /api/profile/  (financial_context CRUD)
│   │   │       ├── accounts.py     # /api/accounts/
│   │   │       ├── transactions.py # /api/transactions/
│   │   │       ├── budgets.py      # /api/budgets/
│   │   │       ├── goals.py        # /api/goals/
│   │   │       ├── chat.py         # /api/chat/  (SSE streaming)
│   │   │       ├── holdings.py     # /api/holdings/  CRUD for stocks/options/assets
│   │   │       ├── portfolio.py    # /api/portfolio/summary  (live quotes + rollup)
│   │   │       ├── options.py      # /api/options/analytics  (delta-adjusted exposure, expirations)
│   │   │       ├── plaid.py        # /api/plaid/  (Fidelity & banks: Link, exchange, holdings sync)
│   │   │       ├── ibkr.py         # /api/ibkr/  (Client Portal Gateway connect + positions sync)
│   │   │       └── trades.py       # /api/trades/  (legacy manual CRUD, kept)
│   │   ├── models/                 # Pydantic models for each resource
│   │   └── services/
│   │       ├── chat.py             # Anthropic streaming client + tool-use loop + system prompt
│   │       ├── chat_tools.py       # Tool definitions (portfolio summary, list holdings) + executor
│   │       ├── portfolio.py        # Portfolio rollup (live quotes + per-position enrichment, LLM views)
│   │       ├── market_data.py      # Yahoo Finance quote fetcher (httpx, 5-min cache)
│   │       ├── options.py          # OCC symbol build/parse + contract multiplier
│   │       ├── options_analytics.py # Delta-adjusted exposure, expiration calendar, risk flags
│   │       ├── ibkr.py             # Client Portal API client + auth-strategy factory (gateway today, OAuth 1.0a future)
│   │       └── ibkr_positions.py   # Map IBKR positions → holdings rows (full-replace sync)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── layout.tsx              # Root layout, metadata
│   │   ├── page.tsx                # Landing
│   │   ├── login/page.tsx          # Sign in / sign up (Supabase)
│   │   └── dashboard/
│   │       ├── layout.tsx          # Shared dashboard shell (top nav + sign out)
│   │       ├── page.tsx            # Redirects → /dashboard/chat
│   │       ├── chat/page.tsx       # ChatGPT-style chat UI + sidebar
│   │       ├── portfolio/page.tsx  # Stats cards + allocation donut + grouped holdings table
│   │       ├── options/page.tsx    # Delta-adjusted exposure, expiration calendar, risk flags
│   │       ├── holdings/page.tsx   # Add form + IBKR panel + grouped holdings table w/ delete
│   │       └── trades/page.tsx     # Legacy trade-journal dashboard
│   ├── components/
│   │   └── portfolio/              # Shared grouped-by-ticker holdings table + grouping helpers (used by portfolio + holdings)
│   ├── lib/
│   │   ├── api.ts                  # Typed fetch helper
│   │   └── supabase/               # Browser + server Supabase clients
│   ├── middleware.ts               # Cookie-presence auth gate on /dashboard/*
│   ├── package.json
│   └── .env.example
├── supabase/migrations/
│   ├── 001_initial_schema.sql      # profiles, broker_connections, trades, audit_log
│   ├── 002_advisor_expansion.sql   # Rename → account_connections + 8 new tables
│   ├── 003_user_context.sql        # profiles.financial_context
│   ├── 004_asset_types.sql         # holdings.security_type adds real_estate / vehicle
│   ├── 005_account_auth_config.sql # account_connections.auth_config (jsonb)
│   ├── 006_holdings_greeks.sql     # holdings.greeks (jsonb) — option delta/gamma/theta/vega
│   └── 007_account_balances.sql    # accounts.balances (jsonb) — margin / buying power
└── docker-compose.yml              # Local Postgres + Redis (dev only)
```

## API Endpoints

### Auth & profile
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/auth/me` | Current user from JWT |
| GET | `/api/profile/` | User profile (auto-creates row on first call) |
| PATCH | `/api/profile/` | Update display_name / financial_context |

### Chat (v1)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chat/conversations` | List conversations, newest first |
| GET | `/api/chat/conversations/{id}/messages` | Messages for one conversation |
| POST | `/api/chat/messages` | Send message — SSE stream of `text` / `done` / `error` events |

### Portfolio (live)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio/summary` | Total value, today change, total return, allocation %, `by_tax_treatment` rollup, enriched per-holding rows (each tagged with account / provider / tax bucket) with live quotes. The donor-advised fund is excluded from net worth. Also records today's net-worth snapshot |
| GET | `/api/portfolio/history` | Net-worth time series (`?days=`), ascending by date |
| POST | `/api/portfolio/snapshot` | Record today's net-worth snapshot (idempotent per day; for a daily cron) |
| GET | `/api/holdings/` | List all holdings (raw, no quotes) |
| POST | `/api/holdings/` | Add a holding. Polymorphic body: stocks/ETFs/crypto use `symbol`; options use `underlying`+`expiry`+`strike`+`option_type`; real estate / vehicle / other use `name`+`current_value`. Quantity may be negative for short positions |
| PUT | `/api/holdings/{id}` | Update quantity / cost basis / current value |
| DELETE | `/api/holdings/{id}` | Remove a holding |

### Options analytics
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/options/analytics` | Per-underlying delta-adjusted exposure + theta/day (from IBKR greeks), portfolio net Δ$ / theta / vega, margin & buying power, an aggressiveness scorecard (margin utilization, leverage, concentration, −10%/+10-IV shock loss), expiration calendar, moneyness, and assignment-risk / near-expiry flags |

### Accounts, transactions, budgets, goals (read-only stubs until Plaid lands)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/accounts/` | List active accounts |
| GET | `/api/accounts/{id}` | Single account |
| GET | `/api/transactions/` | Paginated transactions (filter by account/category) |
| GET | `/api/budgets/` | Active budgets |
| GET | `/api/goals/` | Active goals |

### Plaid (Fidelity & banks)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/plaid/link-token` | Create a Plaid Link token (needs `PLAID_CLIENT_ID`/`PLAID_SECRET`) |
| POST | `/api/plaid/exchange` | Exchange Link's `public_token`, store the connection (token Fernet-encrypted), and sync holdings |
| POST | `/api/plaid/sync` | Re-pull investments holdings; full-replace this item's accounts/holdings |
| GET | `/api/plaid/status` | Connection status (institution, last sync, whether Plaid is configured) |
| DELETE | `/api/plaid/disconnect/{connection_id}` | `item/remove` + drop token; synced holdings retained |

### IBKR (Client Portal Gateway, positions sync)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ibkr/connect` | Body `{base_url, verify_ssl?}` — probe a running gateway and store the connection |
| GET | `/api/ibkr/status` | Connection status + last sync time |
| POST | `/api/ibkr/sync` | Pull live positions and replace IBKR holdings (full snapshot) |
| DELETE | `/api/ibkr/disconnect` | Disconnect (holdings retained until you delete the IBKR account row) |

### Trades (legacy, still functional)
| Method | Path |
|--------|------|
| GET | `/api/trades/` |
| GET | `/api/trades/stats` |
| GET | `/api/trades/{id}` |
| POST | `/api/trades/` |
| PUT | `/api/trades/{id}` |
| PUT | `/api/trades/{id}/close` |
| DELETE | `/api/trades/{id}` |

## Database Schema

| Table | Purpose |
|-------|---------|
| `profiles` | User profile, includes free-form `financial_context` for the chat advisor |
| `account_connections` | OAuth / API tokens (encrypted) for ibkr / plaid / manual sources |
| `accounts` | Provider-agnostic accounts: depository / credit / investment / retirement / loan. `balances` jsonb holds the IBKR account summary (net liquidation, excess liquidity, buying power, maintenance margin, gross position value) captured at sync |
| `transactions` | Bank + investment transactions; positive = inflow |
| `holdings` | Investment + asset positions: stocks, ETFs, crypto, options (OCC symbols), real estate, vehicles. Cost basis + current value, historical snapshots by `as_of` date; `greeks` jsonb (option delta/gamma/theta/vega captured at IBKR sync) |
| `budgets` | Per-category spending limits (weekly / monthly / yearly) |
| `goals` | Savings / debt-payoff / purchase goals with target dates |
| `net_worth_snapshots` | Daily aggregated assets / liabilities / net worth |
| `chat_conversations` | Chat conversation metadata |
| `chat_messages` | Individual chat messages with role, content, tool_calls, token counts |
| `trades` | IBKR trade records (long/short, entry/exit, P&L, tags) |
| `trade_executions` | Individual fills, linked to trades |
| `audit_log` | Every API action logged with user, IP, timestamp |

All user-owned tables enforce row-level security — users can only access their own rows.

## Security

- **JWT validation** — every API request validates the Supabase JWT in `app/api/deps.py`
- **Row-level security** — enforced at the Postgres level on every user-owned table
- **Fernet encryption** — broker / Plaid access tokens encrypted at rest before DB write
- **Read-only IBKR scope** — no order placement
- **Audit logging** — every data access logged with user ID, action, IP, timestamp
- **Cookie-presence middleware** — frontend auth gate uses cookie presence only (server-side `getUser()` call was removed to work around corporate networks that block outbound from Node runtime). Real validation still happens on every backend call.
- **Disclaimers everywhere** — chat UI surfaces "informational guidance, not professional advice." Positioned as a copilot, not a licensed advisor.
- **Secrets in `.env`** — never committed

## Local Development

### Prerequisites

- Node.js 18+
- Python 3.11+
- A [Supabase](https://supabase.com) project
- An [Anthropic](https://console.anthropic.com) API key

### Setup

```bash
# Clone
git clone https://github.com/li-boyuan/finance-agent.git
cd finance-agent

# Frontend
cd frontend
cp .env.example .env.local    # Fill in Supabase keys + NEXT_PUBLIC_API_URL
npm install

# Backend
cd ../backend
cp .env.example .env           # Fill in Supabase keys, Fernet key, Anthropic key
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Database — apply migrations in order via Supabase SQL Editor:
#   1. supabase/migrations/001_initial_schema.sql
#   2. supabase/migrations/002_advisor_expansion.sql
#   3. supabase/migrations/003_user_context.sql
#   4. supabase/migrations/004_asset_types.sql
#   5. supabase/migrations/005_account_auth_config.sql
#   6. supabase/migrations/006_holdings_greeks.sql
#   7. supabase/migrations/007_account_balances.sql

# Generate Fernet key for encrypting broker tokens
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste output as TOKEN_ENCRYPTION_KEY in backend/.env
```

### Run

```bash
# Terminal 1 — Backend
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open `http://localhost:3000`, sign up, you'll land on `/dashboard/chat`. Open the "About you" panel in the sidebar to give the advisor context, then ask anything.

### Connecting IBKR (optional)

To sync live positions from Interactive Brokers, run their **Client Portal Gateway** locally:

1. Download from [interactivebrokers.com/en/trading/ib-api.php](https://www.interactivebrokers.com/en/trading/ib-api.php) — "Client Portal API" → "Gateway".
2. Run `bin/run.sh root/conf.yaml` (requires Java 17+). Default port: `5000`.
3. Open `https://localhost:5000` in a browser, accept the self-signed cert, log in with your IBKR credentials.
4. In the Finance Agent dashboard, `POST /api/ibkr/connect` with `{"base_url": "https://localhost:5000"}`, then trigger `/api/ibkr/sync`. Your positions land in the portfolio dashboard.

The gateway session lasts ~24 hours. After it expires, log in via the browser again and re-sync.

### Environment Variables

**Backend (`backend/.env`)**
| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase secret key (server only) |
| `JWT_SECRET` | Supabase legacy HS256 signing key (ES256 / JWKS also supported) |
| `TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting broker tokens |
| `ANTHROPIC_API_KEY` | Anthropic API key for the chat advisor |
| `IBKR_CLIENT_ID` / `IBKR_CLIENT_SECRET` | Optional, only for IBKR OAuth |
| `PLAID_CLIENT_ID` / `PLAID_SECRET` | Plaid keys for Fidelity / bank import (optional) |
| `PLAID_ENV` | `sandbox` (fake institutions) / `development` / `production` |
| `REDIS_URL` | Upstash / local Redis connection string |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |

**Frontend (`frontend/.env.local`)**
| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase publishable key |
| `NEXT_PUBLIC_API_URL` | Backend API URL (use `http://127.0.0.1:8000` to avoid IPv6 quirks) |

## Roadmap

| Phase | Status | Scope |
|-------|--------|-------|
| **v1 — Chat advisor + public surface** | ✅ Shipped | SSE streaming chat, conversation persistence, free-form "About you" context, markdown rendering, ChatGPT-style UI, SaaS marketing landing, sign-up / sign-in flow — all sharing one light-themed visual language |
| **v2a — Portfolio dashboard** | ✅ Shipped | Holdings CRUD across stocks / ETFs / crypto / **options (OCC + ×100)** / real estate / vehicles / other; Yahoo Finance quote fetcher with 5-min cache; allocation donut (a slice per underlying group by net value), stats cards (Total Value / Today / Total Return / Positions), collapsible group-summary table (expand a ticker to its legs, with animated expand); type-aware add form |
| **v2b — Chat tool use over portfolio** | ✅ Shipped | Claude can call `get_portfolio_summary` and `list_holdings` to reason over real positions, allocation, and returns. Streaming surfaces tool-call status in the chat UI; tool calls persisted on assistant messages |
| **v2c — IBKR live sync (self-hosted gateway)** | ✅ Shipped | Connect to IBKR's Client Portal Gateway, sync live positions into `holdings` with one click. Parses options from `contractDesc` (IBKR doesn't populate structured strike/expiry fields on the gateway), preserves long/short sign so P&L math is correct on credit spreads and naked shorts, and groups stock + related options by underlying ticker on the dashboard (including corporate-action-adjusted roots like `GME1` → `GME`). Designed so OAuth 1.0a can drop in later as a second auth strategy without schema changes |
| **v2d — Plaid integration** | ✅ Shipped (investments) | Plaid Link → exchange → investments-holdings sync for Fidelity (IRA / Roth / 529 / HSA / brokerage); each Plaid account becomes a typed `accounts` row, holdings full-replace per item, access token Fernet-encrypted. **Fidelity exposes balances only via Plaid** (`available_products: ['balance']`, zero positions for these held-away account types), so each account imports as a single balance line under "Other Assets" — per-position stock/option detail would need a Fidelity CSV importer. Banks/spending (transactions) + cash-value insurance (IUL/VUL, manual) still to come |
| **v2e — Options analytics & risk** | ✅ Shipped | `/dashboard/options`: per-underlying delta-adjusted exposure + theta/day from IBKR greeks (`holdings.greeks`); **margin / buying power** + an **aggressiveness scorecard** (margin utilization, leverage, concentration, −10%/+10-IV shock loss, rated 🟢🟡🟠🔴) from the IBKR account summary (`accounts.balances`); expirations as a **timeline**; moneyness + intrinsic/extrinsic and assignment-risk / near-expiry flags. Sync carries greeks forward so a flaky fetch doesn't wipe them |
| **v2f — Net-worth time series** | ✅ Shipped | Daily net-worth snapshots into `net_worth_snapshots` (recorded opportunistically on each dashboard visit, idempotent per day; `POST /api/portfolio/snapshot` for a cron) + a trend chart on `/dashboard/portfolio` |
| **v2g — Tax-treatment breakdown** | ✅ Shipped | Every holding tagged with its account source (`provider`) and a tax bucket (taxable / tax-deferred / tax-free / education / charitable), derived from account subtype + name (e.g. `BrokerageLink` → tax-deferred, `BrokerageLink Roth` → tax-free). A "By tax treatment" card on `/dashboard/portfolio` (stacked bar + per-bucket $/%) and **IBKR / FID source badges** on each row separate taxable IBKR positions from tax-advantaged Fidelity ones. The donor-advised fund is excluded from net worth |
| **v3 — Analytics dashboard** | ⏳ | Spending by category, budget vs actual, weekly AI insight card (net-worth-over-time ✅ done in v2f) |
| **v4 — SaaS polish** | ⏳ | Stripe billing, onboarding wizard, marketing landing, transactional emails (Resend), social login (Clerk?) |
| **v5 — Power features** | ⏳ | Conversation export, copy / regenerate, suggested follow-ups, share read-only links |
| **v6 — Tax intelligence** | ⏳ | Capital gains tracking, tax-loss harvesting suggestions, deduction surface, year-end CSV — positioned as **tax-aware copilot**, not tax advisor |

## Deployment

| Service | Platform | Notes |
|---------|----------|-------|
| Frontend | Vercel | Connect GitHub repo, set env vars |
| Backend | Railway | Deploy from `backend/` directory, set env vars |
| Database | Supabase | Already hosted, run migrations via SQL Editor |
| Redis | Upstash | Create serverless Redis, copy URL to `REDIS_URL` |

## License

Private — all rights reserved.
