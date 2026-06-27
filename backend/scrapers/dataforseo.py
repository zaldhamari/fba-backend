"""
DataForSEO client for real Amazon product data.

HOOKUP CHECKLIST (when API key arrives):
  1. Set env vars: DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD
  2. Delete the STUB_MODE block in search_amazon_products()
  3. Uncomment the real API call block

Cost: ~$0.003 per request (Amazon Organic SERP, live endpoint)
Docs: https://docs.dataforseo.com/v3/serp/amazon/organic/live/
"""
import asyncio
import os
import base64
from typing import Optional
import httpx

DATAFORSEO_BASE = "https://api.dataforseo.com/v3"

MARKETPLACE_TO_LOCATION: dict[str, tuple[int, str]] = {
    "US": (2840,  "en"),
    "UK": (2826,  "en"),
    "DE": (2276,  "de"),
    "CA": (2124,  "en"),
    "AU": (2036,  "en"),
}


def _auth_header() -> str:
    login    = os.environ.get("DATAFORSEO_LOGIN", "")
    password = os.environ.get("DATAFORSEO_PASSWORD", "")
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return f"Basic {token}"


def _is_configured() -> bool:
    return bool(os.environ.get("DATAFORSEO_LOGIN") and os.environ.get("DATAFORSEO_PASSWORD"))


async def search_amazon_products(
    keyword: str,
    marketplace: str = "US",
    max_results: int = 20,
) -> list[dict]:
    """
    Returns real Amazon product listings via DataForSEO SERP API.
    Falls back to stub data when credentials are not configured.
    """
    # ── STUB MODE (remove when API key is set) ─────────────────────────
    if not _is_configured():
        return _stub_results(keyword, marketplace, max_results)
    # ───────────────────────────────────────────────────────────────────

    location_code, language_code = MARKETPLACE_TO_LOCATION.get(marketplace, (2840, "en"))

    payload = [{
        "keyword":       keyword,
        "location_code": location_code,
        "language_code": language_code,
        "depth":         max_results,
    }]

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{DATAFORSEO_BASE}/merchant/amazon/products/live/advanced",
            headers={
                "Authorization": _auth_header(),
                "Content-Type":  "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    items = (
        data.get("tasks", [{}])[0]
            .get("result", [{}])[0]
            .get("items", [])
    )

    products = []
    for item in items:
        if item.get("type") not in ("amazon_serp_element", "amazon_product_info"):
            continue
        price = item.get("price_from") or item.get("price")
        reviews = item.get("reviews_count") or item.get("rating", {}).get("votes_count")
        rating_val = (item.get("rating") or {}).get("value") if isinstance(item.get("rating"), dict) else item.get("rating")
        products.append({
            "title":        item.get("title", ""),
            "price":        price,
            "price_to":     item.get("price_to"),
            "rating":       rating_val,
            "review_count": reviews,
            "asin":         item.get("asin", ""),
            "image":        item.get("image_url", ""),
            "url":          item.get("url", ""),
            "is_prime":     item.get("is_amazon_choice") or item.get("is_best_seller"),
            "competition":  _competition_label(reviews),
            "opportunity":  _opportunity_label(price, reviews),
            "source":       "dataforseo",
        })

    return products[:max_results]


def _domain_for(marketplace: str) -> str:
    domains = {"US": "amazon.com", "UK": "amazon.co.uk", "DE": "amazon.de",
               "CA": "amazon.ca",  "AU": "amazon.com.au"}
    return domains.get(marketplace, "amazon.com")


def _competition_label(reviews: Optional[int]) -> str:
    if reviews is None:      return "Unknown"
    if reviews < 100:        return "Low"
    if reviews < 500:        return "Medium"
    return "High"


def _opportunity_label(price: Optional[float], reviews: Optional[int]) -> str:
    p = price or 0
    r = reviews or 999
    if r < 200 and p > 20:  return "Good"
    if r > 1000 or p < 12: return "Saturated"
    return "Moderate"


# ── Stub data (realistic shape, fake values) ──────────────────────────────────

def _stub_results(keyword: str, marketplace: str, max_results: int) -> list[dict]:
    import hashlib, math
    seed = int(hashlib.md5(keyword.encode()).hexdigest()[:8], 16)

    results = []
    for i in range(min(max_results, 12)):
        n         = (seed + i * 137) % 997
        price     = round(15 + (n % 80), 2)
        reviews   = 50 + (n * 7 % 900)
        rating    = round(3.5 + (n % 15) / 10, 1)
        comp      = _competition_label(reviews)
        results.append({
            "title":        f"{keyword.title()} — {['Premium', 'Professional', 'Heavy Duty', 'Portable', 'Compact', 'Ergonomic', 'Durable'][i % 7]} Edition",
            "price":        price,
            "price_to":     round(price * 1.3, 2),
            "rating":       min(rating, 5.0),
            "review_count": reviews,
            "asin":         f"B0STUB{n:04d}",
            "image":        "",
            "url":          f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}",
            "is_prime":     i % 3 == 0,
            "competition":  comp,
            "opportunity":  _opportunity_label(price, reviews),
            "source":       "stub",
        })
    return results
