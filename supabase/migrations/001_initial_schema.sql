-- Enable UUID generation
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- ─── Users Profile ─────────────────────────────────────────────
create table public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null,
    display_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "Users can view own profile"
    on public.profiles for select
    using (auth.uid() = id);

create policy "Users can update own profile"
    on public.profiles for update
    using (auth.uid() = id);

-- ─── Broker Connections ────────────────────────────────────────
create table public.broker_connections (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    broker text not null check (broker in ('ibkr', 'fidelity_csv')),
    encrypted_access_token bytea,
    encrypted_refresh_token bytea,
    token_expires_at timestamptz,
    account_id text,
    status text not null default 'active' check (status in ('active', 'disconnected', 'expired')),
    last_sync_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.broker_connections enable row level security;

create policy "Users can view own connections"
    on public.broker_connections for select
    using (auth.uid() = user_id);

create policy "Users can insert own connections"
    on public.broker_connections for insert
    with check (auth.uid() = user_id);

create policy "Users can update own connections"
    on public.broker_connections for update
    using (auth.uid() = user_id);

create policy "Users can delete own connections"
    on public.broker_connections for delete
    using (auth.uid() = user_id);

-- ─── Trades ────────────────────────────────────────────────────
create table public.trades (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    broker_connection_id uuid references public.broker_connections(id) on delete set null,
    symbol text not null,
    side text not null check (side in ('long', 'short')),
    status text not null default 'open' check (status in ('open', 'closed')),
    entry_price numeric(18, 6) not null,
    exit_price numeric(18, 6),
    quantity numeric(18, 6) not null,
    entry_time timestamptz not null,
    exit_time timestamptz,
    pnl numeric(18, 6),
    pnl_percent numeric(10, 4),
    fees numeric(18, 6) default 0,
    notes text,
    tags text[] default '{}',
    setup_type text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.trades enable row level security;

create policy "Users can view own trades"
    on public.trades for select
    using (auth.uid() = user_id);

create policy "Users can insert own trades"
    on public.trades for insert
    with check (auth.uid() = user_id);

create policy "Users can update own trades"
    on public.trades for update
    using (auth.uid() = user_id);

create policy "Users can delete own trades"
    on public.trades for delete
    using (auth.uid() = user_id);

-- ─── Trade Executions (individual fills) ───────────────────────
create table public.trade_executions (
    id uuid primary key default uuid_generate_v4(),
    trade_id uuid not null references public.trades(id) on delete cascade,
    user_id uuid not null references public.profiles(id) on delete cascade,
    execution_id text,
    side text not null check (side in ('buy', 'sell')),
    price numeric(18, 6) not null,
    quantity numeric(18, 6) not null,
    fees numeric(18, 6) default 0,
    executed_at timestamptz not null,
    raw_data jsonb,
    created_at timestamptz not null default now()
);

alter table public.trade_executions enable row level security;

create policy "Users can view own executions"
    on public.trade_executions for select
    using (auth.uid() = user_id);

create policy "Users can insert own executions"
    on public.trade_executions for insert
    with check (auth.uid() = user_id);

-- ─── Audit Log ─────────────────────────────────────────────────
create table public.audit_log (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid references public.profiles(id) on delete set null,
    action text not null,
    resource_type text not null,
    resource_id text,
    ip_address inet,
    metadata jsonb default '{}',
    created_at timestamptz not null default now()
);

alter table public.audit_log enable row level security;

create policy "Users can view own audit logs"
    on public.audit_log for select
    using (auth.uid() = user_id);

-- ─── Indexes ───────────────────────────────────────────────────
create index idx_trades_user_id on public.trades(user_id);
create index idx_trades_symbol on public.trades(symbol);
create index idx_trades_entry_time on public.trades(entry_time);
create index idx_trades_status on public.trades(status);
create index idx_trade_executions_trade_id on public.trade_executions(trade_id);
create index idx_broker_connections_user_id on public.broker_connections(user_id);
create index idx_audit_log_user_id on public.audit_log(user_id);
create index idx_audit_log_created_at on public.audit_log(created_at);

-- ─── Updated-at trigger ────────────────────────────────────────
create or replace function update_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger profiles_updated_at before update on public.profiles
    for each row execute function update_updated_at();

create trigger broker_connections_updated_at before update on public.broker_connections
    for each row execute function update_updated_at();

create trigger trades_updated_at before update on public.trades
    for each row execute function update_updated_at();
