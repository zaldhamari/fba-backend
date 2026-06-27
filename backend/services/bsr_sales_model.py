"""
BSR → Monthly Sales Model
=========================
Power-law model:  monthly_sales = a * BSR^(-b)

Provenance fields per category
-------------------------------
Every category entry now carries:
  calibrated     bool  — True only after coefficients have been fitted against
                         real observed (BSR, monthly_sales) pairs via
                         backend/scripts/calibrate_bsr.py.
  calibration_n  int   — Number of real data points used in the last fit.

All shipped coefficients start as calibrated=False, calibration_n=0.
This is intentional: they are industry-rule-of-thumb starting values,
NOT validated against real Amazon sales data. The calibration script must
be run with operator-supplied observations before any category can be
promoted to calibrated=True.

Honesty contract
----------------
When a category is uncalibrated:
  - "High" confidence is never returned (downgraded to "Medium").
  - The SalesEstimate.note always appends a calibration caveat.
  - This guarantees we never present a pure-model guess as a validated fact.

Use calibrateCategory() to fit new coefficients from real data, then run
the calibration script to generate an updated CATEGORY_COEFFICIENTS block
for human review before committing.
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# ── Category coefficients ─────────────────────────────────────────────────────
# Fields: a, b, calibrated, calibration_n
# Calibration anchor (rule-of-thumb): BSR=10,000 → ~100 sales/mo for most cats.

CATEGORY_COEFFICIENTS: Dict[str, Dict] = {
    "home_kitchen":    {"a": 168_000.0, "b": 0.7500, "calibrated": False, "calibration_n": 0},
    "electronics":     {"a": 300_000.0, "b": 0.8000, "calibrated": False, "calibration_n": 0},
    "sports_outdoors": {"a": 120_000.0, "b": 0.7300, "calibrated": False, "calibration_n": 0},
    "toys_games":      {"a": 140_000.0, "b": 0.7400, "calibrated": False, "calibration_n": 0},
    "beauty":          {"a": 200_000.0, "b": 0.7700, "calibrated": False, "calibration_n": 0},
    "clothing":        {"a": 250_000.0, "b": 0.7800, "calibrated": False, "calibration_n": 0},
    "books":           {"a":  80_000.0, "b": 0.7000, "calibrated": False, "calibration_n": 0},
    "health":          {"a": 180_000.0, "b": 0.7600, "calibrated": False, "calibration_n": 0},
    "grocery":         {"a": 220_000.0, "b": 0.7800, "calibrated": False, "calibration_n": 0},
    "pet_supplies":    {"a": 150_000.0, "b": 0.7400, "calibrated": False, "calibration_n": 0},
    "tools":           {"a": 130_000.0, "b": 0.7300, "calibrated": False, "calibration_n": 0},
    "office":          {"a": 160_000.0, "b": 0.7500, "calibrated": False, "calibration_n": 0},
    "default":         {"a": 168_000.0, "b": 0.7500, "calibrated": False, "calibration_n": 0},
}

# Alias map: lowercase raw strings → internal category key
CATEGORY_ALIASES: Dict[str, str] = {
    "home & kitchen":            "home_kitchen",
    "home and kitchen":          "home_kitchen",
    "kitchen":                   "home_kitchen",
    "electronics":               "electronics",
    "sports & outdoors":         "sports_outdoors",
    "sports and outdoors":       "sports_outdoors",
    "sports":                    "sports_outdoors",
    "outdoors":                  "sports_outdoors",
    "toys & games":              "toys_games",
    "toys and games":            "toys_games",
    "toys":                      "toys_games",
    "games":                     "toys_games",
    "beauty":                    "beauty",
    "beauty & personal care":    "beauty",
    "personal care":             "beauty",
    "clothing":                  "clothing",
    "clothing, shoes & jewelry": "clothing",
    "apparel":                   "clothing",
    "fashion":                   "clothing",
    "books":                     "books",
    "health & household":        "health",
    "health and household":      "health",
    "health":                    "health",
    "grocery":                   "grocery",
    "grocery & gourmet food":    "grocery",
    "food":                      "grocery",
    "pet supplies":              "pet_supplies",
    "pet":                       "pet_supplies",
    "tools & home improvement":  "tools",
    "tools and home improvement":"tools",
    "tools":                     "tools",
    "office products":           "office",
    "office":                    "office",
}


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class SalesEstimate:
    monthly_sales:    int    # point estimate (round number)
    low:              int    # conservative bound
    high:             int    # optimistic bound
    confidence:       str    # "High" | "Medium" | "Low"
    confidence_score: int    # 0–100 (for machine consumption)
    note:             str    # human-readable caveat
    category_key:     str    # normalised category used for estimation


# ── Public API ────────────────────────────────────────────────────────────────

def normalizeCategory(raw: str) -> str:
    """Map a raw Amazon category string to an internal coefficient key."""
    key = raw.strip().lower()
    if key in CATEGORY_COEFFICIENTS:
        return key
    return CATEGORY_ALIASES.get(key, "default")


def estimateMonthlySales(bsr: int, category: str) -> SalesEstimate:
    """
    Estimate monthly unit sales from a Best Sellers Rank using a power law:
        sales = a * BSR^(-b)

    Confidence reflects both BSR range and calibration status:

      BSR range alone:
        ≤ 2,000    → High   (dense data, stable relationship)
        ≤ 20,000   → Medium (reliable directional signal)
        ≤ 100,000  → Low
        > 100,000  → Low    (very noisy — treat as floor)

      Calibration penalty (uncalibrated categories):
        High  → Medium   (we can't claim High confidence on rule-of-thumb coefficients)
        Medium → Low
        Low   → Low      (floor; no further degradation)

    This means an uncalibrated category can NEVER return "High" confidence,
    regardless of BSR. This is intentional.
    """
    if bsr <= 0:
        raise ValueError(f"BSR must be a positive integer, got {bsr!r}")

    cat_key = normalizeCategory(category)
    coeff   = CATEGORY_COEFFICIENTS[cat_key]
    a, b    = coeff["a"], coeff["b"]
    calibrated    = coeff.get("calibrated", False)
    calibration_n = coeff.get("calibration_n", 0)

    point = a * (bsr ** -b)
    monthly_sales = max(1, round(point))

    # Uncertainty band grows logarithmically with BSR
    log_bsr     = math.log10(max(bsr, 1))
    uncertainty = min(0.60, max(0.20, 0.15 + (log_bsr - 2.0) * 0.09))

    low  = max(1, round(point * (1.0 - uncertainty)))
    high = max(monthly_sales + 1, round(point * (1.0 + uncertainty)))

    # Base confidence from BSR range
    if bsr <= 2_000:
        confidence, score = "High",   85
        note = "Strong signal — BSR in a well-studied range for this category."
    elif bsr <= 20_000:
        confidence, score = "Medium", 65
        note = "Directional estimate — moderate confidence for this BSR range."
    elif bsr <= 100_000:
        confidence, score = "Low",    40
        note = "Use as a rough order-of-magnitude. Verify with launch data."
    else:
        confidence, score = "Low",    20
        note = "BSR above 100k — high uncertainty. Treat as a lower bound only."

    # Calibration penalty — downgrade one bucket if coefficients are unvalidated
    if not calibrated:
        if confidence == "High":
            confidence, score = "Medium", 60
        elif confidence == "Medium":
            confidence, score = "Low",    35
        # Low stays Low
        note += (
            " Model not yet calibrated on real data for this category"
            " — directional estimate."
        )

    return SalesEstimate(
        monthly_sales=monthly_sales,
        low=low,
        high=high,
        confidence=confidence,
        confidence_score=score,
        note=note,
        category_key=cat_key,
    )


def calibrateCategory(
    category: str,
    data_points: List[Tuple[int, int]],
) -> Dict:
    """
    Fit {a, b} for  sales = a * BSR^(-b)  from two or more (BSR, sales) pairs.

    Log-linearise: log(sales) = log(a) + (-b) * log(BSR)
    Use ordinary least squares on the log-log form.

    Returns {"a": float, "b": float} — replace the matching entry in
    CATEGORY_COEFFICIENTS to upgrade from industry estimates to your own data.
    The calibration script (backend/scripts/calibrate_bsr.py) handles the
    full pipeline with R² reporting and the 5-point minimum guard.
    """
    valid = [(bsr, sales) for bsr, sales in data_points if bsr > 0 and sales > 0]
    if len(valid) < 2:
        raise ValueError(
            f"calibrateCategory requires at least 2 positive data points, got {len(valid)}"
        )

    xs = [math.log(bsr)   for bsr, _    in valid]
    ys = [math.log(sales) for _,   sales in valid]
    n  = len(xs)

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n

    num   = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    denom = sum((xs[i] - x_mean) ** 2               for i in range(n))

    if denom == 0:
        raise ValueError("All BSR values are identical — cannot fit a slope.")

    slope = num / denom
    b     = -slope
    a     = math.exp(y_mean - slope * x_mean)

    return {"a": round(a, 2), "b": round(b, 6)}


def estimateNicheDemand(
    bsr_list: List[int],
    category:  str,
    top_n:     int = 10,
) -> Dict:
    """
    Aggregate BSR→sales estimate across the top-N products in a niche.
    Uses the lowest BSRs (highest-demand products) for the estimate.
    """
    valid = sorted(b for b in bsr_list if b > 0)[:top_n]
    if not valid:
        return {
            "total_monthly_sales": 0,
            "avg_monthly_sales":   0,
            "products_sampled":    0,
            "category_key":        normalizeCategory(category),
        }

    estimates = [estimateMonthlySales(b, category) for b in valid]
    total = sum(e.monthly_sales for e in estimates)
    avg   = round(total / len(estimates))

    return {
        "total_monthly_sales": total,
        "avg_monthly_sales":   avg,
        "products_sampled":    len(valid),
        "category_key":        normalizeCategory(category),
    }
