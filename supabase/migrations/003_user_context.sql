-- Migration 003 — User financial context
--
-- Adds a free-form text column on profiles where the user can describe
-- their financial situation in plain language. The chat advisor pulls
-- this into its system prompt so it can give personalized answers
-- without needing live account data.
--
-- Pre-requisite: 002_advisor_expansion.sql has been applied.

alter table public.profiles
    add column financial_context text;
