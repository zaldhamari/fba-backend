"""
Tests for backend/services/keepa_cache.py
Keepa HTTP and Supabase are fully stubbed — no real I/O.
Run: python3 -m pytest tests/test_keepa_cache.py -v
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.keepa import KeepaProduct, KeepaRateLimitError, KeepaError
from backend.services.keepa_cache import (
    get_cached_product,
    get_cached_products_batch,
    _to_payload,
    _from_payload,
    _is_fresh,
    _parse_fetched_at,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _product(asin="B000000001") -> KeepaProduct:
    return KeepaProduct(
        asin=asin,
        title="Test",
        brand="Brand",
        category="Home & Kitchen",
        current_bsr=5000,
        current_price_cents=1999,
        avg90_price_cents=2100,
        rating=4.5,
        review_count=100,
        bsr_history=[5000, 4800],
        price_history_cents=[1999, 2099],
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stale_iso(hours=48) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _make_row(asin="B000000001", fetched_iso=None, domain=1) -> dict:
    p = _product(asin)
    return {
        "asin":       asin,
        "domain":     domain,
        "payload":    _to_payload(p),
        "fetched_at": fetched_iso or _now_iso(),
    }


def _mock_supabase(row=None, rows=None):
    """Return a minimal Supabase mock that covers table().select()...execute() chains."""
    sb = MagicMock()
    table = MagicMock()
    sb.table.return_value = table

    # Fluent chain for single-asin lookup: .select().eq().eq().maybe_single().execute()
    maybe_single_result = MagicMock()
    maybe_single_result.data = row
    chain = MagicMock()
    chain.maybe_single.return_value.execute.return_value = maybe_single_result

    # Fluent chain for batch lookup: .select().in_().eq().execute()
    batch_result = MagicMock()
    batch_result.data = rows or []
    chain.in_.return_value.eq.return_value.execute.return_value = batch_result

    # .eq().eq() → chain
    chain.eq.return_value = chain

    table.select.return_value = chain

    # upsert chain
    upsert_chain = MagicMock()
    upsert_chain.execute.return_value = MagicMock()
    table.upsert.return_value = upsert_chain

    return sb


# ── Unit tests: pure helpers ──────────────────────────────────────────────────

class TestToFromPayload:
    def test_round_trip(self):
        p = _product()
        recovered = _from_payload(_to_payload(p))
        assert recovered.asin                == p.asin
        assert recovered.current_bsr         == p.current_bsr
        assert recovered.current_price_cents == p.current_price_cents
        assert recovered.rating              == p.rating
        assert recovered.bsr_history         == p.bsr_history
        assert recovered.price_history_cents == p.price_history_cents


class TestIsFresh:
    def test_fresh_within_window(self):
        fetched = datetime.now(timezone.utc) - timedelta(hours=1)
        assert _is_fresh(fetched, max_age_hours=24) is True

    def test_stale_beyond_window(self):
        fetched = datetime.now(timezone.utc) - timedelta(hours=25)
        assert _is_fresh(fetched, max_age_hours=24) is False

    def test_exactly_at_boundary(self):
        fetched = datetime.now(timezone.utc) - timedelta(hours=24, seconds=1)
        assert _is_fresh(fetched, max_age_hours=24) is False


class TestParseFetchedAt:
    def test_parses_utc_string(self):
        ts = "2025-06-07T12:00:00+00:00"
        dt = _parse_fetched_at(ts)
        assert dt.tzinfo is not None
        assert dt.year == 2025

    def test_naive_string_gets_utc(self):
        dt = _parse_fetched_at("2025-06-07T12:00:00")
        assert dt.tzinfo is not None


# ── Integration tests: get_cached_product ─────────────────────────────────────

class TestGetCachedProduct:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cache_source(self):
        row = _make_row(fetched_iso=_now_iso())

        with patch("backend.services.keepa_cache.get_supabase", return_value=_mock_supabase(row=row)):
            product, source = await get_cached_product("B000000001")

        assert source == "cache"
        assert product.asin == "B000000001"

    @pytest.mark.asyncio
    async def test_cache_miss_calls_keepa_and_returns_live(self):
        # No cached row
        live_product = _product("B000000001")

        with patch("backend.services.keepa_cache.get_supabase", return_value=_mock_supabase(row=None)), \
             patch("backend.services.keepa_cache.get_product_by_asin", AsyncMock(return_value=live_product)):
            product, source = await get_cached_product("B000000001")

        assert source == "live"
        assert product.asin == "B000000001"

    @pytest.mark.asyncio
    async def test_stale_cache_calls_keepa_and_returns_live(self):
        stale_row    = _make_row(fetched_iso=_stale_iso(hours=48))
        live_product = _product("B000000001")

        with patch("backend.services.keepa_cache.get_supabase", return_value=_mock_supabase(row=stale_row)), \
             patch("backend.services.keepa_cache.get_product_by_asin", AsyncMock(return_value=live_product)):
            product, source = await get_cached_product("B000000001")

        assert source == "live"

    @pytest.mark.asyncio
    async def test_rate_limit_with_stale_returns_stale(self):
        stale_row = _make_row(fetched_iso=_stale_iso(hours=48))

        with patch("backend.services.keepa_cache.get_supabase", return_value=_mock_supabase(row=stale_row)), \
             patch("backend.services.keepa_cache.get_product_by_asin", AsyncMock(side_effect=KeepaRateLimitError(0))):
            product, source = await get_cached_product("B000000001")

        assert source == "stale"
        assert product.asin == "B000000001"

    @pytest.mark.asyncio
    async def test_rate_limit_with_no_cache_reraises(self):
        with patch("backend.services.keepa_cache.get_supabase", return_value=_mock_supabase(row=None)), \
             patch("backend.services.keepa_cache.get_product_by_asin", AsyncMock(side_effect=KeepaRateLimitError(0))):
            with pytest.raises(KeepaRateLimitError):
                await get_cached_product("B000000001")


# ── Integration tests: get_cached_products_batch ─────────────────────────────

class TestGetCachedProductsBatch:
    @pytest.mark.asyncio
    async def test_empty_asins_returns_empty(self):
        result = await get_cached_products_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_all_cache_hits_no_keepa_call(self):
        asins = ["B000000001", "B000000002"]
        rows  = [_make_row(a, fetched_iso=_now_iso()) for a in asins]

        with patch("backend.services.keepa_cache.get_supabase", return_value=_mock_supabase(rows=rows)), \
             patch("backend.services.keepa_cache.get_products_by_asins", AsyncMock()) as mock_keepa:
            results = await get_cached_products_batch(asins)

        mock_keepa.assert_not_called()
        assert len(results) == 2
        assert all(src == "cache" for _, src in results)

    @pytest.mark.asyncio
    async def test_partial_miss_fetches_only_missing(self):
        hit_asin  = "B000000001"
        miss_asin = "B000000002"
        rows      = [_make_row(hit_asin, fetched_iso=_now_iso())]
        live_prod = _product(miss_asin)

        with patch("backend.services.keepa_cache.get_supabase", return_value=_mock_supabase(rows=rows)), \
             patch("backend.services.keepa_cache.get_products_by_asins", AsyncMock(return_value=[live_prod])) as mock_keepa:
            results = await get_cached_products_batch([hit_asin, miss_asin])

        mock_keepa.assert_called_once()
        call_args = mock_keepa.call_args[0][0]
        assert miss_asin in call_args
        assert hit_asin not in call_args

        sources = {p.asin: src for p, src in results}
        assert sources[hit_asin]  == "cache"
        assert sources[miss_asin] == "live"

    @pytest.mark.asyncio
    async def test_preserves_input_order(self):
        asins = ["B000000003", "B000000001", "B000000002"]
        rows  = [_make_row(a, fetched_iso=_now_iso()) for a in asins]
        # Rows returned from DB in different order
        rows_shuffled = [rows[2], rows[0], rows[1]]

        with patch("backend.services.keepa_cache.get_supabase", return_value=_mock_supabase(rows=rows_shuffled)):
            results = await get_cached_products_batch(asins)

        result_asins = [p.asin for p, _ in results]
        assert result_asins == asins

    @pytest.mark.asyncio
    async def test_rate_limit_degrades_to_stale_for_cached_asins(self):
        fresh_asin = "B000000001"
        stale_asin = "B000000002"
        no_cache_asin = "B000000003"

        rows = [
            _make_row(fresh_asin, fetched_iso=_now_iso()),
            _make_row(stale_asin, fetched_iso=_stale_iso(hours=48)),
        ]

        with patch("backend.services.keepa_cache.get_supabase", return_value=_mock_supabase(rows=rows)), \
             patch("backend.services.keepa_cache.get_products_by_asins", AsyncMock(side_effect=KeepaRateLimitError(0))):
            results = await get_cached_products_batch([fresh_asin, stale_asin, no_cache_asin])

        result_map = {p.asin: src for p, src in results}
        assert result_map[fresh_asin]  == "cache"   # was already fresh
        assert result_map[stale_asin]  == "stale"   # degraded
        assert no_cache_asin not in result_map       # dropped (no row at all)
