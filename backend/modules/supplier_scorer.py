"""
Supplier Confidence Index — dynamic, explainable, multi-dimension scoring.

Scores are derived from 6 weighted dimensions that genuinely differentiate
platforms and product risk levels. Rule-based scoring always runs; AI enhances
the negotiation strategy when available.

Expected distribution:
  Elite  (85–95): Global Sources / Made-in-China with low MOQ + ideal price
  Strong (70–84): Alibaba / 1688 with acceptable terms
  Average(50–69): DHgate / AliExpress or any platform with risky terms
  Weak   (25–49): Unknown platform / high MOQ / suspicious price / regulated category
"""
from backend.modules.ai_client import chat_json, AI_AVAILABLE

# ── Platform credibility profiles ──────────────────────────────────────────────
# (credibility 0-100, estimated_response_hours, has_certifications)
# Calibrated so credibility spans 20-95 for genuine score separation.
_PLATFORM_PROFILES: dict[str, tuple[int, int, bool]] = {
    "global sources":  (95,  8, True),   # Curated, vetted exporters — highest trust
    "made-in-china":   (82, 10, True),   # Industrial B2B, ISO certifications common
    "alibaba":         (78, 14, True),   # Large verified network, variable quality
    "1688":            (38,  4, False),  # Domestic China: fast but unverified
    "dhgate":          (48, 22, False),  # Trading companies, slower comms
    "aliexpress":      (32, 20, False),  # Consumer-focused, weaker B2B rigour
}
_UNKNOWN_PLATFORM = (20, 36, False)

# Category risk keyword sets
_HIGH_RISK_KW = {"baby", "infant", "toy", "food", "supplement", "vitamin",
                 "cosmetic", "skincare", "medical", "drug", "edible"}
_MED_RISK_KW  = {"electronic", "battery", "charger", "laser", "knife",
                 "blade", "chemical", "power", "voltage", "circuit"}

# Weights must sum to 1.0
_WEIGHTS = {
    "platform_credibility":  0.32,
    "price_competitiveness": 0.22,
    "moq_accessibility":     0.20,
    "response_quality":      0.12,
    "verification_trust":    0.09,
    "category_fit":          0.05,
}


# ── Dimension scoring functions ────────────────────────────────────────────────

def _resolve_platform(supplier_name: str) -> tuple[int, int, bool]:
    name = supplier_name.lower()
    for platform, profile in _PLATFORM_PROFILES.items():
        if platform in name:
            return profile
    return _UNKNOWN_PLATFORM


def _dim_price(price: float) -> int:
    """Pricing competitiveness (0-100). Sweet spot $3-$12 for FBA viability."""
    if price <= 0:    return 0
    if price < 1.5:   return 8     # Dumped price — serious quality concern
    if price < 2.5:   return 28    # Borderline suspicious
    if price <= 5.0:  return 100   # Ideal FBA sweet spot
    if price <= 10.0: return 88    # Competitive
    if price <= 15.0: return 72    # Reasonable margin pressure
    if price <= 25.0: return 50    # Premium — margin gets thin
    if price <= 40.0: return 30    # High unit cost — niche FBA only
    return 12                       # Very expensive — FBA rarely viable


def _dim_moq(moq: int) -> int:
    """MOQ accessibility (0-100). Lower = less capital at risk."""
    if moq <= 50:    return 100
    if moq <= 100:   return 88
    if moq <= 200:   return 72
    if moq <= 300:   return 58
    if moq <= 500:   return 42
    if moq <= 1000:  return 22
    return 8


def _dim_response(hours: int) -> int:
    """Response speed (0-100). Faster comms = fewer production delays."""
    if hours <= 4:   return 100
    if hours <= 8:   return 85
    if hours <= 12:  return 72
    if hours <= 24:  return 52
    if hours <= 48:  return 28
    return 8


def _dim_trust(has_certs: bool, credibility: int) -> int:
    """Verification & trust (0-100). Certs unlock a higher ceiling."""
    if has_certs:
        return min(int(65 + credibility * 0.30), 100)
    return max(int(20 + credibility * 0.30), 20)


def _dim_category(product_name: str) -> tuple[int, str]:
    """Category safety score + risk level label."""
    pl = product_name.lower()
    if any(k in pl for k in _HIGH_RISK_KW):
        return 15, "high_risk"
    if any(k in pl for k in _MED_RISK_KW):
        return 52, "medium_risk"
    return 88, "low_risk"


# ── Explainability builders ────────────────────────────────────────────────────

def _build_strengths(dims: dict, has_certs: bool, moq: int,
                     price: float, cat_level: str) -> list[str]:
    out = []
    if dims["platform_credibility"] >= 82:
        out.append("Verified supplier network with established export track record")
    elif dims["platform_credibility"] >= 60:
        out.append("Recognized sourcing platform with active buyer community")
    if dims["moq_accessibility"] >= 88:
        out.append(f"Low MOQ ({moq} units) — ideal for product testing with minimal risk")
    elif dims["moq_accessibility"] >= 58:
        out.append(f"Accessible MOQ ({moq} units) — manageable first-order commitment")
    if dims["price_competitiveness"] >= 88:
        out.append("Unit cost sits in FBA profit zone — healthy margin headroom")
    elif dims["price_competitiveness"] >= 72:
        out.append("Competitive pricing for the category — margin is achievable")
    if dims["response_quality"] >= 85:
        out.append("Fast estimated response window — responsive during production issues")
    if has_certs:
        out.append("ISO/CE-certified supply chain — reduced compliance and customs risk")
    if cat_level == "low_risk":
        out.append("Non-regulated product category — no mandatory certification overhead")
    return out[:4]


def _build_risks(dims: dict, has_certs: bool, cat_level: str,
                 moq: int, price: float, resp_h: int, product_name: str) -> list[str]:
    out = []
    if price < 2.5:
        out.append("Unit price is unusually low — request factory audit and paid sample before committing")
    if moq > 500:
        out.append(f"High MOQ ({moq} units) — significant capital exposure on a first or test order")
    if resp_h > 24:
        out.append("Slow estimated response time — factor communication delays into your production schedule")
    if dims["platform_credibility"] < 45:
        out.append("Lower-credibility platform — conduct independent vetting before wire transfer")
    if not has_certs and cat_level == "high_risk":
        out.append(f"Regulated product category with no certification data — compliance verification required before import")
    elif not has_certs and cat_level == "medium_risk":
        out.append("Electronics/chemical category without cert data — confirm compliance before listing")
    if cat_level == "high_risk":
        out.append("High-risk category (baby/food/supplement) — US and EU import regulations are strict")
    if dims["price_competitiveness"] <= 30:
        out.append("High unit cost will compress FBA margin — run a detailed profitability calc before ordering")
    return out


# ── Recommendation & labels ────────────────────────────────────────────────────

def _recommendation(score: float, risks: list) -> str:
    if score >= 85:
        return "Elite supplier. Request a paid sample, confirm lead time in writing, then move to negotiation."
    if score >= 70:
        return "Strong supplier. Order samples to verify quality — clear terms before committing to bulk inventory."
    if score >= 50:
        return "Average. Negotiate hard on price and MOQ. Verify specs independently before any capital commitment."
    return "High risk. Source at least two additional quotes. Use this supplier as price leverage only."


def _confidence_label(score: float) -> str:
    if score >= 85: return "Elite"
    if score >= 70: return "Strong"
    if score >= 50: return "Average"
    return "Weak"


# ── Main scoring function ──────────────────────────────────────────────────────

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
    credibility, est_resp_h, has_certs = _resolve_platform(supplier_name)

    # Caller-supplied explicit values override platform-inferred defaults
    if years_experience > 0:
        credibility = min(credibility + min(years_experience * 3, 25), 100)
    if response_time_hours != 24:
        est_resp_h = response_time_hours
    if has_certifications:
        has_certs = True

    cat_score, cat_level = _dim_category(product_name)

    dims = {
        "platform_credibility":  credibility,
        "price_competitiveness": _dim_price(price_per_unit),
        "moq_accessibility":     _dim_moq(moq),
        "response_quality":      _dim_response(est_resp_h),
        "verification_trust":    _dim_trust(has_certs, credibility),
        "category_fit":          cat_score,
    }

    total = round(sum(dims[k] * _WEIGHTS[k] for k in dims), 1)

    grade = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"

    strengths = _build_strengths(dims, has_certs, moq, price_per_unit, cat_level)
    risks     = _build_risks(dims, has_certs, cat_level, moq, price_per_unit, est_resp_h, product_name)

    return {
        "supplier_name":    supplier_name,
        "total_score":      total,
        "grade":            grade,
        "confidence_label": _confidence_label(total),
        "score_breakdown":  dims,
        "strengths":        strengths,
        "risk_flags":       risks,
        "recommendation":   _recommendation(total, risks),
        "negotiation_strategy": _negotiation_strategy(
            supplier_name, product_name, price_per_unit,
            moq, target_order_qty, total,
        ),
    }


# ── Negotiation strategy ───────────────────────────────────────────────────────

def _negotiation_strategy(supplier_name, product, price, moq, target_qty, score) -> dict:
    if AI_AVAILABLE:
        try:
            system = "You are an expert Amazon FBA sourcing agent. Write concise supplier negotiation tactics."
            user = f"""Supplier: {supplier_name} | Product: {product}
Current price: ${price}/unit | Current MOQ: {moq} | Target order: {target_qty} units
Supplier confidence score: {score}/100

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
    target_price  = round(price * 0.82, 2)
    opening_price = round(price * 0.72, 2)
    return {
        "opening_offer": f"${opening_price}/unit",
        "target_price":  f"${target_price}/unit",
        "moq_ask":       str(max(50, moq // 2)),
        "leverage_points": [
            f"You're evaluating {3} suppliers simultaneously — price will be the deciding factor",
            "Promise repeat orders if quality meets expectations on the first shipment",
            "Offer faster payment terms (30% deposit vs standard 50%) in exchange for a better price",
        ],
        "email_opener": (
            f"We're impressed with your listing for {product or 'this product'} and are prepared to move quickly. "
            f"For an initial trial order of {target_qty} units, could you offer ${target_price}/unit?"
        ),
        "red_lines": [
            "Sample must pass quality inspection before bulk order is confirmed",
            "Lead time and production schedule must be confirmed in writing before deposit",
        ],
    }
