from backend.modules.ai_client import chat_json, AI_AVAILABLE

MARKETPLACE_NAMES = {
    "US": "Amazon US",
    "CA": "Amazon Canada",
    "UK": "Amazon UK",
    "DE": "Amazon EU",
    "AE": "Amazon UAE",
    "SA": "Amazon Saudi Arabia",
}


def analyze_product_quick(
    price: float,
    reviews: int,
    competition: str,
    trend: str,
    currency: str = "USD",
    marketplace: str = "US",
) -> dict:
    cost = price / 3.5
    margin = round(((price - cost) / price) * 100, 1)
    marketplace_label = MARKETPLACE_NAMES.get(marketplace.upper(), "Amazon US")

    result = None
    if AI_AVAILABLE:
        result = _ai_analyze(price, reviews, competition, trend, margin, currency, marketplace_label)

    if not result:
        result = _fallback(price, reviews, competition, trend, margin)

    result["metrics"] = {
        "price": price,
        "margin": margin,
        "reviews": reviews,
        "competition": competition,
        "trend": trend,
    }
    return result


def _ai_analyze(price, reviews, competition, trend, margin, currency, marketplace_label):
    system = "You are a senior Amazon FBA analyst. Be direct, specific, and actionable. No fluff."
    user = f"""Analyze this FBA product opportunity. Respond with JSON only — no markdown fences.

Marketplace: {marketplace_label} | Currency: {currency}

Data:
- Price: ${price} USD
- Reviews: {reviews}
- Competition: {competition}
- Trend: {trend}
- Estimated margin: {margin}%

Tailor your verdict and next steps for the {marketplace_label} marketplace. Consider local competition dynamics, fees, and buyer behaviour where relevant.

Return exactly:
{{
  "verdict": "LAUNCH" or "TEST" or "AVOID",
  "confidence": integer 0-100,
  "summary": "one sentence",
  "reasons": ["reason 1", "reason 2", "reason 3"],
  "risk": "single biggest risk",
  "next_step": "one specific action to take now"
}}

Keep total output under 120 words."""

    try:
        return chat_json(system, user, max_tokens=350)
    except Exception:
        return None


def _fallback(price, reviews, competition, trend, margin):
    trend_l = trend.lower()
    comp_l = competition.lower()

    if margin > 30 and reviews < 300 and trend_l == "rising":
        verdict, confidence = "LAUNCH", 78
        reasons = [
            f"{margin:.0f}% margin — healthy after fees and ads",
            f"Only {reviews} reviews — market is still winnable",
            "Rising trend signals growing buyer demand",
        ]
        risk = "Low barriers may attract fast copycats"
        next_step = "Find 3 suppliers on Alibaba and request samples this week"

    elif margin > 20 and comp_l != "high":
        verdict, confidence = "TEST", 55
        reasons = [
            f"{margin:.0f}% margin — workable but monitor ad spend closely",
            f"{reviews} reviews means competition is established",
            f"Trend is {trend} — needs monitoring before full commitment",
        ]
        risk = "PPC costs could erode margin at scale"
        next_step = "Order a test batch of 100–200 units before committing capital"

    else:
        verdict, confidence = "AVOID", 72
        reasons = [
            f"Only {margin:.0f}% margin — too tight once ads and fees are included",
            f"{reviews} reviews signals a saturated, hard-to-enter market",
            f"{trend} trend makes timing unfavourable",
        ]
        risk = "Thin margins leave no room to survive a price war"
        next_step = "Search for a variation or adjacent product at a higher price point"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": f"{verdict} — {margin:.0f}% margin, {reviews} reviews, {trend.lower()} trend",
        "reasons": reasons,
        "risk": risk,
        "next_step": next_step,
    }
