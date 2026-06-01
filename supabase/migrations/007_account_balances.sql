-- Migration 007 — Account balances / margin on accounts
--
-- Store the IBKR account summary (net liquidation, excess liquidity, buying
-- power, margin requirements, gross position value) captured at sync time so the
-- options risk view can show margin utilization and account-relative risk
-- without a live call on every page load. Nullable; only the IBKR account
-- populates it.

alter table public.accounts
    add column if not exists balances jsonb;
