# Finance Agent

AI personal finance advisor. Chat with Claude over your real financial situation, link bank and investment accounts (coming soon), and get plain-language guidance on budgeting, debt, investing, and major decisions.

> Note: README below still describes the original trade-journal scope. Full rewrite pending — the product is pivoting to an AI finance advisor with chat (shipped), Plaid integration, and tax-aware analytics.

## Architecture

```
┌─────────────────────────────────┐
│  Next.js 14 (Vercel)            │
│  - Supabase Auth (email/pass)   │
│  - Dashboard, trade table       │
│  - IBKR OAuth initiation        │
└──────────────┬──────────────────┘
               │ HTTPS
┌──────────────▼──────────────────┐
│  FastAPI (Railway)              │
│  - JWT validation (Supabase)    │
│  - IBKR OAuth token exchange    │
│  - Trade sync + P&L calculation │
│  - Audit logging                │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│  Supabase                       │
│  - PostgreSQL with RLS          │
│  - Auth (email + MFA)           │
│  - Encrypted token storage      │
└─────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Next.js 14 (App Router) | UI, auth flow, dashboard |
| Backend | FastAPI (Python) | API, IBKR integration, trade processing |
| Database | Supabase (PostgreSQL) | Data storage, auth, row-level security |
| Cache | Upstash Redis | Rate limiting, real-time state |
| Hosting | Vercel + Railway | Frontend + backend deployment |

## Project Structure

```
finance-agent/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, route registration
│   │   ├── config.py               # Pydantic settings from .env
│   │   ├── db.py                   # Supabase client singleton
│   │   ├── core/
│   │   │   ├── security.py         # Fernet token encryption, JWT verification
│   │   │   └── audit.py            # Structured access logging
│   │   ├── api/
│   │   │   ├── deps.py             # Auth middleware (Supabase JWT)
│   │   │   └── routes/
│   │   │       ├── auth.py         # GET /api/auth/me
│   │   │       ├── trades.py       # Trade CRUD + stats
│   │   │       └── ibkr.py         # IBKR OAuth + sync
│   │   ├── models/
│   │   │   └── trade.py            # Pydantic models
│   │   └── services/
│   │       ├── ibkr.py             # IBKR API client + OAuth helpers
│   │       └── trade_sync.py       # Trade import, dedup, P&L calc
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── layout.tsx              # Root layout
│   │   ├── page.tsx                # Landing page
│   │   ├── login/page.tsx          # Sign in / sign up
│   │   └── dashboard/page.tsx      # Dashboard with stats + trade table
│   ├── lib/
│   │   ├── api.ts                  # Typed API fetch helper
│   │   └── supabase/
│   │       ├── client.ts           # Browser Supabase client
│   │       └── server.ts           # Server Supabase client
│   ├── middleware.ts               # Auth guard on /dashboard/*
│   ├── package.json
│   └── .env.example
├── supabase/
│   └── migrations/
│       └── 001_initial_schema.sql  # Tables, RLS policies, indexes, triggers
└── docker-compose.yml              # Local Postgres + Redis
```

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/auth/me` | Get current user profile |

### Trades
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/trades/` | List trades (filter by status, symbol) |
| GET | `/api/trades/stats` | Aggregated stats (win rate, P&L, today P&L) |
| GET | `/api/trades/{id}` | Single trade with executions |
| POST | `/api/trades/` | Create trade manually |
| PUT | `/api/trades/{id}` | Update notes, tags, setup type |
| PUT | `/api/trades/{id}/close` | Close trade with exit price (auto P&L) |
| DELETE | `/api/trades/{id}` | Delete trade and its executions |

### IBKR Integration
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/ibkr/auth-url` | Get IBKR OAuth authorization URL |
| POST | `/api/ibkr/callback` | Exchange auth code for tokens, store encrypted |
| GET | `/api/ibkr/status` | Check IBKR connection status |
| POST | `/api/ibkr/sync` | Pull trades from IBKR, dedup, calculate P&L |
| DELETE | `/api/ibkr/disconnect` | Disconnect IBKR, wipe stored tokens |

## Database Schema

- **profiles** — user profile, linked to Supabase Auth
- **broker_connections** — IBKR OAuth tokens (encrypted), connection status
- **trades** — trade records with entry/exit, P&L, tags, setup type
- **trade_executions** — individual fills from IBKR, linked to trades
- **audit_log** — access log for every API action

All tables have row-level security (RLS) — users can only access their own data.

## Security

- **Read-only IBKR scope** — no order placement, caps worst case at data exposure
- **Fernet encryption** — IBKR tokens encrypted at rest before DB write
- **Row-level security** — enforced at the database level on every table
- **JWT validation** — every API request validates Supabase JWT
- **Audit logging** — every data access logged with user ID, action, IP, timestamp
- **Auth middleware** — dashboard routes protected server-side and client-side
- **CORS** — locked to frontend origin only
- **Secrets in .env** — never committed (gitignored)

## Local Development

### Prerequisites

- Node.js 18+
- Python 3.11+
- A [Supabase](https://supabase.com) project

### Setup

```bash
# Clone
git clone https://github.com/li-boyuan/finance-agent.git
cd finance-agent

# Frontend
cd frontend
cp .env.example .env.local    # Fill in Supabase keys
npm install

# Backend
cd ../backend
cp .env.example .env           # Fill in Supabase keys + generate Fernet key
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Database
# Run supabase/migrations/001_initial_schema.sql in Supabase SQL Editor

# Generate Fernet encryption key
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

Open http://localhost:3000 (or 3001 if 3000 is in use).

### Environment Variables

**Backend (`backend/.env`)**
| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase secret key (server only) |
| `JWT_SECRET` | Supabase JWT signing key |
| `TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting IBKR tokens |
| `IBKR_CLIENT_ID` | IBKR OAuth app client ID |
| `IBKR_CLIENT_SECRET` | IBKR OAuth app client secret |
| `REDIS_URL` | Redis connection string |
| `CORS_ORIGINS` | Allowed frontend origins |

**Frontend (`frontend/.env.local`)**
| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase publishable key |
| `NEXT_PUBLIC_API_URL` | Backend API URL |

## Deployment

| Service | Platform | Notes |
|---------|----------|-------|
| Frontend | Vercel | Connect GitHub repo, set env vars |
| Backend | Railway | Deploy from `backend/` directory, set env vars |
| Database | Supabase | Already hosted, run migrations via SQL Editor |
| Redis | Upstash | Create serverless Redis, copy URL to `REDIS_URL` |

## License

Private — all rights reserved.
