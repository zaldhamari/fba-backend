-- Migration 0001: add increment_keepa_free_usage(text, date) overload
--
-- WHY
-- The original function (p_user_id text) uses CURRENT_DATE (Supabase DB
-- timezone) to derive the month row, while the Python caller uses
-- datetime.now(timezone.utc).date() (Railway server UTC) for the pre-flight
-- SELECT.  Near UTC midnight on a month boundary the two clocks can disagree,
-- causing the pre-flight check to read month N while the increment lands in
-- month N+1 — giving an unintended free extra lookup.
--
-- FIX
-- The new two-arg overload accepts p_month explicitly from the caller.
-- Python now derives both the SELECT key and the RPC p_month from a single
-- datetime.now(timezone.utc) call, so pre-flight read and atomic increment
-- always reference the same row.
--
-- OVERLOAD NOTE
-- PostgreSQL identifies functions by (name + argument types).  Adding a second
-- argument list creates a NEW overload — it does NOT replace the existing
-- increment_keepa_free_usage(text).  Both signatures co-exist after this
-- migration, which is intentional: the old backend still works during rollout.
-- The old signature is removed in migration 0002, applied only after the new
-- backend is fully deployed.
--
-- DEPLOY ORDER (mandatory)
--   1. Apply THIS migration (0001) to Supabase FIRST, before deploying backend.
--   2. Deploy the new Python backend (passes p_month in the RPC call).
--   3. Verify the new backend is healthy in production.
--   4. Apply migration 0002 to drop the now-unused old signature.
--
-- HOW TO APPLY
--   Option A — Supabase dashboard: Database → SQL Editor → paste and run.
--   Option B — psql: psql "$DATABASE_URL" -f migrations/0001_increment_keepa_free_usage_explicit_month.sql
--   Safe to re-run (CREATE OR REPLACE on the new signature is idempotent).

CREATE OR REPLACE FUNCTION increment_keepa_free_usage(
  p_user_id  text,   -- matches keepa_free_usage.user_id (type: text)
  p_month    date    -- first day of the UTC month, e.g. '2026-06-01'; supplied
                     -- by the caller so DB never derives it from CURRENT_DATE
)
RETURNS TABLE(call_count integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  INSERT INTO keepa_free_usage (usage_month, user_id, call_count)
  VALUES (p_month, p_user_id, 1)
  ON CONFLICT (usage_month, user_id)
  DO UPDATE SET call_count = keepa_free_usage.call_count + 1
  RETURNING keepa_free_usage.call_count;
END;
$$;

-- Mirror the grants the existing (text) overload carries.
-- Confirmed from pg_proc / aclexplode on 2026-06-08:
--   postgres, anon, authenticated, service_role all have EXECUTE.
GRANT EXECUTE ON FUNCTION increment_keepa_free_usage(text, date) TO postgres;
GRANT EXECUTE ON FUNCTION increment_keepa_free_usage(text, date) TO anon;
GRANT EXECUTE ON FUNCTION increment_keepa_free_usage(text, date) TO authenticated;
GRANT EXECUTE ON FUNCTION increment_keepa_free_usage(text, date) TO service_role;
