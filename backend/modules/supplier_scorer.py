"""
Supplier Intelligence — scores suppliers and generates negotiation strategies.
Uses AI for negotiation strategy if available; rule-based scoring always runs.
"""
from backend.modules.ai_client import chat_json, AI_AVAILABLE


def score_supplier(
    supplier_name: str,
    price_per_unit: float,
    moq: int,
    years_experience: int = 0,
    response_time_hours: int = 24,
    has_certifications: bool = False,
    product_name: str = "",
    target_order_qty: int = 500,
) -> dict:
    scores = _score_components(price_per_unit, moq, years_experience,
                               response_time_hours, has_certifications)
    total = round(
        scores["price_score"] * 0.25 +
        scores["moq_score"] * 0.20 +
        scores["experience_score"] * 0.20 +
        scores["responsiveness_score"] * 0.20 +
        scores["trust_score"] * 0.15,
        1,
    )

    flags = _risk_flags(price_per_unit, moq, years_experience,
                        response_time_hours, has_certifications, product_name)
    grade = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"

    negotiation = _negotiation_strategy(
        supplier_name, product_name, price_per_unit,
        moq, target_order_qty, total
    )

    return {
        "supplier_name": supplier_name,
        "total_score": total,
        "grade": grade,
        "score_breakdown": scores,
        "risk_flags": flags,
        "recommendation": _recommendation(total, flags),
        "negotiation_strategy": negotiation,
    }


def _score_components(price, moq, experience, response_h, certs) -> dict:
    # Price score: lower is better relative to typical FBA supplier range
    if price < 3:
        price_score = 40  # suspiciously cheap
    elif price <= 8:
        price_score = 100
    elif price <= 15:
        price_score = 75
    elif price <= 25:
        price_score = 50
    else:
        price_score = 25

    # MOQ score: smaller MOQ = lower risk for first-time buyers
    if moq <= 100:
        moq_score = 100
    elif moq <= 300:
        moq_score = 80
    elif moq <= 500:
        moq_score = 65
    elif moq <= 1000:
        moq_score = 45
    else:
        moq_score = 20

    # Experience
    if experience >= 10:
        exp_score = 100
    elif experience >= 5:
        exp_score = 80
    elif experience >= 2:
        exp_score = 55
    elif experience >= 1:
        exp_score = 35
    else:
        exp_score = 20

    # Responsiveness
    if response_h <= 4:
        resp_score = 100
    elif response_h <= 12:
        resp_score = 80
    elif response_h <= 24:
        resp_score = 60
    elif response_h <= 48:
        resp_score = 35
    else:
        resp_score = 10

    trust_score = 80 if certs else 40

    return {
        "price_score": price_score,
        "moq_score": moq_score,
        "experience_score": exp_score,
        "responsiveness_score": resp_score,
        "trust_score": trust_score,
    }


def _risk_flags(price, moq, experience, response_h, certs, product) -> list[str]:
    flags = []
    if price < 3:
        flags.append("Price is suspiciously low — quality risk, verify with sample")
    if moq > 1000:
        flags.append("High MOQ increases capital risk for first orders")
    if experience < 2:
        flags.append("Supplier has limited experience — higher fulfilment risk")
    if response_h > 48:
        flags.append("Slow response time — may cause delays during production issues")
    if not certs and product.lower() in ["baby", "toy", "food", "supplement", "cosmetic"]:
        flags.append("No certifications listed — required for this product category")
    return flags


def _recommendation(score: float, flags: list) -> str:
    if score >= 80 and not flags:
        return "Strong supplier. Request a sample and proceed to negotiation."
    if score >= 65:
        return "Viable supplier with some risk. Order sample, verify quality before committing."
    if score >= 50:
        return "Marginal. Use only if no better options. Negotiate hard on price and MOQ."
    return "High risk. Seek alternative suppliers before proceeding."


def _negotiation_strategy(supplier_name, product, price, moq, target_qty, score) -> dict:
    if AI_AVAILABLE:
        try:
            system = "You are an expert Amazon FBA sourcing agent. Write concise supplier negotiation tactics."
            user = f"""Supplier: {supplier_name} | Product: {product}
Current price: ${price}/unit | Current MOQ: {moq} | Target order: {target_qty} units
Supplier score: {score}/100

Return JSON:
{{
  "opening_offer": "suggested first offer price as string",
  "target_price": "realistic target after negotiation",
  "moq_ask": "what MOQ to request",
  "leverage_points": ["point 1", "point 2", "point 3"],
  "email_opener": "2-sentence opening for negotiation email",
  "red_lines": ["non-negotiable requirement 1", "requirement 2"]
}}"""
            return chat_json(system, user, max_tokens=400)
        except Exception:
            pass

    # Rule-based fallback
    target_price = round(price * 0.82, 2)
    opening = round(price * 0.72, 2)
    return {
        "opening_offer": f"${opening}/unit",
        "target_price": f"${target_price}/unit",
        "moq_ask": str(max(100, moq // 2)),
        "leverage_points": [
            f"You're evaluating {3} suppliers simultaneously",
            "Promise repeat orders if quality meets expectations",
            "Offer faster payment (30% deposit vs standard 50%)",
        ],
        "email_opener": (
            f"We're impressed with your listing for {product or 'this product'} and "
            f"are ready to move forward. For an initial trial order of {target_qty} units, "
            f"could you offer ${target_price}/unit?"
        ),
        "red_lines": [
            "Sample must pass quality inspection before bulk order",
            "Lead time must be confirmed in writing before deposit",
        ],
    }
