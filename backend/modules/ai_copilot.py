"""
AI Copilot — "Should I launch this product?"
Uses GPT-4o-mini with structured output. Falls back to rule-based if no API key.

Two entry points:
  analyze_product()            — legacy; accepts estimated inputs from the client
  analyze_product_with_keepa() — preferred; accepts real KeepaProduct + SalesEstimate
                                  and uses those numbers as ground truth in the prompt
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


# ── Keepa-aware analysis (Prompt 5) ──────────────────────────────────────────

def analyze_product_with_keepa(
    product,          # KeepaProduct
    sales_est,        # SalesEstimate | None
    supplier_price:   float,
    marketplace:      str          = "US",
    currency:         str          = "USD",
    competition:      str          = "Medium",
    financial_context: Optional[dict] = None,
    signals:          Optional[dict] = None,   # output of keepa_signals.compute_signals()
) -> dict:
    """
    Analyse a product using verified Keepa data as ground truth.

    All numeric inputs (price, review count, BSR, sales estimate) come from
    Keepa — not from client-supplied estimates — so the AI prompt reflects
    the real market state rather than a user's guess.

    When signals (bsr_stability + price_trend) are provided they are folded
    into both the AI prompt and the rule-based scorer. Risk signals are ALWAYS
    raised, never softened — that is the Siftly honesty contract.

    Falls back to rule-based if OpenAI is unavailable.
    """
    current_price = (product.current_price_cents or 0) / 100
    avg90_price   = (product.avg90_price_cents   or 0) / 100

    # Infer price trend label from 90-day average vs current
    if product.avg90_price_cents and product.current_price_cents:
        if product.current_price_cents < product.avg90_price_cents * 0.95:
            price_trend_label = "Falling (current price below 90-day avg)"
        elif product.current_price_cents > product.avg90_price_cents * 1.05:
            price_trend_label = "Rising (current price above 90-day avg)"
        else:
            price_trend_label = "Stable"
    else:
        price_trend_label = "Unknown"

    # Extract signal booleans for the scorer
    bsr_declining = False
    spike_flag    = False
    price_falling = False
    if signals:
        bsr_declining = signals.get("bsr", {}).get("trend") == "declining"
        spike_flag    = bool(signals.get("bsr", {}).get("spike_flag"))
        price_falling = signals.get("price", {}).get("direction") == "falling"

    # Rule-based opportunity score using real numbers + signal penalties
    amazon_price_for_opp = current_price if current_price > 0 else avg90_price
    opp = score_opportunity(
        amazon_price=amazon_price_for_opp or 0,
        supplier_price=supplier_price,
        review_count=product.review_count or 0,
        trend_direction="Rising" if "Rising" in price_trend_label else (
            "Declining" if "Falling" in price_trend_label else "Stable"
        ),
        weight_lbs=1.0,
        category=product.category or "all",
        bsr_declining=bsr_declining,
        spike_flag=spike_flag,
        price_falling=price_falling,
    )

    if AI_AVAILABLE:
        result = _ai_analysis_keepa(
            product=product,
            sales_est=sales_est,
            supplier_price=supplier_price,
            current_price=current_price,
            avg90_price=avg90_price,
            price_trend_label=price_trend_label,
            opp=opp,
            marketplace=marketplace,
            currency=currency,
            competition=competition,
            financial_context=financial_context,
            signals=signals,
        )
        if result:
            return result

    return _rule_based_analysis_keepa(product, sales_est, opp, currency)


def _ai_analysis_keepa(
    product, sales_est, supplier_price,
    current_price, avg90_price, price_trend_label, opp,
    marketplace, currency, competition, financial_context,
    signals=None,
):
    system = (
        "You are a senior Amazon FBA expert with access to verified live market data. "
        "The figures below come from Keepa (real Amazon data) — treat them as ground truth, "
        "not estimates. Give a direct, actionable launch decision. "
        "CRITICAL HONESTY RULE: Any line starting with ⚠ is a verified risk signal from "
        "historical data. You MUST surface these signals prominently in top_risks. "
        "Do NOT downplay, reframe, or omit them. A spike flag or declining BSR means real risk "
        "— present it that way. "
        "When financial context from the seller's Profit Lab is provided, use it for "
        "profit and margin figures; otherwise derive from the data shown. "
        "Never fabricate numbers not present in the data."
    )

    fin_section = (
        _build_financial_section(financial_context, currency)
        if financial_context else ""
    )

    bsr_line     = f"BSR: {product.current_bsr:,}" if product.current_bsr else "BSR: N/A"
    reviews_line = f"{product.review_count:,}" if product.review_count else "N/A"
    rating_line  = f"{product.rating}/5" if product.rating else "N/A"
    sales_range  = (
        f"{sales_est.low}–{sales_est.high}/mo "
        f"(point: {sales_est.monthly_sales}, {sales_est.confidence} confidence)"
        if sales_est else "N/A"
    )

    # Build signal warning block — these must appear as hard facts, not suggestions
    signal_warnings = ""
    if signals:
        warnings = []
        bsr_sig   = signals.get("bsr", {})
        price_sig = signals.get("price", {})
        if bsr_sig.get("trend") == "declining":
            warnings.append("⚠ BSR TREND DECLINING — rank is worsening over time; demand is fading")
        if bsr_sig.get("spike_flag"):
            volatility = bsr_sig.get("volatility")
            vol_str = f", volatility={volatility:.2f}" if volatility is not None else ""
            warnings.append(
                f"⚠ BSR SPIKE DETECTED — recent rank far better than historical median"
                f"{vol_str}; likely a temporary demand event, NOT sustained sales"
            )
        if price_sig.get("direction") == "falling":
            pct = price_sig.get("pct_change_90d")
            pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
            warnings.append(f"⚠ PRICE FALLING{pct_str} — race-to-the-bottom risk; margin pressure likely")
        if warnings:
            signal_warnings = "\n\nRISK SIGNALS (verified from history data — do NOT soften these):\n" + "\n".join(warnings)

    user = f"""VERIFIED KEEPA DATA — {product.asin}

Product:    {product.title or 'Unknown'} ({product.brand or 'Unknown brand'})
Category:   {product.category or 'Unknown'} | Marketplace: {marketplace} | Currency: {currency}
Current price: ${current_price:.2f} | 90-day avg: ${avg90_price:.2f} | Trend: {price_trend_label}
Supplier cost: ${supplier_price:.2f}
Reviews: {reviews_line} | Rating: {rating_line} | Competition: {competition}
{bsr_line} | Est. monthly sales: {sales_range}
Opportunity score: {opp['score']}/100 ({opp['grade']} — {opp['label']}){signal_warnings}{fin_section}

Return JSON with these exact keys:
{{
  "verdict": "Launch" | "Test First" | "Avoid",
  "confidence": 0-100,
  "summary": "2-sentence plain-English decision referencing the real data",
  "top_risks": ["risk 1", "risk 2", "risk 3"],
  "differentiation": ["specific improvement idea 1", "idea 2", "idea 3"],
  "launch_strategy": "2-sentence recommended approach",
  "estimated_monthly_revenue": number (monthly_sales × current_price),
  "estimated_monthly_profit": number (conservative, after fees and ads in {currency})
}}"""

    try:
        result = chat_json(system, user, max_tokens=700)
        result["opportunity_score"] = opp["score"]
        result["profit_summary"]    = opp["profit_summary"]
        result["data_source"]       = "keepa"
        return result
    except Exception:
        return None


def _rule_based_analysis_keepa(product, sales_est, opp, currency):
    score  = opp["score"]
    margin = opp["profit_summary"]["margin_pct"]

    if score >= 75:
        verdict, confidence = "Launch", 82
        summary = (
            f"{product.title or product.asin} shows strong fundamentals — "
            f"{margin:.0f}% margin and {sales_est.monthly_sales if sales_est else 'solid'} "
            "estimated monthly sales."
        )
    elif score >= 55:
        verdict, confidence = "Test First", 62
        summary = (
            f"{product.title or product.asin} has potential but warrants validation. "
            "Order a small sample batch and test demand before scaling."
        )
    else:
        verdict, confidence = "Avoid", 75
        summary = (
            f"{product.title or product.asin} shows weak margins or high competition. "
            "Continue searching — better opportunities exist."
        )

    risks = []
    if (product.review_count or 0) > 500:
        risks.append(f"Top listings have {product.review_count:,} reviews — hard to compete without heavy PPC")
    if margin < 25:
        risks.append("Thin margin leaves little room for PPC spend and returns")
    if sales_est and sales_est.confidence == "Low":
        risks.append("Low BSR-data confidence — validate sales volume before committing inventory")
    if not risks:
        risks = ["Monitor competitor pricing weekly", "Plan PPC budget carefully before launch"]

    monthly_profit = round(opp["profit_summary"]["profit"] * (sales_est.monthly_sales if sales_est else 150))
    monthly_revenue = round(
        ((product.current_price_cents or 0) / 100) * (sales_est.monthly_sales if sales_est else 150)
    )

    return {
        "verdict":   verdict,
        "confidence": confidence,
        "summary":   summary,
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
        "estimated_monthly_revenue":          monthly_revenue,
        "estimated_monthly_profit":           monthly_profit,
        "estimated_monthly_profit_currency":  currency,
        "opportunity_score": opp["score"],
        "profit_summary":    opp["profit_summary"],
        "data_source":       "keepa",
    }
