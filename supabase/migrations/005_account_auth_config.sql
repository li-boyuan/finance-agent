-- Migration 005 — Generic auth config on account_connections
--
-- The old broker-OAuth columns (encrypted_access_token, encrypted_refresh_token,
-- token_expires_at) assume an OAuth2 bearer-token flow. IBKR's reality is
-- different: self-hosted Client Portal Gateway uses session cookies against a
-- user-supplied base URL, and the production path is OAuth 1.0a with RSA
-- signing. Plaid will have yet another shape (item_id + access_token).
--
-- `auth_config` is a per-connection JSON blob carrying everything an auth
-- strategy needs. Examples:
--   gateway:  {"strategy": "gateway", "base_url": "https://localhost:5000",
--             "verify_ssl": false}
--   plaid:    {"strategy": "plaid"}            -- tokens stay in encrypted_* cols
--   oauth1a:  {"strategy": "oauth1a", "consumer_key": "..."}
--
-- Old columns are kept; they remain the right home for opaque secrets.

alter table public.account_connections
    add column if not exists auth_config jsonb not null default '{}'::jsonb;
