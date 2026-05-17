-- Migration 002 — Advisor expansion
--
-- Generalizes broker_connections → account_connections (Plaid + IBKR + manual),
-- and adds the finance domain: accounts, transactions, holdings, budgets,
-- goals, net worth snapshots, chat conversations + messages.
--
-- Pre-requisite: 001_initial_schema.sql has been applied.

-- ─── Generalize connections (broker_connections → account_connections) ──

alter table public.broker_connections rename to account_connections;

alter table public.account_connections
    drop constraint broker_connections_broker_check;

alter table public.account_connections rename column broker to provider;

alter table public.account_connections
    add constraint account_connections_provider_check
    check (provider in ('ibkr', 'plaid', 'manual'));

-- `account_id` on the old broker table meant "broker-side account number".
-- Plaid uses an `item_id` per Link session that fans out to many account_ids,
-- so rename to `provider_item_id` and let per-account info live in `accounts`.
alter table public.account_connections rename column account_id to provider_item_id;

alter table public.account_connections
    add column institution_name text,
    add column institution_logo_url text;

alter trigger broker_connections_updated_at on public.account_connections
    rename to account_connections_updated_at;

alter index idx_broker_connections_user_id
    rename to idx_account_connections_user_id;

-- Match the new naming on the trades FK column
alter table public.trades rename column broker_connection_id to connection_id;

-- ─── Accounts (provider-agnostic financial accounts) ───────────

create table public.accounts (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    connection_id uuid references public.account_connections(id) on delete cascade,
    provider_account_id text,
    name text not null,
    official_name text,
    mask text,
    type text not null check (type in ('depository', 'credit', 'investment', 'retirement', 'loan', 'other')),
    subtype text,
    currency text not null default 'USD',
    current_balance numeric(20, 4),
    available_balance numeric(20, 4),
    credit_limit numeric(20, 4),
    is_active boolean not null default true,
    is_hidden boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.accounts enable row level security;

create policy "Users can view own accounts"
    on public.accounts for select
    using (auth.uid() = user_id);

create policy "Users can insert own accounts"
    on public.accounts for insert
    with check (auth.uid() = user_id);

create policy "Users can update own accounts"
    on public.accounts for update
    using (auth.uid() = user_id);

create policy "Users can delete own accounts"
    on public.accounts for delete
    using (auth.uid() = user_id);

create index idx_accounts_user_id on public.accounts(user_id);
create index idx_accounts_connection_id on public.accounts(connection_id);
create unique index idx_accounts_provider_unique
    on public.accounts(connection_id, provider_account_id)
    where provider_account_id is not null;

create trigger accounts_updated_at before update on public.accounts
    for each row execute function update_updated_at();

-- ─── Transactions (bank + investment) ──────────────────────────

create table public.transactions (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    account_id uuid not null references public.accounts(id) on delete cascade,
    provider_transaction_id text,
    -- positive = inflow, negative = outflow
    amount numeric(20, 4) not null,
    currency text not null default 'USD',
    transaction_date date not null,
    posted_at timestamptz,
    merchant_name text,
    description text,
    category_primary text,
    category_detailed text,
    is_pending boolean not null default false,
    is_excluded_from_budget boolean not null default false,
    notes text,
    tags text[] not null default '{}',
    raw_data jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.transactions enable row level security;

create policy "Users can view own transactions"
    on public.transactions for select
    using (auth.uid() = user_id);

create policy "Users can insert own transactions"
    on public.transactions for insert
    with check (auth.uid() = user_id);

create policy "Users can update own transactions"
    on public.transactions for update
    using (auth.uid() = user_id);

create policy "Users can delete own transactions"
    on public.transactions for delete
    using (auth.uid() = user_id);

create index idx_transactions_user_id on public.transactions(user_id);
create index idx_transactions_account_id on public.transactions(account_id);
create index idx_transactions_date on public.transactions(transaction_date desc);
create unique index idx_transactions_provider_unique
    on public.transactions(account_id, provider_transaction_id)
    where provider_transaction_id is not null;

create trigger transactions_updated_at before update on public.transactions
    for each row execute function update_updated_at();

-- ─── Holdings (investment positions snapshot) ──────────────────

create table public.holdings (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    account_id uuid not null references public.accounts(id) on delete cascade,
    symbol text not null,
    name text,
    cusip text,
    isin text,
    security_type text check (security_type in ('stock', 'etf', 'mutual_fund', 'bond', 'option', 'crypto', 'cash', 'other')),
    quantity numeric(20, 8) not null,
    cost_basis numeric(20, 6),
    current_price numeric(20, 6),
    current_value numeric(20, 4),
    currency text not null default 'USD',
    -- one row per (account, symbol, day) so we can keep historical snapshots
    as_of date not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.holdings enable row level security;

create policy "Users can view own holdings"
    on public.holdings for select
    using (auth.uid() = user_id);

create policy "Users can insert own holdings"
    on public.holdings for insert
    with check (auth.uid() = user_id);

create policy "Users can update own holdings"
    on public.holdings for update
    using (auth.uid() = user_id);

create policy "Users can delete own holdings"
    on public.holdings for delete
    using (auth.uid() = user_id);

create unique index idx_holdings_unique on public.holdings(account_id, symbol, as_of);
create index idx_holdings_user_id on public.holdings(user_id);
create index idx_holdings_as_of on public.holdings(as_of desc);

create trigger holdings_updated_at before update on public.holdings
    for each row execute function update_updated_at();

-- ─── Budgets ───────────────────────────────────────────────────

create table public.budgets (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    name text not null,
    category text not null,
    amount numeric(20, 4) not null,
    period text not null check (period in ('weekly', 'monthly', 'yearly')),
    start_date date not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.budgets enable row level security;

create policy "Users can view own budgets"
    on public.budgets for select
    using (auth.uid() = user_id);

create policy "Users can insert own budgets"
    on public.budgets for insert
    with check (auth.uid() = user_id);

create policy "Users can update own budgets"
    on public.budgets for update
    using (auth.uid() = user_id);

create policy "Users can delete own budgets"
    on public.budgets for delete
    using (auth.uid() = user_id);

create index idx_budgets_user_id on public.budgets(user_id);

create trigger budgets_updated_at before update on public.budgets
    for each row execute function update_updated_at();

-- ─── Goals ─────────────────────────────────────────────────────

create table public.goals (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    name text not null,
    goal_type text not null check (goal_type in ('savings', 'debt_payoff', 'investment', 'purchase', 'emergency_fund', 'retirement', 'other')),
    target_amount numeric(20, 4) not null,
    current_amount numeric(20, 4) not null default 0,
    target_date date,
    linked_account_id uuid references public.accounts(id) on delete set null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.goals enable row level security;

create policy "Users can view own goals"
    on public.goals for select
    using (auth.uid() = user_id);

create policy "Users can insert own goals"
    on public.goals for insert
    with check (auth.uid() = user_id);

create policy "Users can update own goals"
    on public.goals for update
    using (auth.uid() = user_id);

create policy "Users can delete own goals"
    on public.goals for delete
    using (auth.uid() = user_id);

create index idx_goals_user_id on public.goals(user_id);

create trigger goals_updated_at before update on public.goals
    for each row execute function update_updated_at();

-- ─── Net worth snapshots (daily) ───────────────────────────────

create table public.net_worth_snapshots (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    snapshot_date date not null,
    assets_total numeric(20, 4) not null,
    liabilities_total numeric(20, 4) not null default 0,
    net_worth numeric(20, 4) not null,
    breakdown jsonb,
    created_at timestamptz not null default now()
);

alter table public.net_worth_snapshots enable row level security;

create policy "Users can view own snapshots"
    on public.net_worth_snapshots for select
    using (auth.uid() = user_id);

create policy "Users can insert own snapshots"
    on public.net_worth_snapshots for insert
    with check (auth.uid() = user_id);

create policy "Users can update own snapshots"
    on public.net_worth_snapshots for update
    using (auth.uid() = user_id);

create policy "Users can delete own snapshots"
    on public.net_worth_snapshots for delete
    using (auth.uid() = user_id);

create unique index idx_net_worth_snapshots_unique
    on public.net_worth_snapshots(user_id, snapshot_date);
create index idx_net_worth_snapshots_date
    on public.net_worth_snapshots(snapshot_date desc);

-- ─── Chat conversations + messages ─────────────────────────────

create table public.chat_conversations (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    title text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.chat_conversations enable row level security;

create policy "Users can view own conversations"
    on public.chat_conversations for select
    using (auth.uid() = user_id);

create policy "Users can insert own conversations"
    on public.chat_conversations for insert
    with check (auth.uid() = user_id);

create policy "Users can update own conversations"
    on public.chat_conversations for update
    using (auth.uid() = user_id);

create policy "Users can delete own conversations"
    on public.chat_conversations for delete
    using (auth.uid() = user_id);

create index idx_chat_conversations_user_id
    on public.chat_conversations(user_id, updated_at desc);

create trigger chat_conversations_updated_at before update on public.chat_conversations
    for each row execute function update_updated_at();

create table public.chat_messages (
    id uuid primary key default uuid_generate_v4(),
    conversation_id uuid not null references public.chat_conversations(id) on delete cascade,
    user_id uuid not null references public.profiles(id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'tool', 'system')),
    content text,
    tool_calls jsonb,
    tool_call_id text,
    model text,
    input_tokens integer,
    output_tokens integer,
    cached_tokens integer,
    created_at timestamptz not null default now()
);

alter table public.chat_messages enable row level security;

create policy "Users can view own messages"
    on public.chat_messages for select
    using (auth.uid() = user_id);

create policy "Users can insert own messages"
    on public.chat_messages for insert
    with check (auth.uid() = user_id);

create policy "Users can delete own messages"
    on public.chat_messages for delete
    using (auth.uid() = user_id);

create index idx_chat_messages_conversation
    on public.chat_messages(conversation_id, created_at);

-- ─── Link trades to accounts (optional) ────────────────────────

alter table public.trades
    add column account_id uuid references public.accounts(id) on delete set null;

create index idx_trades_account_id on public.trades(account_id);
