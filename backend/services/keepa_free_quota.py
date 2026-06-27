"""
Monthly Keepa lookup allowance for the free (explorer) tier.

Backed by the `keepa_free_usage` table (usage_month, user_id, call_count).
Monthly reset is implicit — rows are keyed by the first day of the month (UTC).

The allowance is counted only against live/stale Keepa fetches; cache hits
are free. Atomic increment is handled by the `increment_keepa_free_usage`
Postgres RPC — race-safe across multiple instances.

All month keys are derived from a single UTC timestamp so the pre-flight
SELECT and the atomic RPC increment always reference the same row, even
when the Railway server and Supabase DB are in different timezones.

Limit (env-configurable):
  KEEPA_FREE_MONTHLY_LOOKUPS — lookups per calendar month (default 5)
"""
import os
import logging
from datetime import datetime, date, timezone
from typing import Optional

from backend.services.supabase_client import get_supabase

log = logging.getLogger("siftly.keepa_free_quota")

FREE_MONTHLY_LOOKUPS = int(os.environ.get("KEEPA_FREE_MONTHLY_LOOKUPS", 5))


class FreeLookupExhaustedError(Exception):
    """Raised when a free-tier user has used their monthly allowance."""
    def __init__(self, used: int, limit: int, resets_on: str):
        self.used      = used
        self.limit     = limit
        self.resets_on = resets_on
        super().__init__(
            f"Free lookup limit reached: {used}/{limit} used this month "
            f"(resets {resets_on})."
        )


def _utc_today() -> date:
    """Return today's date in UTC, regardless of the server's local timezone."""
    return datetime.now(timezone.utc).date()


def _this_month_str() -> str:
    """Return the ISO date for the first day of the current month (UTC)."""
    d = _utc_today()
    return date(d.year, d.month, 1).isoformat()


def _next_month_str() -> str:
    """Return the ISO date for the first day of next month (UTC)."""
    d = _utc_today()
    if d.month == 12:
        return date(d.year + 1, 1, 1).isoformat()
    return date(d.year, d.month + 1, 1).isoformat()


def _read_count(user_id: str, *, month: Optional[str] = None) -> int:
    """Return how many live lookups this user has made for the given UTC month."""
    sb    = get_supabase()
    month = month or _this_month_str()
    r = (
        sb.table("keepa_free_usage")
          .select("call_count")
          .eq("usage_month", month)
          .eq("user_id", user_id)
          .maybe_single()
          .execute()
    )
    return (r.data or {}).get("call_count", 0) if r.data else 0


def check_and_record_free(user_id: str, *, dry_run: bool = False) -> dict:
    """
    Check whether a free-tier user may make a live Keepa lookup.

    dry_run=True  — check only, no increment.
    dry_run=False — check then atomically increment.

    Returns {used, limit, resets_on}.
    Raises FreeLookupExhaustedError when the monthly limit is reached.

    Month keys are derived from a single UTC snapshot so the pre-flight read,
    the RPC increment, and resets_on are all consistent even when the DB
    and server clocks are in different timezones.
    """
    today_utc  = _utc_today()
    this_month = date(today_utc.year, today_utc.month, 1).isoformat()
    resets_on  = (
        date(today_utc.year + 1, 1, 1).isoformat()
        if today_utc.month == 12
        else date(today_utc.year, today_utc.month + 1, 1).isoformat()
    )

    used = _read_count(user_id, month=this_month)

    if used >= FREE_MONTHLY_LOOKUPS:
        raise FreeLookupExhaustedError(used, FREE_MONTHLY_LOOKUPS, resets_on)

    if dry_run:
        return {"used": used, "limit": FREE_MONTHLY_LOOKUPS, "resets_on": resets_on}

    # Atomic upsert — p_month passed explicitly so the DB function uses the
    # same month key as our pre-flight SELECT, not its own CURRENT_DATE.
    result = get_supabase().rpc(
        "increment_keepa_free_usage",
        {"p_user_id": user_id, "p_month": this_month},
    ).execute()

    row      = (result.data or [{}])[0]
    new_used = row.get("call_count", used + 1)

    log.debug("Free lookup recorded: user=%s used=%d/%d", user_id, new_used, FREE_MONTHLY_LOOKUPS)

    return {"used": new_used, "limit": FREE_MONTHLY_LOOKUPS, "resets_on": resets_on}


def get_free_allowance(user_id: str) -> dict:
    """
    Return the current free-tier lookup status for a user.
    Used by GET /api/product/free-allowance.
    """
    today_utc  = _utc_today()
    this_month = date(today_utc.year, today_utc.month, 1).isoformat()
    resets_on  = (
        date(today_utc.year + 1, 1, 1).isoformat()
        if today_utc.month == 12
        else date(today_utc.year, today_utc.month + 1, 1).isoformat()
    )
    used = _read_count(user_id, month=this_month)
    return {
        "used":      used,
        "limit":     FREE_MONTHLY_LOOKUPS,
        "resets_on": resets_on,
    }
