"""
Per-user and global daily Keepa call quotas — durable in Supabase.

Backed by the `keepa_usage` table (usage_date, user_id, tier, call_count).
Daily reset is implicit: rows are keyed by usage_date, so a new calendar day
produces new rows. No in-memory rollover logic needed.

Increment path uses the `increment_keepa_usage` Postgres RPC so the counter
update is a single atomic SQL upsert — race-safe across multiple server
instances and survives restarts/redeploys.

Limits (configurable via env):
  KEEPA_DAILY_GLOBAL   — total live calls allowed per calendar day (default 500)
  KEEPA_DAILY_BUILDER  — per-user limit for builder tier              (default 20)
  KEEPA_DAILY_OPERATOR — per-user limit for operator tier             (default 50)

Cache hits (source="cache") must NOT be counted — only live/stale Keepa API
calls consume quota. Callers must pass dry_run=True for pre-flight checks and
False only when they've confirmed a live/stale fetch is about to happen.
"""
import os
import time
import logging
from datetime import date
from typing import Optional, Tuple

from backend.services.supabase_client import get_supabase

log = logging.getLogger("siftly.keepa_quota")

# ── Configurable limits ───────────────────────────────────────────────────────

DAILY_GLOBAL   = int(os.environ.get("KEEPA_DAILY_GLOBAL",   500))
DAILY_BUILDER  = int(os.environ.get("KEEPA_DAILY_BUILDER",   20))
DAILY_OPERATOR = int(os.environ.get("KEEPA_DAILY_OPERATOR",  50))

_TIER_LIMITS = {
    "builder":  DAILY_BUILDER,
    "operator": DAILY_OPERATOR,
}

# ── Stats read-cache (≤60 s TTL, read path only) ─────────────────────────────
# Never cache check_and_record — only the dashboard stats endpoint.

_stats_cache: Optional[Tuple[float, dict]] = None
_STATS_TTL = 60.0


# ── Errors ────────────────────────────────────────────────────────────────────

class QuotaExceededError(Exception):
    """Raised when a per-user or global daily quota is exhausted."""
    def __init__(self, scope: str, used: int, limit: int):
        self.scope = scope   # "global" | "user:{user_id}"
        self.used  = used
        self.limit = limit
        super().__init__(
            f"Keepa quota exceeded ({scope}): {used}/{limit} calls today."
        )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _today_str() -> str:
    return date.today().isoformat()


def _read_counts(user_id: str) -> Tuple[int, int]:
    """
    Return (user_used_today, global_used_today) via two Supabase queries.

    Per-user: single row lookup by (usage_date, user_id).
    Global: sum all call_count values for today — one aggregate read.
    Two queries is intentional; a single RPC for reads adds complexity with
    no latency benefit given the pre-flight path is not on the hot path.
    """
    sb    = get_supabase()
    today = _today_str()

    # Per-user count
    r = (
        sb.table("keepa_usage")
          .select("call_count")
          .eq("usage_date", today)
          .eq("user_id", user_id)
          .maybe_single()
          .execute()
    )
    user_used = (r.data or {}).get("call_count", 0) if r.data else 0

    # Global sum — fetch all of today's rows, sum in Python
    g = (
        sb.table("keepa_usage")
          .select("call_count")
          .eq("usage_date", today)
          .execute()
    )
    global_used = sum(row["call_count"] for row in (g.data or []))

    return user_used, global_used


# ── Public API ────────────────────────────────────────────────────────────────

def check_and_record(user_id: str, tier: str, *, dry_run: bool = False) -> dict:
    """
    Check whether this user+tier may make a live Keepa call; optionally record it.

    dry_run=True  — read and check only (used by the endpoint pre-flight).
                    Never writes to the database.
    dry_run=False — read, check, then atomically increment via SQL RPC.
                    The RPC's returned counts are used in the response, not the
                    pre-flight read, so the value is accurate under concurrent load.

    Returns a dict: {user_used, user_limit, global_used, global_limit}.
    Raises QuotaExceededError if either the per-user or global limit is hit.
    """
    tier_limit = _TIER_LIMITS.get(tier, DAILY_BUILDER)

    # ── Pre-flight read (always) ───────────────────────────────────────────────
    user_used, global_used = _read_counts(user_id)

    if global_used >= DAILY_GLOBAL:
        raise QuotaExceededError("global", global_used, DAILY_GLOBAL)
    if user_used >= tier_limit:
        raise QuotaExceededError(f"user:{user_id}", user_used, tier_limit)

    if dry_run:
        return {
            "user_used":    user_used,
            "user_limit":   tier_limit,
            "global_used":  global_used,
            "global_limit": DAILY_GLOBAL,
        }

    # ── Atomic increment via Postgres RPC ─────────────────────────────────────
    # The upsert is SQL-side so concurrent instances can't double-count.
    result = get_supabase().rpc(
        "increment_keepa_usage",
        {"p_user_id": user_id, "p_tier": tier},
    ).execute()

    row            = (result.data or [{}])[0]
    new_user_used  = row.get("user_count",   user_used + 1)
    new_global_used = row.get("global_count", global_used + 1)

    # Log overshoots — these happen only under a race between instances.
    # They cannot be prevented at the Python layer without a distributed lock;
    # the SQL upsert already provides the strongest guarantee we can make.
    if new_user_used > tier_limit:
        log.warning(
            "User quota overshot (concurrent race): user=%s %d > %d",
            user_id, new_user_used, tier_limit,
        )
    if new_global_used > DAILY_GLOBAL:
        log.warning(
            "Global quota overshot (concurrent race): %d > %d",
            new_global_used, DAILY_GLOBAL,
        )

    log.debug(
        "Keepa call recorded: user=%s tier=%s used=%d/%d global=%d/%d",
        user_id, tier, new_user_used, tier_limit, new_global_used, DAILY_GLOBAL,
    )

    return {
        "user_used":    new_user_used,
        "user_limit":   tier_limit,
        "global_used":  new_global_used,
        "global_limit": DAILY_GLOBAL,
    }


def get_stats() -> dict:
    """
    Return today's quota counters for the /api/metrics/keepa endpoint.

    Cached for up to 60 seconds — the metrics endpoint is informational and
    does not need per-request accuracy.
    """
    global _stats_cache
    now = time.monotonic()

    if _stats_cache is not None:
        ts, data = _stats_cache
        if now - ts < _STATS_TTL:
            return data

    sb    = get_supabase()
    today = _today_str()

    rows = (
        sb.table("keepa_usage")
          .select("user_id, call_count")
          .eq("usage_date", today)
          .execute()
    ).data or []

    global_used = sum(r["call_count"] for r in rows)
    top_users   = sorted(
        [{"user_id": r["user_id"], "calls": r["call_count"]} for r in rows],
        key=lambda x: x["calls"],
        reverse=True,
    )[:10]

    data = {
        "date":               today,
        "global_used":        global_used,
        "global_limit":       DAILY_GLOBAL,
        "tier_limits":        {"builder": DAILY_BUILDER, "operator": DAILY_OPERATOR},
        "unique_users_today": len(rows),
        "top_users":          top_users,
    }
    _stats_cache = (now, data)
    return data
