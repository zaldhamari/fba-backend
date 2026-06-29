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
    max_results: int = 10,
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
        # Price: DataForSEO may return price as a plain number OR a dict
        # {"currency": "USD", "value": 29.99} — must unwrap before using.
        price_info_raw = item.get("price_info") or {}
        def _extract_price(raw):
            if raw is None:
                return None
            if isinstance(raw, dict):
                v = raw.get("value") or raw.get("amount") or raw.get("price")
                return float(v) if isinstance(v, (int, float)) and v > 0 else None
            return float(raw) if isinstance(raw, (int, float)) and raw > 0 else None

        price = (
            _extract_price(item.get("price_from"))
            or _extract_price(item.get("price"))
            or _extract_price(price_info_raw.get("current"))
            or _extract_price(price_info_raw.get("price"))
            or _extract_price(item.get("price_to"))
            or _extract_price(price_info_raw.get("regular_price"))
        )

        # Rating: returned as {"value": 4.5, "votes_count": 1234} or plain float
        rating_raw  = item.get("rating")
        rating_val  = rating_raw.get("value")   if isinstance(rating_raw, dict) else rating_raw
        votes_count = rating_raw.get("votes_count") if isinstance(rating_raw, dict) else None

        # Reviews: try several field names; fall back to votes_count from rating dict
        def _to_int(v):
            return int(v) if isinstance(v, (int, float)) and v > 0 else None

        reviews = (
            _to_int(item.get("reviews_count"))
            or _to_int((item.get("reviews_info") or {}).get("reviews_count"))
            or _to_int(item.get("rating_count"))
            or _to_int(votes_count)
        )
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

        # BSR — first entry is the primary category rank
        bsr_list     = item.get("bestseller_rank") or []
        bsr_entry    = bsr_list[0] if bsr_list else {}
        bsr_rank     = bsr_entry.get("rank")
        bsr_category = bsr_entry.get("category")

        # Price discount (Amazon's strike-through / coupon)
        price_info   = item.get("price_info") or {}
        discount_pct = price_info.get("savings_percent")
        list_price   = price_info.get("list_price")

        # Real product category from DataForSEO breadcrumb
        categories    = item.get("categories") or []
        real_category = categories[0].get("name") if categories else None

        # Whether Amazon itself sells this listing (vs third-party FBA seller)
        sold_by_amazon = isinstance(seller, dict) and seller.get("type") == "amazon"

        # Number of variations (size/color/etc.) — signals listing maturity
        variations_count = item.get("variations_count")

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
            "bsr":               bsr_rank,
            "bsr_category":      bsr_category,
            "category":          real_category,
            "discount_pct":      discount_pct,
            "list_price":        list_price,
            "sold_by_amazon":    sold_by_amazon,
            "variations_count":  variations_count,
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
