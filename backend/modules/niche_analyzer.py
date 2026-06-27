"""
Niche Intelligence engine — turns raw Amazon SERP data into a structured verdict.

Produces the NicheReport shape consumed by the frontend NicheReport component:
  verdict | market_snapshot | the_gap | products_to_model | can_you_afford_it
"""
from typing import Optional


def analyze_niche(
    keyword: str,
    products: list[dict],
    budget: int,
    price_min: float,
    price_max: float,
    max_top_seller_reviews: int,
    marketplace: str = "US",
) -> dict:
    """
    Derives a niche intelligence report from a list of Amazon product results.
    All inputs are real (from DataForSEO) or stub — logic is the same either way.
    """
    if not products:
        return _empty_report(keyword)

    # ── Market snapshot metrics ───────────────────────────────────────────────
    prices    = [p["price"] for p in products if p.get("price")]
    reviews   = [p["review_count"] for p in products if p.get("review_count") is not None]
    ratings   = [p["rating"]       for p in products if p.get("rating") is not None]

    avg_price   = round(sum(prices) / len(prices), 2)   if prices   else 0
    avg_reviews = round(sum(reviews) / len(reviews))     if reviews  else 0
    avg_rating  = round(sum(ratings) / len(ratings), 1)  if ratings  else 0
    top_reviews = max(reviews) if reviews else 0
    min_reviews = min(reviews) if reviews else 0

    in_price_range = [
        p for p in products
        if p.get("price") and price_min <= p["price"] <= price_max
    ]
    low_comp = [p for p in products if (p.get("review_count") or 999) < max_top_seller_reviews]

    # ── Verdict ───────────────────────────────────────────────────────────────
    verdict = _derive_verdict(
        avg_price, avg_reviews, top_reviews, max_top_seller_reviews,
        price_min, price_max, budget,
    )

    # ── The Gap — weaknesses to exploit ──────────────────────────────────────
    gap = _derive_gap(products, avg_rating)

    # ── Products to model (best fit for user's price + competition filters) ──
    modellable = sorted(
        [p for p in in_price_range if (p.get("review_count") or 999) < max_top_seller_reviews],
        key=lambda x: (x.get("review_count") or 999),
    )[:5]

    # ── Can you afford it ─────────────────────────────────────────────────────
    target_unit_cost = round(avg_price * 0.28, 2)  # 28% of sell price → unit cost
    min_order_cost   = target_unit_cost * 100        # assume 100-unit MOQ
    can_afford       = budget >= min_order_cost

    return {
        "keyword":   keyword,
        "marketplace": marketplace,
        "verdict": verdict,
        "market_snapshot": {
            "avg_price":       avg_price,
            "avg_reviews":     avg_reviews,
            "avg_rating":      avg_rating,
            "top_reviews":     top_reviews,
            "total_products":  len(products),
            "in_price_range":  len(in_price_range),
            "low_competition": len(low_comp),
        },
        "the_gap":             gap,
        "products_to_model":   modellable,
        "can_you_afford_it": {
            "budget":           budget,
            "target_unit_cost": target_unit_cost,
            "min_order_cost":   round(min_order_cost, 2),
            "can_afford":       can_afford,
            "verdict":          "Yes — within budget" if can_afford else f"Stretch — need ~${round(min_order_cost - budget):,} more",
        },
    }


def _derive_verdict(
    avg_price: float,
    avg_reviews: int,
    top_reviews: int,
    max_reviews: int,
    price_min: float,
    price_max: float,
    budget: int,
) -> dict:
    score = 0
    reasons = []
    warnings = []

    if top_reviews < max_reviews:
        score += 2
        reasons.append(f"Top seller has only {top_reviews:,} reviews — beatable")
    elif avg_reviews < max_reviews * 0.6:
        score += 1
        reasons.append(f"Average {avg_reviews:,} reviews — some opportunity")
    else:
        warnings.append(f"Top seller has {top_reviews:,} reviews — high barrier to entry")

    if price_min <= avg_price <= price_max:
        score += 2
        reasons.append(f"Avg price ${avg_price:.0f} fits your target range")
    elif avg_price < price_min:
        warnings.append(f"Market avg ${avg_price:.0f} is below your target — margin may be tight")
    else:
        score += 1
        reasons.append(f"Market avg ${avg_price:.0f} is above your min — potential for value play")

    if avg_price * 100 * 0.28 <= budget:
        score += 1
        reasons.append("First order fits your budget")
    else:
        warnings.append(f"First order may strain budget — consider starting smaller")

    if score >= 4:
        label, color = "Strong Opportunity", "green"
    elif score >= 2:
        label, color = "Moderate Opportunity", "amber"
    else:
        label, color = "Challenging Market", "red"

    return {
        "label":    label,
        "color":    color,
        "score":    score,
        "reasons":  reasons,
        "warnings": warnings,
    }


def _derive_gap(products: list[dict], avg_rating: float) -> list[str]:
    gaps = []
    low_rated = [p for p in products if p.get("rating") and p["rating"] < 4.0]
    if low_rated:
        gaps.append(f"{len(low_rated)} products rated under 4★ — quality gap to exploit")

    if avg_rating < 4.2:
        gaps.append("Category average rating is below 4.2★ — customers want better")

    high_reviews_only = all(
        (p.get("review_count") or 0) > 500 for p in products[:5]
    )
    if high_reviews_only:
        gaps.append("Top 5 products are entrenched — look for long-tail keyword variations")

    price_spread = max(
        (p["price"] for p in products if p.get("price")), default=0
    ) - min(
        (p["price"] for p in products if p.get("price")), default=0
    )
    if price_spread > 30:
        gaps.append(f"${price_spread:.0f} price spread in market — room to own a price point")

    if not gaps:
        gaps.append("Market is fairly well-served — differentiate on branding and listing quality")

    return gaps


def _empty_report(keyword: str) -> dict:
    return {
        "keyword":   keyword,
        "marketplace": "US",
        "verdict":   {"label": "No Data", "color": "grey", "score": 0, "reasons": [], "warnings": ["No products found for this keyword"]},
        "market_snapshot": {},
        "the_gap":   [],
        "products_to_model": [],
        "can_you_afford_it": {},
    }
