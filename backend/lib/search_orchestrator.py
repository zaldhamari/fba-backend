"""
Search Orchestrator — unified interface for product and supplier searches.

Replaces direct calls to api.searchAmazon(), api.searchSuppliers(), etc.
with intelligent routing through the data source abstraction layer.

All existing routes (routes.py) should delegate to these orchestrator functions.
This makes it trivial to add new providers, swap priorities, or change fallback chains.
"""

from typing import Dict, Any, Optional
import logging
import time

from .data_source_router import get_router

logger = logging.getLogger(__name__)

# ── Backend search cache (TTL: 10 min) ────────────────────────────────────────
# Skips DataForSEO/Alibaba calls entirely for repeated searches.
# Resets on Railway restart (~every deployment), which is fine.
_SEARCH_CACHE_TTL = 600  # seconds
_search_cache: Dict[str, tuple] = {}  # key → (expires_at, result)

def _cache_get(key: str):
    entry = _search_cache.get(key)
    if entry and time.time() < entry[0]:
        return entry[1]
    return None

def _cache_set(key: str, result) -> None:
    _search_cache[key] = (time.time() + _SEARCH_CACHE_TTL, result)
    # Evict oldest if over 200 entries
    if len(_search_cache) > 200:
        oldest = min(_search_cache.items(), key=lambda x: x[1][0])
        _search_cache.pop(oldest[0], None)


async def search_amazon_products(
    keyword: str,
    marketplace: str = "US",
    max_results: int = 15,
) -> Dict[str, Any]:
    """
    Unified product search orchestrator.

    Automatically tries: DataForSEO → AI estimate → Keyword estimate → Stub

    Returns: {
        "keyword": "yoga mat",
        "marketplace": "US",
        "products": [
            {
                "title": "...",
                "price": 29.99,
                "rating": 4.5,
                "review_count": 1200,
                "asin": "B123...",
                "source": "dataforseo",  ← Real data indicator
                ...
            },
            ...
        ],
        "data_source": "dataforseo",  ← What was used for whole search
        "total_results": 42,
    }
    """
    cache_key = f"amazon:{keyword.lower().strip()}:{marketplace}:{max_results}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"[cache HIT] {cache_key}")
        return cached

    router = get_router()

    try:
        result = await router.search_products(keyword, marketplace, max_results)

        # Enrich response with metadata
        response = {
            **result,
            "keyword": keyword,
            "marketplace": marketplace,
            "total_results": len(result.get("products", [])),
            "request_id": f"{keyword}-{marketplace}",  # For debugging/tracking
        }
        # Only cache successful results (not errors)
        if result.get("data_source") != "error":
            _cache_set(cache_key, response)
        return response
    except Exception as e:
        logger.error(f"search_amazon_products failed: {str(e)}")
        return {
            "products": [],
            "data_source": "error",
            "keyword": keyword,
            "marketplace": marketplace,
            "total_results": 0,
            "error": str(e),
        }


async def search_suppliers(
    product: str,
    marketplace: str = "US",
    max_unit_price: Optional[float] = None,
    max_moq: Optional[int] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    Unified supplier search orchestrator.

    Automatically tries: Alibaba → Global Sources → Fallback → Stub

    Returns: {
        "product": "yoga mat",
        "suppliers": [
            {
                "title": "Eco Yoga Mat - 1000+ per month",
                "supplier": "Sunshine Factory",
                "price_range": (3.50, 6.00),
                "moq": 500,
                "rating": 4.7,
                "verified": True,
                "years_on_platform": 8,
                "source": "alibaba_api",  ← Real data indicator
                ...
            },
            ...
        ],
        "data_source": "alibaba_api",  ← What was used
        "total_suppliers": 23,
    }
    """
    cache_key = f"suppliers:{product.lower().strip()}:{marketplace}:{max_unit_price}:{max_results}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"[cache HIT] {cache_key}")
        return cached

    router = get_router()

    try:
        result = await router.search_suppliers(
            product, marketplace, max_unit_price, max_moq, max_results
        )

        # Enrich response
        response = {
            **result,
            "product": product,
            "marketplace": marketplace,
            "total_suppliers": len(result.get("suppliers", [])),
            "filters_applied": {
                "max_unit_price": max_unit_price,
                "max_moq": max_moq,
            },
        }
        if result.get("data_source") != "error":
            _cache_set(cache_key, response)
        return response
    except Exception as e:
        logger.error(f"search_suppliers failed: {str(e)}")
        return {
            "suppliers": [],
            "data_source": "error",
            "product": product,
            "marketplace": marketplace,
            "total_suppliers": 0,
            "error": str(e),
        }




async def get_data_sources_status() -> Dict[str, Any]:
    """
    Get status of all configured data sources for Settings screen.

    Returns: {
        "providers": [
            {
                "type": "dataforseo",
                "name": "DataForSEO - Real Amazon Data",
                "status": "available",
                "enabled": True,
                "priority": 1,
                "daily_usage": "42/1000",
                "cost_per_request": 0.001,
                "category": "products",
                "connect_url": "https://app.dataforseo.com/...",
            },
            ...
        ],
        "real_data_available": True,  ← User should see this
        "ai_estimate_available": True,
        "summary": "✓ Live data connected. Using DataForSEO + AI estimates.",
    }
    """
    router = get_router()
    report = router.get_status_report()

    # Add friendly names and connection URLs
    provider_metadata = {
        "dataforseo": {
            "name": "DataForSEO — Real Amazon Data",
            "category": "products",
            "connect_url": "https://app.dataforseo.com/integration",
            "docs": "https://docs.dataforseo.com/amazon",
        },
        "alibaba_api": {
            "name": "Alibaba API — Real Supplier Data",
            "category": "suppliers",
            "connect_url": "https://www.alibaba.com/trade-api",
            "docs": "https://www.alibaba.com/trade-api/doc",
        },
        "globalsources": {
            "name": "Global Sources — Verified Suppliers",
            "category": "suppliers",
            "connect_url": "https://www.globalsources.com/api",
            "docs": None,  # Coming soon
        },
        "madeinchina": {
            "name": "Made-in-China — Direct Factories",
            "category": "suppliers",
            "connect_url": "https://www.made-in-china.com/api",
            "docs": None,  # Coming soon
        },
        "ai_estimate": {
            "name": "AI Estimation — Claude AI",
            "category": "attributes",
            "enabled": report.get("ai_estimate_available"),
            "docs": None,
        },
    }

    # Enrich providers with metadata
    for provider in report.get("providers", []):
        ptype = provider["type"]
        if ptype in provider_metadata:
            provider.update(provider_metadata[ptype])

    # Generate summary for UI
    if report.get("real_data_available"):
        summary = "✓ Live data connected. Using real provider data + AI estimates as fallback."
    elif report.get("ai_estimate_available"):
        summary = "🤖 Using AI-generated estimates and data. Connect to DataForSEO or Alibaba for real data."
    else:
        summary = "⚠ No real data or AI available. Using placeholder data for testing."

    return {
        **report,
        "summary": summary,
        "recommendation": "Connect DataForSEO for real Amazon data" if not report.get("real_data_available") else None,
    }
