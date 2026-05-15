"""
AI Copilot — "Should I launch this product?"
Uses GPT-4o-mini with structured output. Falls back to rule-based if no API key.
"""
from typing import Optional
from backend.modules.ai_client import chat_json, AI_AVAILABLE
from backend.modules.opportunity import score_opportunity


def _confidence_label(score) -> str:
    if score is None:
        return "Unknown"
    if score >= 80:
        return "High Confidence"
    if score >= 55:
        return "Medium Confidence"
    return "Low Confidence"


def _build_financial_section(fc: dict, currency: str) -> str:
    """Build the financial context block injected into the AI prompt."""
    sym = {"USD": "$", "GBP": "£", "EUR": "€", "CAD": "CA$", "AED": "AED ", "SAR": "SAR "}.get(currency, "$")

    lines = ["", "--- Financial Context from Profit Lab (seller's own calculation) ---"]

    if fc.get("product_name"):
        lines.append(f"Product: {fc['product_name']}")
    mkt = fc.get("marketplace") or "US"
    cur = fc.get("currency") or currency
    lines.append(f"Marketplace: {mkt} | Currency: {cur}")

    if fc.get("selling_price") is not None:
        lines.append(f"Selling price: {sym}{fc['selling_price']:.2f}")
    if fc.get("supplier_cost") is not None:
        lines.append(f"Supplier cost: {sym}{fc['supplier_cost']:.2f}")
    if fc.get("net_profit") is not None:
        lines.append(f"Net profit per unit: {sym}{fc['net_profit']:.2f}")
    if fc.get("margin_pct") is not None:
        lines.append(f"Margin: {fc['margin_pct']:.1f}%")
    if fc.get("roi_pct") is not None:
        lines.append(f"ROI: {fc['roi_pct']:.1f}%")
    if fc.get("confidence_score") is not None:
        score = fc["confidence_score"]
        lines.append(f"Calculation confidence: {score}/100 ({_confidence_label(score)})")
    if fc.get("hs_code"):
        lines.append(f"HS/HTS code: {fc['hs_code']}")
    if fc.get("calculation_date"):
        lines.append(f"Calculated: {fc['calculation_date'][:10]}")

    lines.append("--- End Financial Context ---")
    lines.append(
        "INSTRUCTIONS: Use the financial context above when answering questions about "
        "profit, margin, pricing, inventory risk, and launch viability. "
        "Do NOT invent financial figures not shown above. "
        "Freight, duty, and tax figures in this context are planning estimates — "
        "advise the seller to verify with a freight forwarder or customs broker before ordering. "
        + (
            f"WARNING: The calculation confidence score is {fc['confidence_score']}/100 "
            "({}) — remind the seller to verify their inputs before committing to inventory. ".format(
                _confidence_label(fc["confidence_score"])
            )
            if (fc.get("confidence_score") is not None and fc["confidence_score"] < 55)
            else ""
        )
    )
    return "\n".join(lines)


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
    marketplace: str = "US",
    currency: str = "USD",
    financial_context: Optional[dict] = None,
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
                            competition, opp, marketplace, currency, financial_context)
    return _rule_based_analysis(product_name, opp, review_count,
                                trend_direction, competition, currency)


def _ai_analysis(product_name, amazon_price, supplier_price,
                 review_count, trend_direction, category, competition, opp,
                 marketplace="US", currency="USD", financial_context=None):
    system = (
        "You are a senior Amazon FBA expert. Analyze product data and give a "
        "concise, actionable launch decision. Be direct — sellers need clear signals. "
        "When financial context from the seller's Profit Lab calculation is provided, "
        "prioritise it over estimated figures for profit, margin, ROI, and pricing advice. "
        "Never fabricate financial metrics that are not provided."
    )

    fin_section = (
        _build_financial_section(financial_context, currency)
        if financial_context
        else ""
    )

    user = f"""Product: {product_name}
Category: {category} | Marketplace: {marketplace} | Currency: {currency}
Amazon price: ${amazon_price} | Supplier cost: ${supplier_price}
Profit margin: {opp['profit_summary']['margin_pct']}% | ROI: {opp['profit_summary']['roi_pct']}%
Reviews on top listing: {review_count} | Trend: {trend_direction} | Competition: {competition}
Opportunity score: {opp['score']}/100 ({opp['grade']} — {opp['label']}){fin_section}

Return JSON with these exact keys:
{{
  "verdict": "Launch" | "Test First" | "Avoid",
  "confidence": 0-100,
  "summary": "2-sentence plain-English decision",
  "top_risks": ["risk 1", "risk 2", "risk 3"],
  "differentiation": ["specific improvement idea 1", "improvement idea 2", "improvement idea 3"],
  "launch_strategy": "2-sentence recommended approach",
  "estimated_monthly_profit": number (conservative estimate in {currency})
}}"""

    try:
        result = chat_json(system, user, max_tokens=650)
        result["opportunity_score"] = opp["score"]
        result["profit_summary"] = opp["profit_summary"]
        return result
    except Exception:
        return _rule_based_analysis(product_name, opp, review_count,
                                    trend_direction, competition, currency)


def _rule_based_analysis(product_name, opp, review_count, trend_direction, competition,
                         currency="USD"):
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

    # Rough planning estimate: per-unit profit × ~150 units/month.
    # The value is in the request currency (no conversion applied).
    estimated_monthly_profit = round(opp["profit_summary"]["profit"] * 150)

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
        "estimated_monthly_profit": estimated_monthly_profit,
        "estimated_monthly_profit_currency": currency,
        "opportunity_score": opp["score"],
        "profit_summary": opp["profit_summary"],
    }
