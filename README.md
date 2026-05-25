# Finance Agent

AI personal finance advisor. Chat with Claude over your real financial situation, link bank and investment accounts (coming), and get plain-language guidance on budgeting, debt, investing, and major money decisions.

> Status: **Phase 1 complete.** Public surface (marketing landing, sign-up / sign-in, streaming chat) is live with a cohesive light-themed UI. Chat advisor is grounded in user-provided context. v2 (Plaid + tool use over real account data) is the next milestone.

## Architecture

```
┌─────────────────────────────────────┐
│  Next.js 14 (Vercel)                │
│  - Supabase Auth (email / password) │
│  - Chat UI w/ streaming + markdown  │
│  - About-you context panel          │
└──────────────┬──────────────────────┘
               │ HTTPS
┌──────────────▼──────────────────────┐
│  FastAPI (Railway)                  │
│  - JWT validation (Supabase)        │
│  - Chat SSE endpoint                │
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
│   │   │       ├── plaid.py        # /api/plaid/  (v2 stubs)
│   │   │       ├── ibkr.py         # /api/ibkr/  (OAuth + sync, legacy)
│   │   │       └── trades.py       # /api/trades/  (legacy, kept)
│   │   ├── models/                 # Pydantic models for each resource
│   │   └── services/
│   │       ├── chat.py             # Anthropic streaming client + system prompt
│   │       ├── ibkr.py             # IBKR API client + OAuth
│   │       └── trade_sync.py       # Trade import + P&L calc
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── layout.tsx              # Root layout, metadata
│   │   ├── page.tsx                # Landing
│   │   ├── login/page.tsx          # Sign in / sign up (Supabase)
│   │   └── dashboard/
│   │       ├── page.tsx            # Redirects → /dashboard/chat
│   │       ├── chat/page.tsx       # ChatGPT-style chat UI + sidebar
│   │       └── trades/page.tsx     # Legacy trade-journal dashboard
│   ├── lib/
│   │   ├── api.ts                  # Typed fetch helper
│   │   └── supabase/               # Browser + server Supabase clients
│   ├── middleware.ts               # Cookie-presence auth gate on /dashboard/*
│   ├── package.json
│   └── .env.example
├── supabase/migrations/
│   ├── 001_initial_schema.sql      # profiles, broker_connections, trades, audit_log
│   ├── 002_advisor_expansion.sql   # Rename → account_connections + 8 new tables
│   └── 003_user_context.sql        # profiles.financial_context
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

### Accounts, transactions, budgets, goals (read-only stubs until v2)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/accounts/` | List active accounts |
| GET | `/api/accounts/{id}` | Single account |
| GET | `/api/transactions/` | Paginated transactions (filter by account/category) |
| GET | `/api/budgets/` | Active budgets |
| GET | `/api/goals/` | Active goals |

### Plaid (v2 — currently returns 501)
| Method | Path |
|--------|------|
| POST | `/api/plaid/link-token` |
| POST | `/api/plaid/exchange` |
| POST | `/api/plaid/sync` |
| DELETE | `/api/plaid/disconnect/{connection_id}` |

### IBKR (legacy, still functional)
| Method | Path |
|--------|------|
| GET | `/api/ibkr/auth-url` |
| POST | `/api/ibkr/callback` |
| GET | `/api/ibkr/status` |
| POST | `/api/ibkr/sync` |
| DELETE | `/api/ibkr/disconnect` |

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
| `accounts` | Provider-agnostic accounts: depository / credit / investment / retirement / loan |
| `transactions` | Bank + investment transactions; positive = inflow |
| `holdings` | Investment positions with cost basis + current value (historical snapshots) |
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
| **v2 — Plaid + tool use** | ⏳ Next | Plaid Link for banks / brokerages, transaction & holding sync, Anthropic tool use over real account data |
| **v3 — Analytics dashboard** | ⏳ | Net worth over time, spending by category, budget vs actual, portfolio allocation, weekly AI insight card |
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
