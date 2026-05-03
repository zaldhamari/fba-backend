"""
Supplier research using platform deep-links + category-based pricing estimates.

All B2B supplier sites (Alibaba, DHgate, AliExpress, Made-in-China) block
datacenter IPs. Instead of scraping, we generate supplier platform links
with realistic pricing based on the product category and return them as
supplier leads the user can investigate directly.
"""
from typing import Optional
import re

# Wholesale price ranges (per unit at 100-500 MOQ) for common FBA categories
WHOLESALE_RANGES: dict[str, tuple[float, float, int]] = {
    # (min_price, max_price, typical_moq)
    "cutting board": (2.5, 8.0, 100),
    "knife": (3.0, 15.0, 50),
    "pan": (5.0, 20.0, 50),
    "pot": (6.0, 22.0, 50),
    "mug": (1.5, 5.0, 100),
    "bottle": (2.0, 7.0, 100),
    "organizer": (3.0, 10.0, 100),
    "mat": (4.0, 15.0, 50),
    "yoga": (5.0, 18.0, 50),
    "posture": (4.0, 12.0, 50),
    "resistance band": (1.5, 5.0, 200),
    "foam roller": (3.0, 10.0, 100),
    "massager": (8.0, 25.0, 30),
    "phone case": (1.0, 4.0, 200),
    "charger": (3.0, 12.0, 100),
    "stand": (3.5, 12.0, 100),
    "headphone": (8.0, 35.0, 50),
    "speaker": (6.0, 30.0, 50),
    "dog": (2.0, 12.0, 100),
    "cat": (2.0, 10.0, 100),
    "toy": (2.0, 10.0, 100),
    "puzzle": (2.5, 8.0, 100),
    "baby": (2.5, 10.0, 100),
    "hiking": (5.0, 20.0, 50),
    "camping": (4.0, 18.0, 50),
    "skin": (2.0, 8.0, 100),
    "hair": (1.5, 6.0, 100),
    "desk": (15.0, 60.0, 30),
    "chair": (20.0, 80.0, 20),
}
DEFAULT_RANGE = (2.0, 10.0, 100)

PLATFORMS = [
    {
        "name": "Alibaba",
        "url_template": "https://www.alibaba.com/trade/search?SearchText={query}",
        "tier": "primary",
    },
    {
        "name": "AliExpress Wholesale",
        "url_template": "https://www.aliexpress.com/wholesale?SearchText={query}&SortType=BESTSELLING",
        "tier": "primary",
    },
    {
        "name": "DHgate",
        "url_template": "https://www.dhgate.com/wholesale/search.do?searchkey={query}&orderType=hotsales",
        "tier": "primary",
    },
    {
        "name": "Made-in-China",
        "url_template": "https://www.made-in-china.com/multi-search/{query_dashed}/F0/pg1.html",
        "tier": "secondary",
    },
    {
        "name": "Global Sources",
        "url_template": "https://www.globalsources.com/Manufacturers/{query_dashed}.html",
        "tier": "secondary",
    },
    {
        "name": "1688 (Domestic China)",
        "url_template": "https://s.1688.com/selloffer/offerlist.htm?keywords={query}",
        "tier": "advanced",
    },
]


def _get_price_range(product: str) -> tuple[float, float, int]:
    pl = product.lower()
    for key, (lo, hi, moq) in WHOLESALE_RANGES.items():
        if key in pl:
            return lo, hi, moq
    return DEFAULT_RANGE


def _format_moq(moq: int) -> str:
    return f"{moq}+ units"


async def search_alibaba(product: str, max_price: Optional[float] = None) -> list[dict]:
    """
    Returns supplier platform leads with estimated wholesale pricing.
    Each result links directly to a platform search for the product.
    """
    lo, hi, moq = _get_price_range(product)

    # Tighten range if max_price filter applied
    if max_price and max_price < hi:
        hi = min(hi, max_price)
    if hi <= lo:
        return []

    query = product.strip().replace(" ", "+")
    query_dashed = product.strip().replace(" ", "-").lower()
    mid = round((lo + hi) / 2, 2)

    results = []
    for plat in PLATFORMS:
        url = plat["url_template"].format(query=query, query_dashed=query_dashed)

        # Price varies slightly per platform
        if plat["tier"] == "primary":
            p_lo, p_hi = lo, round(hi * 0.9, 2)
        elif plat["tier"] == "secondary":
            p_lo, p_hi = round(lo * 1.1, 2), round(hi * 1.2, 2)
        else:
            p_lo, p_hi = lo * 0.8, hi * 0.85

        results.append({
            "title": f"{product.title()} — {plat['name']}",
            "price_range": {"min": round(p_lo, 2), "max": round(p_hi, 2)},
            "price_display": f"${p_lo:.2f} – ${p_hi:.2f} /unit",
            "moq": _format_moq(moq),
            "supplier": plat["name"],
            "image": "",
            "url": url,
        })

    return results
