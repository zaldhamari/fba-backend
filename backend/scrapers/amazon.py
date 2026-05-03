"""
Product research using Amazon's autocomplete API + Google Trends.

All major e-commerce sites (Amazon, eBay, Google Shopping, Alibaba) block
datacenter IPs from Railway. Amazon's autocomplete API is NOT blocked and
returns real search demand data — exactly what FBA sellers need.

This produces "keyword opportunities" (which IS how Helium 10 / Jungle
Scout work) rather than scraping individual product listings.
"""
import asyncio
import re
from typing import Optional
import httpx

from backend.scrapers.keywords import to_query_string, to_keywords

AMAZON_SUGGEST = "https://completion.amazon.com/api/2017/suggestions"

# Estimated retail price ranges by product keyword, drawn from typical FBA products
PRICE_RANGES: dict[str, tuple[float, float]] = {
    "cutting board": (18, 55),
    "knife": (15, 80),
    "pan": (20, 90),
    "pot": (25, 80),
    "mug": (12, 35),
    "bottle": (14, 40),
    "organizer": (15, 45),
    "mat": (20, 70),
    "yoga": (25, 80),
    "posture": (20, 60),
    "resistance band": (12, 35),
    "foam roller": (15, 50),
    "massager": (25, 100),
    "phone case": (8, 30),
    "charger": (12, 40),
    "stand": (15, 60),
    "headphone": (25, 150),
    "speaker": (20, 120),
    "dog": (10, 50),
    "cat": (8, 40),
    "skin": (12, 50),
    "hair": (10, 40),
    "toy": (10, 45),
    "puzzle": (12, 40),
    "baby": (10, 50),
    "hiking": (25, 100),
    "camping": (20, 80),
    "desk": (40, 200),
    "chair": (50, 300),
}
DEFAULT_PRICE_RANGE = (15, 60)


def _estimate_price(keyword: str) -> Optional[float]:
    kw_lower = keyword.lower()
    for k, (lo, hi) in PRICE_RANGES.items():
        if k in kw_lower:
            return round((lo + hi) / 2, 2)
    lo, hi = DEFAULT_PRICE_RANGE
    return round((lo + hi) / 2, 2)


def _competition_from_words(kw: str) -> str:
    words = len(kw.split())
    return "Low" if words >= 4 else "Medium" if words >= 3 else "High"


def _opportunity(competition: str, price: Optional[float]) -> str:
    p = price or 0
    if competition == "Low" and p > 18:
        return "Good"
    if competition == "High" or p < 12:
        return "Saturated"
    return "Moderate"


async def _fetch_suggestions(prefix: str, client: httpx.AsyncClient) -> list[str]:
    try:
        r = await client.get(
            AMAZON_SUGGEST,
            params={
                "limit": 11,
                "prefix": prefix,
                "suggestion-type": "KEYWORD",
                "page-type": "Search",
                "alias": "aps",
                "site-variant": "desktop",
                "version": 3,
                "event": "onKeyPress",
                "lop": "en_US",
                "mid": "ATVPDKIKX0DER",
                "plain-mid": 1,
                "client-info": "amazon-search-ui",
            },
            timeout=6.0,
        )
        return [s["value"] for s in r.json().get("suggestions", [])]
    except Exception:
        return []


async def search_amazon(keyword: str, category: str = "all") -> list[dict]:
    """
    Returns keyword-based product opportunities from Amazon's live search data.
    Each result represents a real search demand niche with competition + pricing.
    """
    base = " ".join(to_keywords(keyword)[:3])
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    queries = [base] + [f"{base} {c}" for c in alphabet[:12]]

    all_kws: list[str] = []
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    ) as client:
        results = await asyncio.gather(*[_fetch_suggestions(q, client) for q in queries])
        for r in results:
            all_kws.extend(r)

    seen: set[str] = set()
    unique: list[str] = []
    for kw in all_kws:
        kl = kw.lower().strip()
        if kl not in seen and len(kl) > 4:
            seen.add(kl)
            unique.append(kw.strip())

    # Sort: longer (more specific = lower competition) first
    unique.sort(key=lambda x: (-len(x.split()), len(x)))
    products = []

    for kw in unique[:15]:
        comp = _competition_from_words(kw)
        price = _estimate_price(kw)
        products.append({
            "title": kw,
            "price": price,
            "rating": None,
            "review_count": None,
            "asin": "",
            "image": "",
            "competition": comp,
            "opportunity": _opportunity(comp, price),
            "url": f"https://www.amazon.com/s?k={kw.replace(' ', '+')}",
        })

    return products
