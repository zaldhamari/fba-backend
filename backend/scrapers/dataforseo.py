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
import hashlib
import os
import re
import base64
from typing import Optional
import httpx

DATAFORSEO_BASE = "https://api.dataforseo.com/v3"

MARKETPLACE_TO_LOCATION: dict[str, tuple[int, str]] = {
    "US": (2840,  "en_US"),
    "UK": (2826,  "en_GB"),
    "DE": (2276,  "de_DE"),
    "CA": (2124,  "en_CA"),
    "AU": (2036,  "en_AU"),
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

    location_code, language_code = MARKETPLACE_TO_LOCATION.get(marketplace, (2840, "en_US"))

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
        # Skip paid/sponsored slots; merchant API returns type "amazon_serp"
        item_type = item.get("type", "")
        if item_type in ("amazon_paid", "amazon_sponsored"):
            continue
        if not item.get("title"):
            continue
        price = item.get("price_from") or item.get("price") or (item.get("price_info") or {}).get("current")
        reviews = item.get("reviews_count") or item.get("reviews_info", {}).get("reviews_count")
        rating_raw = item.get("rating")
        rating_val = rating_raw.get("value") if isinstance(rating_raw, dict) else rating_raw
        # Extract ASIN: prefer explicit field, then parse from URL, then hash title
        asin = item.get("asin", "") or ""
        if not asin:
            url_str = item.get("url", "") or ""
            m = re.search(r'/dp/([A-Z0-9]{10})', url_str)
            asin = m.group(1) if m else ""
        if not asin:
            title_key = (item.get("title") or "").encode()
            asin = "SX" + hashlib.md5(title_key).hexdigest()[:8].upper()
        images_list = item.get("images")
        image_url = item.get("image_url") or (images_list[0] if images_list else None)
        # Seller name → brand fallback
        seller = item.get("seller") or {}
        brand = item.get("brand") or (seller.get("name") if isinstance(seller, dict) else None)
        # Units bought past month (Amazon's "X+ bought in past month" label)
        bought_past_month = (
            item.get("bought_recommended_count")
            or item.get("monthly_purchases")
            or item.get("purchases_30d")
        )
        is_best_seller   = bool(item.get("is_best_seller"))
        is_amazon_choice = bool(item.get("is_amazon_choice"))
        products.append({
            "title":             item.get("title", ""),
            "price":             price,
            "price_to":          item.get("price_to"),
            "rating":            rating_val,
            "review_count":      reviews,
            "asin":              asin,
            "image":             image_url,
            "url":               item.get("url", ""),
            "brand":             brand,
            "bought_past_month": bought_past_month,
            "is_best_seller":    is_best_seller,
            "is_amazon_choice":  is_amazon_choice,
            "is_prime":          is_amazon_choice or is_best_seller,
            "competition":       _competition_label(reviews),
            "opportunity":       _opportunity_label(price, reviews, bought_past_month),
            "source":            "dataforseo",
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


def _opportunity_label(price: Optional[float], reviews: Optional[int], bought_past_month: Optional[int] = None) -> str:
    p = price or 0
    # Use real purchase signal when available
    if bought_past_month and bought_past_month > 0:
        if bought_past_month > 500 and p > 20:  return "Good"
        if bought_past_month > 2000:             return "Saturated"
        return "Moderate"
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
            "brand":        f"Brand{i+1}",
            "bought_past_month": 50 + (n * 3 % 400),
            "is_best_seller":   i == 0,
            "is_amazon_choice": i == 1,
            "is_prime":         i % 3 == 0,
            "competition":  comp,
            "opportunity":  _opportunity_label(price, reviews),
            "source":       "stub",
        })
    return results
