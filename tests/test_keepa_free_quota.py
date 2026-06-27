"""
Tests for backend/services/keepa_free_quota.py (Prompt 3).
All Supabase I/O is mocked — no real DB calls.
Run: python3 -m pytest tests/test_keepa_free_quota.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

import backend.services.keepa_free_quota as free_quota_mod
from backend.services.keepa_free_quota import (
    check_and_record_free,
    get_free_allowance,
    FreeLookupExhaustedError,
    FREE_MONTHLY_LOOKUPS,
    _this_month_str,
    _next_month_str,
)


# ── Mock factory ───────────────────────────────────────────────────────────────

def _mock_sb(current_count=0, rpc_count=None):
    """
    Build a Supabase mock for keepa_free_quota.

    Read chain:
      sb.table("keepa_free_usage").select("call_count")
        .eq("usage_month", month).eq("user_id", uid)
        .maybe_single().execute()  → per-user row

    Write chain:
      sb.rpc("increment_keepa_free_usage", {p_user_id}).execute()
        → [{call_count: N}]
    """
    sb    = MagicMock()
    table = MagicMock()
    sb.table.return_value = table

    row_data = {"call_count": current_count} if current_count > 0 else None
    read_result = MagicMock()
    read_result.data = row_data

    table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = read_result

    rpc_row = {"call_count": rpc_count if rpc_count is not None else current_count + 1}
    rpc_result = MagicMock()
    rpc_result.data = [rpc_row]
    sb.rpc.return_value.execute.return_value = rpc_result

    return sb


# ── TestMonthHelpers ──────────────────────────────────────────────────────────

class TestMonthHelpers:

    def test_this_month_str_is_first_day(self):
        month_str = _this_month_str()
        assert month_str.endswith("-01"), f"Expected first-of-month, got {month_str!r}"

    def test_next_month_str_is_first_day(self):
        month_str = _next_month_str()
        assert month_str.endswith("-01"), f"Expected first-of-month, got {month_str!r}"

    def test_next_month_after_this_month(self):
        this = _this_month_str()
        next_ = _next_month_str()
        assert next_ > this

    def test_december_wraps_to_january(self):
        from datetime import date as _date
        with patch("backend.services.keepa_free_quota._utc_today", return_value=_date(2025, 12, 15)):
            result = _next_month_str()
        assert result == "2026-01-01"


# ── TestCheckAndRecordFree ────────────────────────────────────────────────────

class TestCheckAndRecordFree:

    def test_first_lookup_succeeds(self):
        sb = _mock_sb(current_count=0)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            result = check_and_record_free("user_free_1")
        assert result["used"]  == 1
        assert result["limit"] == FREE_MONTHLY_LOOKUPS

    def test_returns_resets_on_field(self):
        sb = _mock_sb(current_count=0)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            result = check_and_record_free("user_free_1")
        assert "resets_on" in result
        assert result["resets_on"] == _next_month_str()

    def test_calls_rpc_on_wet_run(self):
        sb = _mock_sb(current_count=0)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            check_and_record_free("user_free_1")
        expected_month = _this_month_str()
        sb.rpc.assert_called_once_with(
            "increment_keepa_free_usage",
            {"p_user_id": "user_free_1", "p_month": expected_month},
        )

    def test_dry_run_does_not_call_rpc(self):
        sb = _mock_sb(current_count=2)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            result = check_and_record_free("user_free_1", dry_run=True)
        sb.rpc.assert_not_called()
        assert result["used"] == 2

    def test_dry_run_at_limit_raises(self):
        sb = _mock_sb(current_count=FREE_MONTHLY_LOOKUPS)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            with pytest.raises(FreeLookupExhaustedError):
                check_and_record_free("user_free_1", dry_run=True)

    def test_under_cap_succeeds(self):
        for count in range(FREE_MONTHLY_LOOKUPS):
            sb = _mock_sb(current_count=count, rpc_count=count + 1)
            with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
                result = check_and_record_free(f"user_{count}")
            assert result["used"] == count + 1

    def test_at_cap_raises_exhausted_error(self):
        sb = _mock_sb(current_count=FREE_MONTHLY_LOOKUPS)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            with pytest.raises(FreeLookupExhaustedError) as exc_info:
                check_and_record_free("user_free_1")
        err = exc_info.value
        assert err.used  == FREE_MONTHLY_LOOKUPS
        assert err.limit == FREE_MONTHLY_LOOKUPS
        assert err.resets_on == _next_month_str()

    def test_over_cap_also_raises(self):
        sb = _mock_sb(current_count=FREE_MONTHLY_LOOKUPS + 3)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            with pytest.raises(FreeLookupExhaustedError):
                check_and_record_free("user_free_1")

    def test_exhausted_error_has_string_representation(self):
        sb = _mock_sb(current_count=FREE_MONTHLY_LOOKUPS)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            with pytest.raises(FreeLookupExhaustedError) as exc_info:
                check_and_record_free("user_free_1")
        assert str(exc_info.value)  # non-empty

    def test_different_users_have_independent_limits(self):
        """user_b at 0 should succeed even if user_a is exhausted."""
        sb_b = _mock_sb(current_count=0, rpc_count=1)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb_b):
            result = check_and_record_free("user_b")
        assert result["used"] == 1


# ── TestGetFreeAllowance ──────────────────────────────────────────────────────

class TestGetFreeAllowance:

    def test_allowance_shape(self):
        sb = _mock_sb(current_count=2)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            result = get_free_allowance("user_free_1")
        assert "used"      in result
        assert "limit"     in result
        assert "resets_on" in result

    def test_allowance_used_matches_db(self):
        sb = _mock_sb(current_count=3)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            result = get_free_allowance("user_free_1")
        assert result["used"]  == 3
        assert result["limit"] == FREE_MONTHLY_LOOKUPS

    def test_allowance_at_zero(self):
        sb = _mock_sb(current_count=0)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            result = get_free_allowance("new_user")
        assert result["used"] == 0

    def test_allowance_does_not_call_rpc(self):
        sb = _mock_sb(current_count=1)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            get_free_allowance("user_free_1")
        sb.rpc.assert_not_called()


# ── TestMonthlyReset ──────────────────────────────────────────────────────────

class TestMonthlyReset:

    def test_usage_keyed_by_this_month(self):
        """
        The DB key is the first day of the current month.
        A user's quota resets when the month changes — new month → new row → count=0.
        Simulate by having DB return 0 (as it would for a new month).
        """
        sb_new_month = _mock_sb(current_count=0, rpc_count=1)
        with patch("backend.services.keepa_free_quota.get_supabase", return_value=sb_new_month):
            result = check_and_record_free("user_free_1")
        assert result["used"] == 1   # resets to 1 after first call of new month

    def test_this_month_str_format(self):
        """Row key is always first-of-month ISO date."""
        month = _this_month_str()
        parts = month.split("-")
        assert len(parts) == 3
        assert parts[2] == "01"   # day is always 1


# ── TestFreeMonthlyDefault ────────────────────────────────────────────────────

class TestFreeMonthlyDefault:

    def test_default_limit_is_5(self):
        assert FREE_MONTHLY_LOOKUPS == 5

    def test_limit_respects_env_override(self):
        import os
        import importlib
        os.environ["KEEPA_FREE_MONTHLY_LOOKUPS"] = "3"
        try:
            importlib.reload(free_quota_mod)
            assert free_quota_mod.FREE_MONTHLY_LOOKUPS == 3
        finally:
            del os.environ["KEEPA_FREE_MONTHLY_LOOKUPS"]
            importlib.reload(free_quota_mod)


# ── TestUtcConsistency ────────────────────────────────────────────────────────

class TestUtcConsistency:
    """Verify that month keys and resets_on are always derived from UTC."""

    def test_resets_on_is_utc_first_of_next_month(self):
        """resets_on must be the first day of the next UTC month."""
        from datetime import date as _date
        fixed_utc = _date(2026, 6, 15)
        sb = _mock_sb(current_count=0, rpc_count=1)
        with patch("backend.services.keepa_free_quota._utc_today", return_value=fixed_utc), \
             patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            result = check_and_record_free("user_utc")
        assert result["resets_on"] == "2026-07-01"

    def test_month_boundary_preflight_and_rpc_use_same_key(self):
        """
        Regression guard for the timezone drift bug.

        Simulates the last day of a month: _utc_today() returns June 30.
        Both the pre-flight SELECT and the RPC increment must reference
        '2026-06-01', not '2026-07-01' (what the DB's CURRENT_DATE might
        return if it were in a UTC+ timezone).
        """
        from datetime import date as _date
        boundary_utc = _date(2026, 6, 30)
        sb = _mock_sb(current_count=0, rpc_count=1)
        with patch("backend.services.keepa_free_quota._utc_today", return_value=boundary_utc), \
             patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            result = check_and_record_free("boundary_user")

        # RPC must receive the same month key the pre-flight SELECT used
        sb.rpc.assert_called_once_with(
            "increment_keepa_free_usage",
            {"p_user_id": "boundary_user", "p_month": "2026-06-01"},
        )
        # resets_on is the first of July (next month after June)
        assert result["resets_on"] == "2026-07-01"

    def test_december_boundary_rpc_uses_december_key(self):
        """On Dec 31 UTC the RPC must use 2025-12-01, resets_on 2026-01-01."""
        from datetime import date as _date
        dec_utc = _date(2025, 12, 31)
        sb = _mock_sb(current_count=0, rpc_count=1)
        with patch("backend.services.keepa_free_quota._utc_today", return_value=dec_utc), \
             patch("backend.services.keepa_free_quota.get_supabase", return_value=sb):
            result = check_and_record_free("dec_user")

        sb.rpc.assert_called_once_with(
            "increment_keepa_free_usage",
            {"p_user_id": "dec_user", "p_month": "2025-12-01"},
        )
        assert result["resets_on"] == "2026-01-01"
