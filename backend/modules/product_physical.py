"""
Estimates physical shipping attributes (weight, dimensions, category) for a
product when real measured data isn't available.

Neither real-data path already wired into this backend returns this:
DataForSEO's Amazon Organic SERP endpoint returns search-result cards (title,
price, rating, reviews) — not full product-detail specs like item weight or
package dimensions. Alibaba's `alibaba.icbu.product.search` returns price/MOQ/
supplier info, not package weight/dims either — that level of detail usually
has to be negotiated with the supplier directly. So this is the practical
fallback used to pre-populate the FBA calculator instead of leaving weight/
dimensions blank for the user to guess: ask Claude to estimate from the
product title (and price, if known), grounded in how similar physical goods
are actually packaged and shipped.

Always tagged source="ai_estimate" (or "fallback_estimate" if AI is
unavailable) — never presented as measured/confirmed data. The frontend shows
this distinction via EstimateLabel and keeps every field user-editable.
"""
import hashlib
from typing import Optional

from backend.modules.ai_client import chat_json, AI_AVAILABLE

CATEGORIES = [
    "electronics", "home", "kitchen", "sports", "toys",
    "beauty", "clothing", "tools", "books", "all",
]


def estimate_physical_attributes(
    title: str,
    price: Optional[float] = None,
    category: Optional[str] = None,
) -> dict:
    """
    Returns: {weight_lbs, length, width, height, category, confidence, source}

    `length` is always the longest side, in inches. Falls back to a
    deterministic (non-random) generic guess if AI is unavailable or the
    call fails, so the UI always has something to pre-fill rather than
    blocking on a third-party outage.
    """
    if not AI_AVAILABLE:
        return _fallback(title, category)

    try:
        result = chat_json(
            system=(
                "You estimate realistic shipping attributes for e-commerce products sold "
                "on Amazon. Given a product title (and optionally its retail price), return "
                "your best estimate of: typical shipped weight in pounds (including retail "
                "packaging), package dimensions in inches (length = longest side, width, "
                "height), and the single best-fit category from this list: "
                + ", ".join(CATEGORIES) + ". Base this on how similar products are actually "
                "packaged and shipped, not just the bare product size. Respond with JSON only: "
                '{"weight_lbs": number, "length": number, "width": number, "height": number, '
                '"category": string, "confidence": "high"|"medium"|"low"}'
            ),
            user=f"Product: {title}" + (f"\nRetail price: ${price:.2f}" if price else ""),
            max_tokens=200,
        )
        est_category = result.get("category")
        if est_category not in CATEGORIES:
            est_category = category or "all"
        return {
            "weight_lbs": round(float(result.get("weight_lbs", 1.0)), 2),
            "length":     round(float(result.get("length", 10)), 1),
            "width":      round(float(result.get("width", 8)), 1),
            "height":     round(float(result.get("height", 4)), 1),
            "category":   est_category,
            "confidence": result.get("confidence", "medium"),
            "source":     "ai_estimate",
        }
    except Exception:
        return _fallback(title, category)


def _fallback(title: str, category: Optional[str]) -> dict:
    """Deterministic guess — same title always yields the same fallback,
    so refreshing the page doesn't make numbers jump around."""
    seed = int(hashlib.md5(title.lower().strip().encode()).hexdigest()[:6], 16)
    return {
        "weight_lbs": round(0.5 + (seed % 50) / 10, 2),
        "length":     round(8 + (seed % 12), 1),
        "width":      round(6 + (seed % 8), 1),
        "height":     round(2 + (seed % 6), 1),
        "category":   category or "all",
        "confidence": "low",
        "source":     "fallback_estimate",
    }
