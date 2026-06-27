"""
Tests for backend/services/keepa.py
All HTTP calls are mocked — no real Keepa tokens consumed.
Run: python3 -m pytest tests/test_keepa.py -v
"""
import pytest
import httpx
import json
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.keepa import (
    KeepaProduct,
    KeepaRateLimitError,
    KeepaError,
    get_product_by_asin,
    get_products_by_asins,
    _parse_product,
    _cents_or_none,
    _extract_history_values,
    _extract_bsr_history_from_sales_ranks,
    _extract_current_price_and_bsr,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_raw_product(
    asin="B000000001",
    title="Test Product",
    brand="TestBrand",
    category_tree=None,
    stats=None,
    avg_rating=45,
    review_count=1234,
    csv=None,
    sales_ranks=None,
):
    """Build a minimal Keepa raw product dict."""
    cat_tree = category_tree or [{"id": "1055398", "name": "Home & Kitchen"}]
    _stats = stats or {
        "current": [0, 1999, 0, 5000, 0, 0, 0, 0],
        "avg90":   [0, 2100, 0, 0,    0, 0, 0, 2050],
    }
    # csv[1] = new-price history  [t0,v0, t1,v1, ...]
    _csv = csv or [None, [100, 1999, 200, 2099, 300, -1]]
    _sales_ranks = sales_ranks or {"1055398": [100, 5000, 200, 4800, 300, 5100]}
    return {
        "asin":         asin,
        "title":        title,
        "brand":        brand,
        "categoryTree": cat_tree,
        "stats":        _stats,
        "avgRating":    avg_rating,
        "reviewCount":  review_count,
        "csv":          _csv,
        "salesRanks":   _sales_ranks,
    }


def _keepa_response(products, tokens_left=500, refill_rate=3):
    return {
        "tokensLeft":  tokens_left,
        "refillRate":  refill_rate,
        "products":    products,
    }


def _make_mock_response(data: dict, status_code: int = 200):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.text = json.dumps(data)
    return resp


# ── Unit tests: pure helpers ──────────────────────────────────────────────────

class TestCentsOrNone:
    def test_positive_value(self):
        assert _cents_or_none(1999) == 1999

    def test_negative_one_is_none(self):
        assert _cents_or_none(-1) is None

    def test_none_is_none(self):
        assert _cents_or_none(None) is None

    def test_zero_is_zero(self):
        assert _cents_or_none(0) == 0


class TestExtractHistoryValues:
    def test_normal_interleaved(self):
        # [time, value, time, value, ...]
        assert _extract_history_values([100, 1999, 200, 2099]) == [1999, 2099]

    def test_filters_negative_values(self):
        assert _extract_history_values([100, -1, 200, 1999]) == [1999]

    def test_empty_returns_none(self):
        assert _extract_history_values([]) is None

    def test_all_negative_returns_none(self):
        assert _extract_history_values([100, -1, 200, -1]) is None


class TestExtractBsrHistory:
    def test_basic(self):
        result = _extract_bsr_history_from_sales_ranks({"1055398": [100, 5000, 200, 4800]})
        assert result == [5000, 4800]

    def test_filters_zero_and_negative(self):
        result = _extract_bsr_history_from_sales_ranks({"1": [100, 0, 200, -1, 300, 5000]})
        assert result == [5000]

    def test_empty_dict(self):
        assert _extract_bsr_history_from_sales_ranks({}) is None

    def test_none_input(self):
        assert _extract_bsr_history_from_sales_ranks(None) is None


class TestExtractCurrentPriceAndBsr:
    def test_extracts_price_and_bsr(self):
        stats = {
            "current": [0, 1999, 0, 5000],
            "avg90":   [0, 2100, 0, 0,    0, 0, 0, 0],
        }
        price, avg90, bsr = _extract_current_price_and_bsr(stats)
        assert price == 1999
        assert avg90 == 2100  # implementation reads avg90[1]
        assert bsr   == 5000

    def test_negative_price_is_none(self):
        stats = {"current": [0, -1, 0, 100], "avg90": []}
        price, avg90, bsr = _extract_current_price_and_bsr(stats)
        assert price is None

    def test_empty_stats(self):
        price, avg90, bsr = _extract_current_price_and_bsr(None)
        assert price is None
        assert avg90 is None
        assert bsr   is None


# ── Unit tests: _parse_product ────────────────────────────────────────────────

class TestParseProduct:
    def test_basic_fields(self):
        raw = _make_raw_product()
        p   = _parse_product(raw)
        assert isinstance(p, KeepaProduct)
        assert p.asin  == "B000000001"
        assert p.title == "Test Product"
        assert p.brand == "TestBrand"

    def test_category_from_tree(self):
        raw = _make_raw_product(category_tree=[{"id": "1", "name": "Electronics"}])
        p   = _parse_product(raw)
        assert p.category == "Electronics"

    def test_rating_divided_by_10(self):
        raw = _make_raw_product(avg_rating=45)
        p   = _parse_product(raw)
        assert p.rating == 4.5

    def test_negative_rating_is_none(self):
        raw = _make_raw_product(avg_rating=-1)
        p   = _parse_product(raw)
        assert p.rating is None

    def test_current_price_from_stats(self):
        raw = _make_raw_product()
        p   = _parse_product(raw)
        assert p.current_price_cents == 1999

    def test_avg90_price_from_stats(self):
        raw = _make_raw_product()
        p   = _parse_product(raw)
        assert p.avg90_price_cents == 2100  # avg90[1] in fixture

    def test_bsr_from_stats(self):
        raw = _make_raw_product()
        p   = _parse_product(raw)
        assert p.current_bsr == 5000

    def test_bsr_falls_back_to_sales_ranks_when_stats_missing(self):
        raw = _make_raw_product(stats={"current": [], "avg90": []})
        p   = _parse_product(raw)
        # Last value from salesRanks
        assert p.current_bsr == 5100

    def test_price_history_extracted(self):
        raw = _make_raw_product()
        p   = _parse_product(raw)
        # csv[1] = [100, 1999, 200, 2099, 300, -1] → [1999, 2099]
        assert p.price_history_cents == [1999, 2099]

    def test_bsr_history_extracted(self):
        raw = _make_raw_product()
        p   = _parse_product(raw)
        assert p.bsr_history == [5000, 4800, 5100]

    def test_review_count(self):
        raw = _make_raw_product(review_count=999)
        p   = _parse_product(raw)
        assert p.review_count == 999

    def test_negative_review_count_is_none(self):
        raw = _make_raw_product(review_count=-1)
        p   = _parse_product(raw)
        assert p.review_count is None


# ── Integration tests: get_products_by_asins (mocked HTTP) ───────────────────

class TestGetProductsByAsins:
    @pytest.mark.asyncio
    async def test_single_asin_success(self):
        raw     = _make_raw_product(asin="B000000001")
        payload = _keepa_response([raw])

        with patch("backend.services.keepa.KEEPA_API_KEY", "test-key"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = _make_mock_response(payload)
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__  = AsyncMock(return_value=False)
            mock_client.get        = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            results = await get_products_by_asins(["B000000001"])

        assert len(results) == 1
        assert results[0].asin == "B000000001"

    @pytest.mark.asyncio
    async def test_empty_asins_returns_empty(self):
        results = await get_products_by_asins([])
        assert results == []

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_keepa_error(self):
        with patch("backend.services.keepa.KEEPA_API_KEY", ""):
            with pytest.raises(KeepaError, match="KEEPA_API_KEY"):
                await get_products_by_asins(["B000000001"])

    @pytest.mark.asyncio
    async def test_http_error_raises_keepa_error(self):
        mock_resp = _make_mock_response({}, status_code=429)

        with patch("backend.services.keepa.KEEPA_API_KEY", "test-key"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__  = AsyncMock(return_value=False)
            mock_client.get        = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            with pytest.raises(KeepaError, match="429"):
                await get_products_by_asins(["B000000001"])

    @pytest.mark.asyncio
    async def test_rate_limit_error_on_zero_tokens(self):
        raw     = _make_raw_product()
        payload = _keepa_response([raw], tokens_left=0)

        with patch("backend.services.keepa.KEEPA_API_KEY", "test-key"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = _make_mock_response(payload)
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__  = AsyncMock(return_value=False)
            mock_client.get        = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            with pytest.raises(KeepaRateLimitError) as exc_info:
                await get_products_by_asins(["B000000001"])
        assert exc_info.value.tokens_left == 0

    @pytest.mark.asyncio
    async def test_rate_limit_error_on_request_limit_type(self):
        payload = {
            "tokensLeft": 5,
            "refillRate": 3.0,
            "error":      {"type": "REQUEST_LIMIT", "message": "limit hit"},
            "products":   [],
        }

        with patch("backend.services.keepa.KEEPA_API_KEY", "test-key"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = _make_mock_response(payload)
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__  = AsyncMock(return_value=False)
            mock_client.get        = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            with pytest.raises(KeepaRateLimitError):
                await get_products_by_asins(["B000000001"])

    @pytest.mark.asyncio
    async def test_batches_large_asin_list(self):
        """101 ASINs should result in 2 HTTP calls (100 + 1)."""
        asins   = [f"B{str(i).zfill(9)}" for i in range(101)]
        raws    = [_make_raw_product(asin=a) for a in asins]
        batch1  = _keepa_response(raws[:100])
        batch2  = _keepa_response(raws[100:])

        with patch("backend.services.keepa.KEEPA_API_KEY", "test-key"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__  = AsyncMock(return_value=False)
            mock_client.get        = AsyncMock(side_effect=[
                _make_mock_response(batch1),
                _make_mock_response(batch2),
            ])
            mock_client_cls.return_value = mock_client

            results = await get_products_by_asins(asins)

        assert mock_client.get.call_count == 2
        assert len(results) == 101


class TestGetProductByAsin:
    @pytest.mark.asyncio
    async def test_delegates_to_batch(self):
        raw     = _make_raw_product(asin="B000000099")
        payload = _keepa_response([raw])

        with patch("backend.services.keepa.KEEPA_API_KEY", "test-key"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp   = _make_mock_response(payload)
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__  = AsyncMock(return_value=False)
            mock_client.get        = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            product = await get_product_by_asin("B000000099")

        assert product.asin == "B000000099"

    @pytest.mark.asyncio
    async def test_empty_response_raises_keepa_error(self):
        payload = _keepa_response([])

        with patch("backend.services.keepa.KEEPA_API_KEY", "test-key"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp   = _make_mock_response(payload)
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__  = AsyncMock(return_value=False)
            mock_client.get        = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            with pytest.raises(KeepaError, match="no data"):
                await get_product_by_asin("B000000099")
