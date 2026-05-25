-- Migration 004 — Asset types
--
-- Expand security_type check on holdings to cover non-market assets
-- (real estate, vehicles), so the portfolio can include the user's
-- whole net worth, not just tradable securities.

alter table public.holdings
    drop constraint if exists holdings_security_type_check;

alter table public.holdings
    add constraint holdings_security_type_check
    check (security_type in (
        'stock', 'etf', 'mutual_fund', 'bond', 'option',
        'crypto', 'cash', 'real_estate', 'vehicle', 'other'
    ));
