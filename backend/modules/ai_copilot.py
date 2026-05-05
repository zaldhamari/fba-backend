"""
AI Copilot — "Should I launch this product?"
Uses GPT-4o-mini with structured output. Falls back to rule-based if no API key.
"""
from backend.modules.ai_client import chat_json, AI_AVAILABLE
from backend.modules.opportunity import score_opportunity


def analyze_product(
    product_name: str,
    amazon_price: float,
    supplier_price: float,
    review_count: int,
    trend_direction: str,
    weight_lbs: float,
    category: str,
    competition: str = "Medium",
    monthly_sales_est: int = 0,
) -> dict:
    # Always run the rule-based scorer first
    opp = score_opportunity(
        amazon_price=amazon_price,
        supplier_price=supplier_price,
        review_count=review_count,
        trend_direction=trend_direction,
        weight_lbs=weight_lbs,
        category=category,
    )

    if AI_AVAILABLE:
        return _ai_analysis(product_name, amazon_price, supplier_price,
                            review_count, trend_direction, category,
                            competition, opp)
    return _rule_based_analysis(product_name, opp, review_count,
                                trend_direction, competition)


def _ai_analysis(product_name, amazon_price, supplier_price,
                 review_count, trend_direction, category, competition, opp):
    system = (
        "You are a senior Amazon FBA expert. Analyze product data and give a "
        "concise, actionable launch decision. Be direct — sellers need clear signals."
    )
    user = f"""Product: {product_name}
Category: {category}
Amazon price: ${amazon_price} | Supplier cost: ${supplier_price}
Profit margin: {opp['profit_summary']['margin_pct']}% | ROI: {opp['profit_summary']['roi_pct']}%
Reviews on top listing: {review_count} | Trend: {trend_direction} | Competition: {competition}
Opportunity score: {opp['score']}/100 ({opp['grade']} — {opp['label']})

Return JSON with these exact keys:
{{
  "verdict": "Launch" | "Test First" | "Avoid",
  "confidence": 0-100,
  "summary": "2-sentence plain-English decision",
  "top_risks": ["risk 1", "risk 2", "risk 3"],
  "differentiation": ["specific improvement idea 1", "improvement idea 2", "improvement idea 3"],
  "launch_strategy": "2-sentence recommended approach",
  "estimated_monthly_profit": number (conservative estimate in USD)
}}"""

    try:
        result = chat_json(system, user, max_tokens=600)
        result["opportunity_score"] = opp["score"]
        result["profit_summary"] = opp["profit_summary"]
        return result
    except Exception:
        return _rule_based_analysis(product_name, opp, review_count,
                                    trend_direction, competition)


def _rule_based_analysis(product_name, opp, review_count, trend_direction, competition):
    score = opp["score"]
    margin = opp["profit_summary"]["margin_pct"]

    if score >= 75:
        verdict, confidence = "Launch", 82
        summary = (
            f"{product_name} shows strong fundamentals with {margin:.0f}% margin "
            "and manageable competition. Move forward to sample stage."
        )
    elif score >= 55:
        verdict, confidence = "Test First", 62
        summary = (
            f"{product_name} has potential but warrants validation. "
            "Order a small sample batch and test demand before scaling."
        )
    else:
        verdict, confidence = "Avoid", 75
        summary = (
            f"{product_name} has weak margins or high competition. "
            "Continue searching — better opportunities exist."
        )

    risks = []
    if review_count > 500:
        risks.append("High review count on top listings — hard to compete without heavy PPC")
    if margin < 25:
        risks.append("Thin margins leave little room for PPC and returns")
    if trend_direction == "Declining":
        risks.append("Declining trend — demand may shrink before you recoup investment")
    if competition == "High":
        risks.append("Saturated market — differentiation is essential")
    if not risks:
        risks = ["Monitor competitor pricing weekly", "Plan PPC budget carefully"]

    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": summary,
        "top_risks": risks[:3],
        "differentiation": [
            "Improve packaging and unboxing experience",
            "Add a complementary accessory as a bundle",
            "Target a niche keyword variant with lower competition",
        ],
        "launch_strategy": (
            "Start with a mid-range price to build velocity, "
            "then raise once reviews accumulate."
        ),
        "estimated_monthly_profit": round(opp["profit_summary"]["profit"] * 150),
        "opportunity_score": opp["score"],
        "profit_summary": opp["profit_summary"],
    }
