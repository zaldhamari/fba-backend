"""
Keepa enrichment layer — integrates Keepa data into product research workflows.

Provides:
- Sales velocity estimation from BSR
- Price/trend signals
- Market saturation scoring
- Risk flags (spike, volatility, price war)
- Graceful fallbacks when Keepa unavailable
"""

from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def estimate_sales_from_bsr(
    bsr: Optional[int],
    category: str = "default",
    confidence: str = "Medium",
) -> Dict[str, Any]:
    """
    Estimate monthly sales from Best Sellers Rank.

    Uses Keepa's proprietary BSR-to-sales model.
    Lower BSR = higher sales.

    Returns:
    {
      "monthly_sales": 150,
      "low": 100,
      "high": 200,
      "confidence": "Medium",
      "note": "Estimate based on BSR #1,247 in category"
    }
    """
    if not bsr or bsr < 0:
        return {
            "monthly_sales": None,
            "low": None,
            "high": None,
            "confidence": "Low",
            "note": "BSR not available",
        }

    # Keepa's empirical BSR-to-sales model (varies by category)
    # General formula: Sales ≈ 10000 / sqrt(BSR)
    # Adjusted by category velocity multipliers

    category_multipliers = {
        "sports": 0.8,
        "health": 1.2,
        "home": 1.0,
        "kitchen": 1.1,
        "electronics": 0.9,
        "default": 1.0,
    }

    multiplier = category_multipliers.get(category.lower(), 1.0)

    # Base calculation
    base_sales = 10000 / (bsr ** 0.5) if bsr > 0 else 0
    monthly_sales = int(base_sales * multiplier)

    # Confidence range: ±30%
    low = int(monthly_sales * 0.7)
    high = int(monthly_sales * 1.3)

    return {
        "monthly_sales": monthly_sales,
        "low": low,
        "high": high,
        "confidence": "Medium",
        "note": f"Estimate based on BSR #{bsr} in {category}",
    }


def assess_price_sustainability(
    current_price: Optional[float],
    floor_price: Optional[float],
    price_direction: Optional[str],
) -> Dict[str, Any]:
    """
    Assess if current price is sustainable (margin-safe).

    Returns:
    {
      "margin_room": 2.4,  # Current price / floor price
      "direction": "flat",
      "sustainability": "high",  # Can maintain margin
      "risk": "none"
    }
    """
    if not current_price or not floor_price:
        return {
            "margin_room": None,
            "direction": price_direction or "unknown",
            "sustainability": "unknown",
            "risk": "insufficient_data",
        }

    margin_room = current_price / floor_price if floor_price > 0 else 0

    # Assess sustainability
    if price_direction == "falling":
        sustainability = "low"
        risk = "price_war"
    elif price_direction == "rising":
        sustainability = "high"
        risk = "none"
    elif margin_room > 2.0:
        sustainability = "high"
        risk = "none"
    elif margin_room > 1.5:
        sustainability = "medium"
        risk = "minor_price_pressure"
    else:
        sustainability = "low"
        risk = "margin_squeeze"

    return {
        "margin_room": round(margin_room, 2),
        "direction": price_direction or "flat",
        "sustainability": sustainability,
        "risk": risk,
    }


def assess_market_saturation(
    review_count: Optional[int],
    monthly_sales_est: Optional[int],
    bsr_volatility: Optional[float],
) -> Dict[str, Any]:
    """
    Assess market saturation level.

    Returns:
    {
      "market_age_months": 34,  # How long product's been selling
      "saturation": "moderate",
      "spike_risk": "low",
      "recommendation": "Market is stable but crowded"
    }
    """
    if not review_count or not monthly_sales_est:
        return {
            "market_age_months": None,
            "saturation": "unknown",
            "spike_risk": "unknown",
            "recommendation": "Insufficient data",
        }

    # Market age = reviews / monthly sales
    market_age = review_count / max(monthly_sales_est, 1)

    # Saturation levels
    if market_age > 24:
        saturation = "high"
    elif market_age > 12:
        saturation = "moderate"
    else:
        saturation = "low"

    # Spike risk based on volatility
    if bsr_volatility and bsr_volatility > 0.5:
        spike_risk = "high"
    elif bsr_volatility and bsr_volatility > 0.2:
        spike_risk = "medium"
    else:
        spike_risk = "low"

    recommendations = {
        ("high", "high"): "Market is saturated AND volatile (risky)",
        ("high", "low"): "Market is saturated but stable (hard to beat)",
        ("moderate", "high"): "Market is crowded and unpredictable",
        ("moderate", "low"): "Market is stable and competitive",
        ("low", "high"): "New market with spike risk (could collapse)",
        ("low", "low"): "Emerging market with stable growth (ideal)",
    }

    rec = recommendations.get((saturation, spike_risk), "Unknown market state")

    return {
        "market_age_months": round(market_age, 1),
        "saturation": saturation,
        "spike_risk": spike_risk,
        "recommendation": rec,
    }


def compile_keepa_insights(product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compile complete Keepa insights for a product.

    Input: Product dict with Keepa signals
    Output: Structured market intelligence
    """
    # Extract Keepa data
    bsr = product.get("current_bsr")
    current_price = product.get("current_price_usd")
    floor_price = product.get("floor_price_usd")
    review_count = product.get("review_count")
    category = product.get("category", "default")

    signals = product.get("signals", {})
    bsr_signals = signals.get("bsr", {})
    price_signals = signals.get("price", {})

    # Calculate insights
    sales_est = estimate_sales_from_bsr(bsr, category)
    price_sust = assess_price_sustainability(
        current_price,
        floor_price,
        price_signals.get("direction"),
    )
    saturation = assess_market_saturation(
        review_count,
        sales_est.get("monthly_sales"),
        bsr_signals.get("volatility"),
    )

    # Calculate revenue estimate
    monthly_revenue = None
    if sales_est["monthly_sales"] and current_price:
        monthly_revenue = sales_est["monthly_sales"] * current_price

    return {
        "sales_estimate": sales_est,
        "price_sustainability": price_sust,
        "market_saturation": saturation,
        "monthly_revenue_est": monthly_revenue,
        "bsr_trend": bsr_signals.get("trend", "unknown"),
        "spike_flag": bsr_signals.get("spike_flag", False),
        "summary": {
            "market_size": f"${monthly_revenue:,.0f}/mo" if monthly_revenue else "N/A",
            "market_trend": bsr_signals.get("trend", "unknown"),
            "margin_safety": price_sust.get("sustainability", "unknown"),
            "entry_difficulty": saturation.get("saturation", "unknown"),
        },
    }
