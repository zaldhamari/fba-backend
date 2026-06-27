"""
Tests for backend/services/keepa_signals.py (Prompt 4).
All functions are pure — no mocking required.
Run: python3 -m pytest tests/test_keepa_signals.py -v
"""
import pytest
from backend.services.keepa_signals import bsr_stability, price_trend, compute_signals, MIN_POINTS


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_bsr(values):
    return values


def _make_price(values_cents):
    return values_cents


# ── TestBsrStability ──────────────────────────────────────────────────────────

class TestBsrStability:

    def test_none_input_returns_insufficient_data(self):
        result = bsr_stability(None)
        assert result["trend"]           == "insufficient_data"
        assert result["rank_volatility"] is None
        assert result["spike_flag"]      is False

    def test_empty_list_returns_insufficient_data(self):
        result = bsr_stability([])
        assert result["trend"] == "insufficient_data"

    def test_fewer_than_min_points_returns_insufficient_data(self):
        result = bsr_stability([1000, 2000, 3000, 4000])   # 4 < MIN_POINTS(5)
        assert result["trend"] == "insufficient_data"

    def test_exactly_min_points_produces_signal(self):
        result = bsr_stability([5000, 5100, 5050, 4900, 5000])
        assert result["trend"] != "insufficient_data"
        assert result["rank_volatility"] is not None

    def test_improving_trend(self):
        # BSR falls from high → low = rank improves
        # first half median >> second half median (>10% drop)
        bsr = [10000, 9500, 9000, 8000, 7000, 5000, 4000, 3000, 2000, 1000]
        result = bsr_stability(bsr)
        assert result["trend"] == "improving"

    def test_declining_trend(self):
        # BSR rises from low → high = rank worsens
        bsr = [1000, 2000, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 15000]
        result = bsr_stability(bsr)
        assert result["trend"] == "declining"

    def test_stable_trend(self):
        # BSR stays roughly constant (within ±10%)
        bsr = [5000, 5100, 4950, 5050, 5000, 5200, 4900, 5000, 5100, 5050]
        result = bsr_stability(bsr)
        assert result["trend"] == "stable"

    def test_spike_flag_fires_on_recent_dip(self):
        """
        Recent observations much better than history (BSR falls sharply at the end).
        spike_flag fires when recent median < 50% of full median.
        recent_n = max(3, len//5) = 3 for a 10-item list, so last 3 must all be low.
        """
        # History mostly 10000; last 3 all 2000 → recent median 2000 < 5000 (50% of 10000)
        bsr = [10000, 10000, 10000, 10000, 10000, 10000, 10000, 2000, 2000, 2000]
        result = bsr_stability(bsr)
        assert result["spike_flag"] is True

    def test_spike_flag_false_when_recent_rank_consistent(self):
        bsr = [5000, 5100, 4950, 5050, 5000, 5200, 4900, 5000, 5100, 5050]
        result = bsr_stability(bsr)
        assert result["spike_flag"] is False

    def test_spike_flag_false_on_declining_product(self):
        # Rank is getting worse (higher BSR) — NOT a spike situation
        bsr = [1000, 2000, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 15000]
        result = bsr_stability(bsr)
        assert result["spike_flag"] is False

    def test_volatility_is_float(self):
        bsr = [5000, 7000, 3000, 9000, 6000, 4000, 8000, 5500, 6500, 4500]
        result = bsr_stability(bsr)
        assert isinstance(result["rank_volatility"], float)

    def test_high_volatility_on_noisy_bsr(self):
        # Wild swings → high coefficient of variation
        bsr = [100, 50000, 200, 60000, 150, 40000, 300, 55000, 250, 45000]
        result = bsr_stability(bsr)
        assert result["rank_volatility"] > 0.5

    def test_low_volatility_on_stable_bsr(self):
        bsr = [5000, 5010, 4990, 5005, 4995, 5002, 4998, 5001, 4999, 5003]
        result = bsr_stability(bsr)
        assert result["rank_volatility"] < 0.01

    def test_zeros_and_none_in_history_filtered(self):
        # Mixed valid/invalid values — must work as long as ≥5 valid
        bsr = [0, None, 5000, 5100, 4950, 5050, 5000, None, 0, 5200]
        result = bsr_stability(bsr)
        assert result["trend"] != "insufficient_data"

    def test_single_point_dip_at_end_triggers_spike(self):
        """
        Spike detection fires when the recent window (last max(3, len//5) items)
        is clearly better than the full median. With a 10-item list recent_n=3;
        all three must be low for the median to drop below 50% of the full median.
        """
        # Last 3 all 3000; full median of [20000]*7+[3000,3000,3000] = 20000
        # recent median 3000 < 10000 (50% of 20000) → spike
        bsr = [20000, 20000, 20000, 20000, 20000, 20000, 20000, 3000, 3000, 3000]
        result = bsr_stability(bsr)
        assert result["spike_flag"] is True


# ── TestPriceTrend ────────────────────────────────────────────────────────────

class TestPriceTrend:

    def test_none_input_returns_insufficient_data(self):
        result = price_trend(None)
        assert result["direction"]   == "insufficient_data"
        assert result["pct_change"]  is None
        assert result["floor_cents"] is None

    def test_empty_list_returns_insufficient_data(self):
        result = price_trend([])
        assert result["direction"] == "insufficient_data"

    def test_fewer_than_min_points_returns_insufficient_data(self):
        result = price_trend([2000, 1900, 1800, 2100])  # 4 < MIN_POINTS
        assert result["direction"] == "insufficient_data"

    def test_rising_price_direction(self):
        # Price increases from ~$10 to ~$20 (100% rise — clearly rising)
        prices = [1000, 1100, 1200, 1300, 1400, 1500, 1700, 1900, 2000, 2000]
        result = price_trend(prices)
        assert result["direction"] == "rising"
        assert result["pct_change"] > 5.0

    def test_falling_price_direction(self):
        # Price decreases from ~$30 to ~$20 (~33% fall)
        prices = [3000, 2900, 2800, 2700, 2600, 2500, 2300, 2100, 2000, 2000]
        result = price_trend(prices)
        assert result["direction"] == "falling"
        assert result["pct_change"] < -5.0

    def test_flat_price_direction(self):
        # Price stays within ±5%
        prices = [2000, 2050, 1980, 2020, 2000, 2010, 1990, 2030, 2000, 2005]
        result = price_trend(prices)
        assert result["direction"] == "flat"
        assert abs(result["pct_change"]) <= 5.0

    def test_floor_cents_is_minimum(self):
        prices = [3000, 2500, 1500, 2000, 2800, 3200, 2600, 1800, 2200, 2400]
        result = price_trend(prices)
        assert result["floor_cents"] == 1500

    def test_pct_change_is_float(self):
        prices = [2000, 2100, 2200, 2300, 2400, 2500, 2600, 2700, 2800, 2900]
        result = price_trend(prices)
        assert isinstance(result["pct_change"], float)

    def test_zeros_filtered_from_history(self):
        # Zeros should be excluded; remaining ≥5 valid
        prices = [0, 2000, 2100, 2050, 2000, 2080, 0, 2020, 2060, 2040]
        result = price_trend(prices)
        assert result["direction"] != "insufficient_data"
        assert result["floor_cents"] == 2000

    def test_threshold_exactly_five_percent(self):
        # 5% boundary: flat on both sides
        prices_flat = [2000] * 10  # 0% change = flat
        assert price_trend(prices_flat)["direction"] == "flat"


# ── TestComputeSignals ────────────────────────────────────────────────────────

class TestComputeSignals:

    def _make_product(self, bsr_history=None, price_history_cents=None):
        class FakeProduct:
            pass
        p = FakeProduct()
        p.bsr_history          = bsr_history
        p.price_history_cents  = price_history_cents
        return p

    def test_returns_bsr_and_price_blocks(self):
        product = self._make_product()
        signals = compute_signals(product)
        assert "bsr"   in signals
        assert "price" in signals

    def test_bsr_block_has_required_fields(self):
        product = self._make_product()
        bsr_block = compute_signals(product)["bsr"]
        assert "trend"      in bsr_block
        assert "volatility" in bsr_block
        assert "spike_flag" in bsr_block

    def test_price_block_has_required_fields(self):
        product = self._make_product()
        price_block = compute_signals(product)["price"]
        assert "direction"      in price_block
        assert "pct_change_90d" in price_block
        assert "floor_usd"      in price_block

    def test_floor_usd_is_dollars_not_cents(self):
        prices = [2000, 2050, 1980, 2020, 2000, 2010, 1990, 2030, 2000, 2005]
        bsr    = [5000, 5100, 4950, 5050, 5000, 5200, 4900, 5000, 5100, 5050]
        product = self._make_product(bsr_history=bsr, price_history_cents=prices)
        floor_usd = compute_signals(product)["price"]["floor_usd"]
        assert floor_usd is not None
        assert floor_usd == round(min(prices) / 100, 2)

    def test_none_histories_produce_insufficient_data(self):
        product = self._make_product(bsr_history=None, price_history_cents=None)
        signals = compute_signals(product)
        assert signals["bsr"]["trend"]        == "insufficient_data"
        assert signals["price"]["direction"]  == "insufficient_data"
        assert signals["price"]["floor_usd"]  is None


# ── TestSignalPenaltiesInScorer ───────────────────────────────────────────────

class TestSignalPenaltiesInScorer:
    """
    Verifies that bsr_declining, spike_flag, and price_falling dock points
    in score_opportunity() as documented in Prompt 4.
    """

    def _base_score(self, **kwargs):
        from backend.modules.opportunity import score_opportunity
        defaults = dict(
            amazon_price=25.0,
            supplier_price=8.0,
            review_count=100,
            trend_direction="Stable",
            weight_lbs=1.0,
            category="home_kitchen",
        )
        defaults.update(kwargs)
        return score_opportunity(**defaults)

    def test_no_signals_establishes_baseline(self):
        result = self._base_score()
        assert result["breakdown"]["signal_penalty"] == 0

    def test_bsr_declining_docks_10_points(self):
        base     = self._base_score()
        penalised = self._base_score(bsr_declining=True)
        assert penalised["score"] == max(0, round(base["score"] - 10, 1))
        assert penalised["breakdown"]["signal_penalty"] == 10

    def test_spike_flag_docks_8_points(self):
        base     = self._base_score()
        penalised = self._base_score(spike_flag=True)
        assert penalised["score"] == max(0, round(base["score"] - 8, 1))
        assert penalised["breakdown"]["signal_penalty"] == 8

    def test_price_falling_docks_7_points(self):
        base     = self._base_score()
        penalised = self._base_score(price_falling=True)
        assert penalised["score"] == max(0, round(base["score"] - 7, 1))
        assert penalised["breakdown"]["signal_penalty"] == 7

    def test_all_three_signals_dock_25_points(self):
        base     = self._base_score()
        penalised = self._base_score(bsr_declining=True, spike_flag=True, price_falling=True)
        expected_penalty = 10 + 8 + 7
        assert penalised["breakdown"]["signal_penalty"] == expected_penalty
        assert penalised["score"] == max(0, round(base["score"] - expected_penalty, 1))

    def test_score_never_goes_below_zero(self):
        # Very bad product + all signals — should clamp at 0
        result = self._base_score(
            amazon_price=5.0,     # bad price point
            supplier_price=4.5,   # terrible margin
            review_count=5000,    # saturated
            trend_direction="Declining",
            bsr_declining=True,
            spike_flag=True,
            price_falling=True,
        )
        assert result["score"] >= 0

    def test_signal_notes_populated_for_active_signals(self):
        result = self._base_score(bsr_declining=True, price_falling=True)
        notes = result["signal_notes"]
        assert any("BSR" in n for n in notes)
        assert any("price" in n.lower() for n in notes)

    def test_no_signal_notes_when_no_penalties(self):
        result = self._base_score()
        assert result["signal_notes"] == []

    def test_declining_trend_direction_independent_of_bsr_signal(self):
        """trend_direction and bsr_declining are separate inputs — both can be active."""
        result = self._base_score(trend_direction="Declining", bsr_declining=True)
        # Both the trend score penalty AND the bsr_declining penalty apply
        assert result["breakdown"]["signal_penalty"] == 10
        assert result["breakdown"]["trend_score"] == 20   # Declining trend_direction score
