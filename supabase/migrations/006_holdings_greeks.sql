-- Migration 006 — Option greeks on holdings
--
-- Store IBKR model greeks (delta, gamma, theta, vega, iv) captured at sync time
-- so the options-analytics page can compute delta-adjusted exposure without a
-- live market-data call on every page load. Nullable; only option rows from an
-- IBKR sync populate it. Manual holdings and non-options leave it null.

alter table public.holdings
    add column if not exists greeks jsonb;
