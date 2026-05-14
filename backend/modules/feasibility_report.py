"""
Feasibility Report — synthesises all saved data for one product into a
structured go/no-go report.
"""
from backend.modules.ai_client import chat_json, AI_AVAILABLE


def generate_feasibility_report(
    product_name: str,
    amazon_price: float | None = None,
    supplier_analysis: dict | None = None,
    calculation: dict | None = None,
    brand: dict | None = None,
    keywords: dict | None = None,
    freight: dict | None = None,
    marketplace: str = "US",
    currency: str = "USD",
) -> dict:
    if AI_AVAILABLE:
        return _ai_report(product_name, amazon_price, supplier_analysis, calculation, brand, keywords, freight, marketplace, currency)
    return _fallback_report(product_name, calculation)


def _build_context(
    product_name, amazon_price, supplier_analysis, calculation, brand, keywords, freight, marketplace, currency
) -> str:
    lines = [f"Product: {product_name}", f"Marketplace: {marketplace} | Currency: {currency}"]

    if amazon_price:
        lines.append(f"Amazon selling price: {currency} {amazon_price:.2f}")

    if supplier_analysis:
        supplier = supplier_analysis.get("supplier_name") or supplier_analysis.get("title", "Unknown supplier")
        price = supplier_analysis.get("price_per_unit") or supplier_analysis.get("supplier_cost")
        moq = supplier_analysis.get("moq", "Unknown")
        lines.append(f"Supplier: {supplier}, unit cost: {currency} {price}, MOQ: {moq}")

    if calculation:
        lines.append(
            f"Profit calculation: net profit {currency} {calculation.get('netProfit', 0):.2f}, "
            f"margin {calculation.get('margin', 0):.1f}%, ROI {calculation.get('roi', 0):.1f}%, "
            f"selling price {currency} {calculation.get('sellingPrice', 0):.2f}, "
            f"supplier cost {currency} {calculation.get('supplierCost', 0):.2f}"
        )

    if freight:
        lines.append(
            f"Freight: {freight.get('companyName', 'Unknown')}, "
            f"mode: {freight.get('mode', 'Unknown')}, "
            f"${freight.get('costPerUnit', 0):.2f}/unit, "
            f"transit: {freight.get('transitDays', 'Unknown')}"
        )

    if brand:
        lines.append(
            f"Brand: {brand.get('brand_name', 'Unknown')}, "
            f"tagline: \"{brand.get('tagline', '')}\", "
            f"listing title: \"{brand.get('listing_title', '')}\""
        )

    if keywords:
        kw_list = keywords.get("keywords", [])
        top_kws = ", ".join(k.get("phrase", k) if isinstance(k, dict) else k for k in kw_list[:6])
        lines.append(f"SEO keywords ({keywords.get('total', len(kw_list))} found): {top_kws}")

    # Determine data completeness
    fields = [amazon_price, supplier_analysis, calculation, freight, brand, keywords]
    filled = sum(1 for f in fields if f is not None)
    completeness = "full" if filled >= 5 else "partial" if filled >= 3 else "limited"
    lines.append(f"\nData completeness: {completeness} ({filled}/6 sections provided)")

    return "\n".join(lines), completeness


def _ai_report(product_name, amazon_price, supplier_analysis, calculation, brand, keywords, freight, marketplace, currency):
    context, completeness = _build_context(
        product_name, amazon_price, supplier_analysis, calculation, brand, keywords, freight, marketplace, currency
    )

    system = (
        "You are a senior Amazon FBA analyst producing a concise feasibility report for a seller. "
        "Be specific, direct, and data-driven. Focus on whether the numbers work and what the seller "
        "must do next. Never give vague advice. Base your verdict on the actual data provided."
    )

    user = f"""Produce a feasibility report for this FBA product based on the data below.

{context}

Return JSON exactly matching this structure:
{{
  "verdict": "GO" | "CAUTION" | "NO-GO",
  "confidence": <integer 0-100>,
  "headline": "<one punchy sentence summarising the opportunity>",
  "sections": [
    {{
      "title": "Financial Summary",
      "body": "<2-3 sentences on profit, margin, ROI — be specific with numbers>"
    }},
    {{
      "title": "Key Risks",
      "items": ["<specific risk 1>", "<specific risk 2>", "<specific risk 3>"]
    }},
    {{
      "title": "Strengths",
      "items": ["<specific strength 1>", "<specific strength 2>", "<specific strength 3>"]
    }},
    {{
      "title": "Brand & Listing Readiness",
      "body": "<assessment of brand, keywords, and listing positioning if data available, else note what is missing>"
    }},
    {{
      "title": "Next Steps",
      "items": ["<concrete action 1>", "<concrete action 2>", "<concrete action 3>"]
    }}
  ],
  "data_completeness": "{completeness}"
}}"""

    try:
        result = chat_json(system, user, max_tokens=800)
        result.setdefault("data_completeness", completeness)
        return result
    except Exception:
        return _fallback_report(product_name, calculation, completeness)


def _fallback_report(product_name: str, calculation: dict | None, completeness: str = "limited") -> dict:
    if calculation:
        margin = calculation.get("margin", 0)
        profit = calculation.get("netProfit", 0)
        verdict = "GO" if margin >= 30 else "CAUTION" if margin >= 15 else "NO-GO"
        headline = f"{product_name} shows {margin:.0f}% margin — {'strong opportunity' if margin >= 30 else 'tight margins, proceed carefully'}."
    else:
        verdict = "CAUTION"
        headline = f"Insufficient data to fully evaluate {product_name}. Add more data points."

    return {
        "verdict": verdict,
        "confidence": 50,
        "headline": headline,
        "sections": [
            {"title": "Financial Summary", "body": f"Profit: {calculation.get('netProfit', 0):.2f}, margin {calculation.get('margin', 0):.0f}%, ROI {calculation.get('roi', 0):.0f}%." if calculation else "No calculation data available."},
            {"title": "Key Risks", "items": ["Verify supplier quality before bulk order", "Confirm Amazon category is not restricted", "Validate demand with BSR research"]},
            {"title": "Strengths", "items": ["Product identified and validated", "Initial research complete"]},
            {"title": "Brand & Listing Readiness", "body": "Complete brand and keyword setup to improve listing performance."},
            {"title": "Next Steps", "items": ["Order product samples", "Run a full FBA profit calculation", "Complete your brand kit in the Brand tab"]},
        ],
        "data_completeness": completeness,
    }
