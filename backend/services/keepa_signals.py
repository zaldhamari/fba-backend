"""
Pure signal functions over Keepa history arrays.

Both functions are deterministic and dependency-free — safe to unit-test
with synthetic data and safe to call in any context.

History arrays from KeepaProduct are chronological lists of values with
timestamps stripped (see keepa.py _extract_history_values). We cannot
derive exact per-day timestamps, so trend calculations use the full
available window rather than a fixed 90-day period.

Honesty contract
----------------
Every function returns an explicit "insufficient_data" state when the
history is too short to support a reliable signal. We never coerce None
or an empty array into "stable" or "flat" — those are false reassurances.
The minimum for any signal is MIN_POINTS observations.
"""
import math
import statistics
from typing import List, Optional

MIN_POINTS = 5   # minimum observations for any signal


# ── BSR stability ──────────────────────────────────────────────────────────────

def bsr_stability(bsr_history: Optional[List[int]]) -> dict:
    """
    Analyse a BSR history array for volatility, trend, and spike indicators.

    BSR convention: LOWER = better rank (more sales). So a falling BSR over
    time means the product is rising in the rankings — "improving".

    Returns:
      rank_volatility  float  — coefficient of variation (std/mean); higher = noisier
      trend            str    — "improving" | "stable" | "declining" | "insufficient_data"
      spike_flag       bool   — True when recent BSR is far better than historic median,
                                suggesting a temporary demand spike rather than sustained demand

    spike_flag logic
    ----------------
    We compare the median of the most-recent 20% of observations (min 3) against
    the median of the full history. If the recent median is < 50% of the full
    median (rank improved 2× or more at the end), flag it as a potential one-off.
    A spike trap: great current BSR, unstable history.
    """
    valid = [b for b in (bsr_history or []) if b and b > 0]
    if len(valid) < MIN_POINTS:
        return {
            "rank_volatility": None,
            "trend":           "insufficient_data",
            "spike_flag":      False,
        }

    mean = statistics.mean(valid)
    std  = statistics.pstdev(valid)
    rank_volatility = round(std / mean, 4) if mean > 0 else 0.0

    # Trend: compare first-half median vs. second-half median
    mid        = len(valid) // 2
    first_half = valid[:mid]
    second_half = valid[mid:]
    median_first  = statistics.median(first_half)
    median_second = statistics.median(second_half)

    # Falling BSR = improving rank; threshold = 10% change
    pct_change = (median_second - median_first) / median_first if median_first > 0 else 0
    if pct_change < -0.10:
        trend = "improving"
    elif pct_change > 0.10:
        trend = "declining"
    else:
        trend = "stable"

    # Spike flag: are the most-recent observations suspiciously better than history?
    recent_n    = max(3, len(valid) // 5)
    recent      = valid[-recent_n:]
    full_median = statistics.median(valid)
    recent_median = statistics.median(recent)
    spike_flag = bool(full_median > 0 and recent_median < full_median * 0.50)

    return {
        "rank_volatility": rank_volatility,
        "trend":           trend,
        "spike_flag":      spike_flag,
    }


# ── Price trend ────────────────────────────────────────────────────────────────

def price_trend(price_history_cents: Optional[List[int]]) -> dict:
    """
    Analyse a price history array (values in cents) for direction and floor.

    Returns:
      direction     str    — "rising" | "flat" | "falling" | "insufficient_data"
      pct_change    float  — % change from first to last observation (positive = higher)
      floor_cents   int    — lowest price observed in the history

    Thresholds: >5% change = rising/falling; within ±5% = flat.
    A falling price trend is a race-to-the-bottom signal: flag it as a risk.
    """
    valid = [p for p in (price_history_cents or []) if p and p > 0]
    if len(valid) < MIN_POINTS:
        return {
            "direction":   "insufficient_data",
            "pct_change":  None,
            "floor_cents": None,
        }

    first = statistics.median(valid[:max(1, len(valid) // 5)])   # first-20% median
    last  = statistics.median(valid[-max(1, len(valid) // 5):])  # last-20% median

    pct_change = round((last - first) / first * 100, 2) if first > 0 else 0.0
    floor_cents = min(valid)

    if pct_change > 5.0:
        direction = "rising"
    elif pct_change < -5.0:
        direction = "falling"
    else:
        direction = "flat"

    return {
        "direction":   direction,
        "pct_change":  pct_change,
        "floor_cents": floor_cents,
    }


# ── Composite convenience helper ───────────────────────────────────────────────

def compute_signals(product) -> dict:
    """
    Compute both signal blocks from a KeepaProduct.
    Returns the dict that populates the "signals" field in /api/product/data.
    """
    bsr  = bsr_stability(product.bsr_history)
    price = price_trend(product.price_history_cents)
    floor_usd = (
        round(price["floor_cents"] / 100, 2)
        if price["floor_cents"] is not None else None
    )
    return {
        "bsr": {
            "trend":      bsr["trend"],
            "volatility": bsr["rank_volatility"],
            "spike_flag": bsr["spike_flag"],
        },
        "price": {
            "direction":      price["direction"],
            "pct_change_90d": price["pct_change"],
            "floor_usd":      floor_usd,
        },
    }
