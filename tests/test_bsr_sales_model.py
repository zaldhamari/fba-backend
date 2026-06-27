"""
Tests for backend/services/bsr_sales_model.py
Run: python3 -m pytest tests/test_bsr_sales_model.py -v
"""
import math
import pytest
from backend.services.bsr_sales_model import (
    estimateMonthlySales,
    normalizeCategory,
    calibrateCategory,
    estimateNicheDemand,
    CATEGORY_COEFFICIENTS,
    SalesEstimate,
)


# ── normalizeCategory ─────────────────────────────────────────────────────────

class TestNormalizeCategory:
    def test_raw_amazon_string(self):
        assert normalizeCategory("Home & Kitchen") == "home_kitchen"

    def test_already_normalised(self):
        assert normalizeCategory("electronics") == "electronics"

    def test_leading_trailing_whitespace(self):
        assert normalizeCategory("  Sports & Outdoors  ") == "sports_outdoors"

    def test_unknown_falls_back_to_default(self):
        assert normalizeCategory("Antique Furniture") == "default"

    def test_clothing_alias(self):
        assert normalizeCategory("Clothing, Shoes & Jewelry") == "clothing"

    def test_all_known_keys_round_trip(self):
        for key in CATEGORY_COEFFICIENTS:
            assert normalizeCategory(key) == key


# ── estimateMonthlySales ──────────────────────────────────────────────────────

class TestEstimateMonthlySales:
    def test_home_kitchen_bsr_100k_in_expected_range(self):
        """BSR=100,000 in home_kitchen should estimate 20–45 monthly sales."""
        est = estimateMonthlySales(100_000, "home_kitchen")
        assert isinstance(est, SalesEstimate)
        assert 20 <= est.monthly_sales <= 45, (
            f"Expected 20–45, got {est.monthly_sales}"
        )

    def test_electronics_bsr_1000_confidence(self):
        """BSR=1,000 in electronics: uncalibrated categories max out at Medium."""
        est = estimateMonthlySales(1_000, "electronics")
        assert est.confidence == "Medium"   # High downgraded to Medium (uncalibrated)
        assert est.confidence_score >= 55

    def test_low_confidence_at_high_bsr(self):
        est = estimateMonthlySales(500_000, "home_kitchen")
        assert est.confidence == "Low"
        assert est.confidence_score <= 25

    def test_medium_confidence_mid_range(self):
        # BSR 2001-20000 baseline is "Medium" — uncalibrated downgrades to "Low"
        est = estimateMonthlySales(10_000, "beauty")
        assert est.confidence == "Low"

    def test_returns_at_least_one_sale(self):
        """Even very high BSR should not return 0 sales."""
        est = estimateMonthlySales(9_999_999, "default")
        assert est.monthly_sales >= 1

    def test_low_band_less_than_point(self):
        est = estimateMonthlySales(5_000, "tools")
        assert est.low < est.monthly_sales

    def test_high_band_greater_than_point(self):
        est = estimateMonthlySales(5_000, "tools")
        assert est.high > est.monthly_sales

    def test_invalid_bsr_raises(self):
        with pytest.raises(ValueError):
            estimateMonthlySales(0, "home_kitchen")
        with pytest.raises(ValueError):
            estimateMonthlySales(-1, "home_kitchen")

    def test_raw_category_string_accepted(self):
        """Should accept un-normalised category strings without error."""
        est = estimateMonthlySales(10_000, "Home & Kitchen")
        assert est.category_key == "home_kitchen"

    def test_all_categories_produce_plausible_results(self):
        for cat in CATEGORY_COEFFICIENTS:
            if cat == "default":
                continue
            est = estimateMonthlySales(50_000, cat)
            assert est.monthly_sales >= 1


# ── calibrateCategory ─────────────────────────────────────────────────────────

class TestCalibrateCategory:
    def test_round_trip_home_kitchen(self):
        """
        Generate two data points from the model, calibrate from them,
        and confirm we recover approximately the original {a, b}.
        """
        from backend.services.bsr_sales_model import CATEGORY_COEFFICIENTS
        original = CATEGORY_COEFFICIENTS["home_kitchen"]
        a0, b0   = original["a"], original["b"]

        # Generate two exact data points
        bsr1, sales1 = 1_000,  round(a0 * 1_000  ** -b0)
        bsr2, sales2 = 50_000, round(a0 * 50_000 ** -b0)

        recovered = calibrateCategory("home_kitchen", [(bsr1, sales1), (bsr2, sales2)])

        assert abs(recovered["b"] - b0) < 0.01, (
            f"b mismatch: original={b0}, recovered={recovered['b']}"
        )
        assert abs(recovered["a"] - a0) / a0 < 0.05, (
            f"a mismatch: original={a0}, recovered={recovered['a']}"
        )

    def test_requires_at_least_two_points(self):
        with pytest.raises(ValueError, match="2"):
            calibrateCategory("default", [(1000, 500)])

    def test_identical_bsr_raises(self):
        with pytest.raises(ValueError):
            calibrateCategory("default", [(1000, 500), (1000, 300)])

    def test_negative_points_excluded(self):
        with pytest.raises(ValueError):
            calibrateCategory("default", [(0, 0), (-1, -1)])

    def test_returns_positive_coefficients(self):
        result = calibrateCategory("default", [(500, 2000), (100_000, 30)])
        assert result["a"] > 0
        assert result["b"] > 0


# ── estimateNicheDemand ───────────────────────────────────────────────────────

class TestEstimateNicheDemand:
    def test_empty_list(self):
        result = estimateNicheDemand([], "home_kitchen")
        assert result["total_monthly_sales"] == 0
        assert result["products_sampled"] == 0

    def test_sums_top_n(self):
        bsr_list = list(range(1_000, 21_000, 1_000))  # 20 products
        result = estimateNicheDemand(bsr_list, "electronics", top_n=10)
        assert result["products_sampled"] == 10
        assert result["total_monthly_sales"] > result["avg_monthly_sales"]

    def test_uses_lowest_bsrs(self):
        """Lower BSR = higher demand; top_n should pick the lowest BSRs."""
        low_bsr  = estimateNicheDemand([1_000, 2_000, 100_000], "home_kitchen", top_n=2)
        high_bsr = estimateNicheDemand([50_000, 80_000, 100_000], "home_kitchen", top_n=2)
        assert low_bsr["total_monthly_sales"] > high_bsr["total_monthly_sales"]

    def test_filters_zero_bsr(self):
        result = estimateNicheDemand([0, 0, 5_000], "default", top_n=5)
        assert result["products_sampled"] == 1
