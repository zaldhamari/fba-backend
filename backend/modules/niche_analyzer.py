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

    # ── BSR-based demand estimation ───────────────────────────────────────────
    # Use real BSR data from DataForSEO to estimate actual monthly sales volume.
    bsr_values = [p["bsr"] for p in products if p.get("bsr") and p["bsr"] > 0]
    demand_data = None
    total_monthly_revenue_est = None
    avg_bsr = None
    if bsr_values:
        try:
            from backend.services.bsr_sales_model import estimateNicheDemand, estimateMonthlySales, normalizeCategory
            cats = [p.get("category") or p.get("bsr_category") for p in products if p.get("category") or p.get("bsr_category")]
            primary_cat = cats[0] if cats else "default"
            demand_data = estimateNicheDemand(bsr_values, primary_cat)
            # Per-product revenue estimate for market size
            revenue_sum = 0.0
            for p in products:
                if p.get("bsr") and p.get("price") and p["bsr"] > 0:
                    est = estimateMonthlySales(p["bsr"], primary_cat)
                    revenue_sum += est.monthly_sales * p["price"]
            total_monthly_revenue_est = round(revenue_sum) if revenue_sum else None
            avg_bsr = round(sum(bsr_values) / len(bsr_values))
        except Exception:
            pass

    # How many listings Amazon itself sells (major competition moat signal)
    sold_by_amazon_count = sum(1 for p in products if p.get("sold_by_amazon"))

    # Price war signal: products actively discounting
    discounting_count = sum(1 for p in products if (p.get("discount_pct") or 0) > 5)

    # ── Verdict ───────────────────────────────────────────────────────────────
    verdict = _derive_verdict(
        avg_price, avg_reviews, top_reviews, max_top_seller_reviews,
        price_min, price_max, budget,
        demand_data=demand_data,
        sold_by_amazon_count=sold_by_amazon_count,
    )

    # ── The Gap — weaknesses to exploit ──────────────────────────────────────
    gap = _derive_gap(products, avg_rating, discounting_count, sold_by_amazon_count)

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
            "avg_price":                  avg_price,
            "avg_reviews":                avg_reviews,
            "avg_rating":                 avg_rating,
            "top_reviews":                top_reviews,
            "total_products":             len(products),
            "in_price_range":             len(in_price_range),
            "low_competition":            len(low_comp),
            "avg_bsr":                    avg_bsr,
            "total_monthly_sales_est":    demand_data["total_monthly_sales"] if demand_data else None,
            "avg_monthly_sales_est":      demand_data["avg_monthly_sales"]   if demand_data else None,
            "total_monthly_revenue_est":  total_monthly_revenue_est,
            "sold_by_amazon_count":       sold_by_amazon_count,
            "discounting_count":          discounting_count,
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
    demand_data: dict = None,
    sold_by_amazon_count: int = 0,
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
        warnings.append("First order may strain budget — consider starting smaller")

    # Real demand signal from BSR
    if demand_data and demand_data.get("total_monthly_sales"):
        total = demand_data["total_monthly_sales"]
        avg   = demand_data["avg_monthly_sales"]
        if total > 5000:
            score += 2
            reasons.append(f"Strong demand — ~{total:,} units/mo across top listings")
        elif total > 1000:
            score += 1
            reasons.append(f"Decent demand — ~{total:,} units/mo across top listings")
        else:
            warnings.append(f"Low demand signal — only ~{total:,} units/mo estimated")

    # Amazon itself selling = moat
    if sold_by_amazon_count >= 3:
        warnings.append(f"Amazon sells {sold_by_amazon_count} of these listings directly — hard to compete")
    elif sold_by_amazon_count == 0:
        score += 1
        reasons.append("No Amazon-sold listings — third-party seller market")

    if score >= 6:
        label, color = "Strong Opportunity", "green"
    elif score >= 3:
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


def _derive_gap(
    products: list[dict],
    avg_rating: float,
    discounting_count: int = 0,
    sold_by_amazon_count: int = 0,
) -> list[str]:
    gaps = []
    low_rated = [p for p in products if p.get("rating") and p["rating"] < 4.0]
    if low_rated:
        gaps.append(f"{len(low_rated)} products rated under 4★ — quality gap to exploit")

    if avg_rating < 4.2:
        gaps.append("Category average rating is below 4.2★ — customers want better quality")

    high_reviews_only = all(
        (p.get("review_count") or 0) > 500 for p in products[:5]
    )
    if high_reviews_only:
        gaps.append("Top 5 products are entrenched — target long-tail keyword variations")

    price_spread = max(
        (p["price"] for p in products if p.get("price")), default=0
    ) - min(
        (p["price"] for p in products if p.get("price")), default=0
    )
    if price_spread > 30:
        gaps.append(f"${price_spread:.0f} price spread — room to own a defensible price point")

    # Discounting signal: competitors cutting prices = margin pressure but also desperation
    if discounting_count >= 3:
        gaps.append(f"{discounting_count} sellers are actively discounting — position on value, not price")

    # Few/no variations in top products = opportunity to launch a fuller variant set
    no_variations = [p for p in products if not p.get("variations_count") or p["variations_count"] < 3]
    if len(no_variations) >= len(products) // 2:
        gaps.append("Most top listings have few variations — a multi-variant launch can dominate")

    # High BSR variance = demand is concentrated in a few products (opportunity for split)
    bsr_vals = [p["bsr"] for p in products if p.get("bsr") and p["bsr"] > 0]
    if len(bsr_vals) >= 4:
        best_bsr  = min(bsr_vals)
        worst_bsr = max(bsr_vals)
        if worst_bsr > best_bsr * 10:
            gaps.append(f"BSR range #{best_bsr:,}–#{worst_bsr:,} — demand is concentrated at top; second-place slot is open")

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
