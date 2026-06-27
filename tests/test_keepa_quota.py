"""
Tests for backend/services/keepa_quota.py (Supabase-backed durable quota).
All Supabase I/O is mocked — no real DB calls.
Run: python3 -m pytest tests/test_keepa_quota.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

import backend.services.keepa_quota as quota_mod
from backend.services.keepa_quota import (
    check_and_record,
    get_stats,
    QuotaExceededError,
    DAILY_BUILDER,
    DAILY_OPERATOR,
    DAILY_GLOBAL,
)


# ── Mock factory ─────────────────────────────────────────────────────────────

def _mock_sb(user_count=0, global_rows=None, rpc_data=None):
    """
    Build a minimal Supabase mock that handles the two read queries and the RPC.

    Read chain layout (see keepa_quota._read_counts):
      sb.table().select().eq(date)          → eq_chain
      eq_chain.execute()                    → global result (all-rows)
      eq_chain.eq(user_id).maybe_single().execute() → per-user result
    """
    sb    = MagicMock()
    table = MagicMock()
    sb.table.return_value = table

    # Per-user single-row result
    per_user_mock = MagicMock()
    per_user_mock.data = {"call_count": user_count} if user_count > 0 else None

    # Global all-rows result
    rows = global_rows if global_rows is not None else (
        [{"call_count": user_count}] if user_count > 0 else []
    )
    global_mock = MagicMock()
    global_mock.data = rows

    # Chain: .select().eq(date) → eq_chain
    eq_chain = MagicMock()
    eq_chain.execute.return_value = global_mock                           # global path
    eq_chain.eq.return_value.maybe_single.return_value.execute.return_value = per_user_mock  # per-user path

    table.select.return_value.eq.return_value = eq_chain

    # RPC mock (increment_keepa_usage)
    global_sum = sum(r["call_count"] for r in rows)
    default_rpc = {"user_count": user_count + 1, "global_count": global_sum + 1}
    rpc_result = MagicMock()
    rpc_result.data = [rpc_data if rpc_data is not None else default_rpc]
    sb.rpc.return_value.execute.return_value = rpc_result

    # Stats path: .select("user_id, call_count").eq().execute()
    stats_result = MagicMock()
    stats_result.data = rows
    table.select.return_value.eq.return_value.execute.return_value = stats_result

    return sb


def _invalidate_stats_cache():
    quota_mod._stats_cache = None


# ── TestCheckAndRecord ────────────────────────────────────────────────────────

class TestCheckAndRecord:
    def setup_method(self):
        _invalidate_stats_cache()

    def test_first_call_succeeds(self):
        sb = _mock_sb(user_count=0)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            stats = check_and_record("user1", "builder")
        assert stats["user_used"]   == 1
        assert stats["global_used"] == 1

    def test_dry_run_does_not_call_rpc(self):
        sb = _mock_sb(user_count=0)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            check_and_record("user1", "builder", dry_run=True)
        sb.rpc.assert_not_called()

    def test_dry_run_returns_current_counts(self):
        sb = _mock_sb(user_count=5, global_rows=[{"call_count": 5}])
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            stats = check_and_record("user1", "builder", dry_run=True)
        assert stats["user_used"]  == 5
        assert stats["global_used"] == 5

    def test_wet_run_calls_rpc(self):
        sb = _mock_sb(user_count=0)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            check_and_record("user1", "operator")
        sb.rpc.assert_called_once_with(
            "increment_keepa_usage",
            {"p_user_id": "user1", "p_tier": "operator"},
        )

    def test_rpc_return_value_is_used_not_preflight_count(self):
        """The return stat comes from the RPC, not the pre-flight read."""
        # Pre-flight sees 18; RPC reports 20 (another instance incremented first)
        rpc_data = {"user_count": 20, "global_count": 20}
        sb = _mock_sb(user_count=18, global_rows=[{"call_count": 18}], rpc_data=rpc_data)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            stats = check_and_record("user1", "operator")
        assert stats["user_used"]   == 20   # RPC value, not 18+1
        assert stats["global_used"] == 20

    def test_two_concurrent_calls_rpc_is_authoritative(self):
        """
        Simulates race: two callers both pass the pre-flight read at count=18.
        The RPC returns the atomically correct post-increment value.
        Verifies the implementation uses the RPC result, not Python arithmetic.
        """
        # Call 1: RPC says it incremented to 19
        rpc1 = {"user_count": 19, "global_count": 19}
        sb1  = _mock_sb(user_count=18, global_rows=[{"call_count": 18}], rpc_data=rpc1)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb1):
            s1 = check_and_record("user1", "operator")

        # Call 2: RPC says it incremented to 20 (SQL handled the race correctly)
        rpc2 = {"user_count": 20, "global_count": 20}
        sb2  = _mock_sb(user_count=18, global_rows=[{"call_count": 18}], rpc_data=rpc2)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb2):
            s2 = check_and_record("user1", "operator")

        assert s1["user_used"] == 19
        assert s2["user_used"] == 20
        assert s2["user_used"] <= DAILY_OPERATOR   # still within limit


# ── TestPerUserQuota ──────────────────────────────────────────────────────────

class TestPerUserQuota:
    def test_builder_blocked_at_limit(self):
        sb = _mock_sb(user_count=DAILY_BUILDER, global_rows=[{"call_count": DAILY_BUILDER}])
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            with pytest.raises(QuotaExceededError) as exc_info:
                check_and_record("user1", "builder")
        assert "user:user1" in exc_info.value.scope
        assert exc_info.value.used  == DAILY_BUILDER
        assert exc_info.value.limit == DAILY_BUILDER

    def test_operator_higher_limit_than_builder(self):
        assert DAILY_OPERATOR > DAILY_BUILDER

    def test_operator_blocked_at_own_limit(self):
        sb = _mock_sb(user_count=DAILY_OPERATOR, global_rows=[{"call_count": DAILY_OPERATOR}])
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            with pytest.raises(QuotaExceededError) as exc_info:
                check_and_record("op_user", "operator")
        assert "op_user" in exc_info.value.scope

    def test_different_users_have_independent_limits(self):
        """user_b at zero should succeed even if user_a is at limit."""
        # user_b pre-flight: user_count=0
        sb_b = _mock_sb(user_count=0, global_rows=[{"call_count": DAILY_BUILDER}])
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb_b):
            stats = check_and_record("user_b", "builder")
        assert stats["user_used"] == 1

    def test_unknown_tier_defaults_to_builder_limit(self):
        """Unrecognised tier strings default to DAILY_BUILDER."""
        sb = _mock_sb(user_count=DAILY_BUILDER, global_rows=[{"call_count": DAILY_BUILDER}])
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            with pytest.raises(QuotaExceededError):
                check_and_record("user1", "superstar_tier")


# ── TestGlobalQuota ───────────────────────────────────────────────────────────

class TestGlobalQuota:
    def test_global_limit_blocks_all_users(self):
        many_rows = [{"call_count": 50}] * 10   # 500 total = limit
        sb = _mock_sb(user_count=0, global_rows=many_rows)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            with pytest.raises(QuotaExceededError) as exc_info:
                check_and_record("new_user", "operator")
        assert exc_info.value.scope == "global"
        assert exc_info.value.used  == DAILY_GLOBAL

    def test_quota_exception_attributes(self):
        rows = [{"call_count": DAILY_GLOBAL}]
        sb   = _mock_sb(user_count=0, global_rows=rows)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            with pytest.raises(QuotaExceededError) as exc_info:
                check_and_record("user1", "operator")
        err = exc_info.value
        assert err.scope == "global"
        assert err.limit == DAILY_GLOBAL


# ── TestGetStats ──────────────────────────────────────────────────────────────

class TestGetStats:
    def setup_method(self):
        _invalidate_stats_cache()

    def _sb_for_stats(self, rows):
        sb    = MagicMock()
        table = MagicMock()
        sb.table.return_value = table
        result = MagicMock()
        result.data = rows
        table.select.return_value.eq.return_value.execute.return_value = result
        return sb

    def test_stats_structure(self):
        sb = self._sb_for_stats([])
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            stats = get_stats()
        assert "date"               in stats
        assert "global_used"        in stats
        assert "global_limit"       in stats
        assert "tier_limits"        in stats
        assert "unique_users_today" in stats
        assert "top_users"          in stats

    def test_top_users_sorted_descending(self):
        rows = [
            {"user_id": "heavy", "call_count": 15},
            {"user_id": "light", "call_count":  2},
        ]
        sb = self._sb_for_stats(rows)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            top = get_stats()["top_users"]
        assert top[0]["user_id"] == "heavy"
        assert top[0]["calls"]   == 15

    def test_top_users_capped_at_10(self):
        rows = [{"user_id": f"u{i}", "call_count": i} for i in range(15)]
        sb   = self._sb_for_stats(rows)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            assert len(get_stats()["top_users"]) <= 10

    def test_tier_limits_present(self):
        sb = self._sb_for_stats([])
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            limits = get_stats()["tier_limits"]
        assert "builder"  in limits
        assert "operator" in limits

    def test_stats_cache_prevents_second_db_call(self):
        _invalidate_stats_cache()
        sb = self._sb_for_stats([{"user_id": "u1", "call_count": 3}])
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            get_stats()
            get_stats()   # second call should hit cache
        # The select chain's execute should have been called only once
        assert sb.table.call_count == 1

    def test_global_cap_survives_restart(self):
        """
        Demonstrates the key property: global_used is read from Supabase,
        not in-memory state, so it persists across restarts.
        """
        rows = [{"user_id": f"u{i}", "call_count": 50} for i in range(10)]  # 500 total
        sb   = self._sb_for_stats(rows)
        with patch("backend.services.keepa_quota.get_supabase", return_value=sb):
            stats = get_stats()
        assert stats["global_used"] == DAILY_GLOBAL
