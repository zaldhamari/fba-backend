"""
Alibaba Open Platform API client for real supplier data.

HOOKUP CHECKLIST (when API credentials are approved, 1-3 business days):
  1. Set env vars: ALIBABA_APP_KEY, ALIBABA_APP_SECRET
  2. Delete the STUB_MODE block in search_suppliers()
  3. Uncomment the real API call block

Docs: https://openapi.alibaba.com/doc/api.htm
App registration: https://openapi.alibaba.com/
Free tier: 10,000 calls/day
"""
import asyncio
import hashlib
import hmac
import os
import time
from typing import Optional
import httpx

_APP_KEY    = os.environ.get("ALIBABA_APP_KEY", "")
_APP_SECRET = os.environ.get("ALIBABA_APP_SECRET", "")

ALIBABA_GATEWAY = "https://eco.taobao.com/router/rest"

MARKETPLACE_TO_CURRENCY = {
    "US": "USD", "UK": "GBP", "DE": "EUR", "CA": "CAD", "AU": "AUD",
}


def _is_configured() -> bool:
    return bool(_APP_KEY and _APP_SECRET)


def _sign(params: dict[str, str], secret: str) -> str:
    sorted_pairs = sorted(params.items())
    raw = secret + "".join(f"{k}{v}" for k, v in sorted_pairs) + secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


async def search_suppliers(
    product: str,
    marketplace: str = "US",
    max_unit_price: Optional[float] = None,
    max_moq: Optional[int] = None,
    max_results: int = 10,
) -> list[dict]:
    """
    Returns real Alibaba supplier listings.
    Falls back to stub data when credentials are not configured.
    """
    # ── STUB MODE (remove when API credentials are approved) ───────────
    if not _is_configured():
        return _stub_results(product, marketplace, max_unit_price, max_moq, max_results)
    # ───────────────────────────────────────────────────────────────────

    params = {
        "method":        "alibaba.icbu.product.search",
        "app_key":       _APP_KEY,
        "timestamp":     str(int(time.time() * 1000)),
        "format":        "json",
        "v":             "2.0",
        "sign_method":   "md5",
        "keywords":      product,
        "page_index":    "1",
        "page_size":     str(min(max_results, 20)),
        "sort_type":     "BEST_MATCH",
    }
    if max_unit_price:
        params["price_from"] = "0"
        params["price_to"]   = str(max_unit_price)

    params["sign"] = _sign(params, _APP_SECRET)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(ALIBABA_GATEWAY, data=params)
        resp.raise_for_status()
        data = resp.json()

    raw_items = (
        data.get("alibaba_icbu_product_search_response", {})
            .get("result", {})
            .get("products", {})
            .get("product", [])
    )

    currency = MARKETPLACE_TO_CURRENCY.get(marketplace, "USD")
    suppliers = []
    for item in raw_items:
        price_range = item.get("priceRange", {})
        p_min = float(price_range.get("from", 0))
        p_max = float(price_range.get("to", p_min * 1.3))

        moq_val = int(item.get("minOrderQuantity", 100))
        if max_moq and moq_val > max_moq:
            continue

        suppliers.append({
            "title":         item.get("subject", product.title()),
            "supplier":      item.get("companyName", "Alibaba Supplier"),
            "price_range":   {"min": round(p_min, 2), "max": round(p_max, 2)},
            "price_display": f"${p_min:.2f} – ${p_max:.2f} /unit",
            "moq":           moq_val,
            "moq_display":   f"{moq_val}+ units",
            "rating":        item.get("supplierRating"),
            "image":         item.get("imageUrl", ""),
            "url":           item.get("productUrl", ""),
            "verified":      item.get("isVerified", False),
            "trade_assurance": item.get("isTradeAssurance", False),
            "years_on_platform": item.get("yearsOnPlatform"),
            "source":        "alibaba_api",
        })

    return suppliers[:max_results]


# ── Stub data ─────────────────────────────────────────────────────────────────

_SUPPLIER_NAMES = [
    "Guangzhou Premier Mfg", "Shenzhen Excellent Co", "Hangzhou Trade Group",
    "Yiwu Best Export", "Zhejiang Quality Goods", "Ningbo Global Supply",
    "Dongguan Pro Mfg", "Foshan Direct Factory", "Jiangsu OEM Specialist",
    "Chengdu Reliable Trade",
]

_PLATFORMS = ["Alibaba", "DHgate", "Made-in-China", "Global Sources", "1688"]


def _stub_results(
    product: str,
    marketplace: str,
    max_unit_price: Optional[float],
    max_moq: Optional[int],
    max_results: int,
) -> list[dict]:
    import hashlib as _h
    seed = int(_h.md5(product.encode()).hexdigest()[:8], 16)

    results = []
    for i in range(min(max_results, len(_SUPPLIER_NAMES))):
        n    = (seed + i * 173) % 997
        p_lo = round(1.5 + (n % 18), 2)
        p_hi = round(p_lo * 1.4, 2)
        moq  = [50, 100, 200, 500][i % 4]

        if max_unit_price and p_lo > max_unit_price:
            continue
        if max_moq and moq > max_moq:
            continue

        results.append({
            "title":           f"{product.title()} — {['OEM Ready', 'Custom Logo', 'Bulk Pack', 'Sample Available', 'Export Ready'][i % 5]}",
            "supplier":        _SUPPLIER_NAMES[i % len(_SUPPLIER_NAMES)],
            "price_range":     {"min": p_lo, "max": p_hi},
            "price_display":   f"${p_lo:.2f} – ${p_hi:.2f} /unit",
            "moq":             moq,
            "moq_display":     f"{moq}+ units",
            "rating":          round(4.0 + (n % 10) / 10, 1),
            "image":           "",
            "url":             f"https://www.alibaba.com/trade/search?SearchText={product.replace(' ', '+')}",
            "verified":        i % 2 == 0,
            "trade_assurance": i % 3 != 0,
            "years_on_platform": 3 + (i % 12),
            "source":          "stub",
        })

    return results
