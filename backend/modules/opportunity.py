from backend.modules.fba_calculator import calculate_fba_fees


def score_opportunity(
    amazon_price: float,
    supplier_price: float,
    review_count: int,
    trend_direction: str,
    weight_lbs: float,
    category: str,
) -> dict:
    # Calculate real profit first
    fba = calculate_fba_fees(
        selling_price=amazon_price,
        supplier_cost=supplier_price,
        weight_lbs=weight_lbs,
        dimensions={"length": 10, "width": 6, "height": 2},
        category=category,
    )

    profit = fba["profit"]
    margin = fba["margin_pct"]
    roi = fba["roi_pct"]

    # Score components (each out of 100)
    # 1. Profit margin score
    if margin >= 40:
        margin_score = 100
    elif margin >= 25:
        margin_score = 70 + (margin - 25) * 2
    elif margin >= 10:
        margin_score = 30 + (margin - 10) * 2.7
    else:
        margin_score = max(0, margin * 3)

    # 2. Competition score (based on review count)
    if review_count < 50:
        comp_score = 100
    elif review_count < 200:
        comp_score = 80
    elif review_count < 500:
        comp_score = 55
    elif review_count < 1000:
        comp_score = 30
    else:
        comp_score = 10

    # 3. Trend score
    trend_scores = {"Rising": 100, "Stable": 60, "Declining": 20, "No data": 50, "Unknown": 50}
    trend_score = trend_scores.get(trend_direction, 50)

    # 4. Price point score (sweet spot $15-$60)
    if 15 <= amazon_price <= 60:
        price_score = 100
    elif 10 <= amazon_price < 15 or 60 < amazon_price <= 100:
        price_score = 65
    else:
        price_score = 30

    # Weighted total
    total = (
        margin_score * 0.40 +
        comp_score * 0.30 +
        trend_score * 0.20 +
        price_score * 0.10
    )
    total = round(min(100, max(0, total)), 1)

    # Grade
    if total >= 75:
        grade = "A"
        label = "Strong Opportunity"
        color = "green"
    elif total >= 55:
        grade = "B"
        label = "Moderate Opportunity"
        color = "orange"
    elif total >= 35:
        grade = "C"
        label = "Weak Opportunity"
        color = "red"
    else:
        grade = "D"
        label = "Avoid"
        color = "red"

    # Action recommendation
    if total >= 75:
        action = "This looks like a solid product to pursue. Order samples and validate."
    elif total >= 55:
        action = "Promising but competitive. Look for a way to differentiate your product."
    elif total >= 35:
        action = "Margins are thin or competition is high. Keep looking."
    else:
        action = "Not recommended. Low profit and/or very saturated market."

    return {
        "score": total,
        "grade": grade,
        "label": label,
        "color": color,
        "action": action,
        "breakdown": {
            "margin_score": round(margin_score, 1),
            "competition_score": round(comp_score, 1),
            "trend_score": round(trend_score, 1),
            "price_score": round(price_score, 1),
        },
        "profit_summary": {
            "profit": profit,
            "margin_pct": margin,
            "roi_pct": roi,
        },
    }
