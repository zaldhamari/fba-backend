"""
Data source router — intelligent orchestration of providers with fallback chains.

Handles:
- Provider initialization
- Request routing to highest-priority available provider
- Fallback chain execution
- Usage tracking (rate limiting, cost)
- Error recovery
"""

import os
from typing import Dict, List, Any, Optional
import logging

from backend.modules.ai_client import AI_AVAILABLE
from backend.scrapers.dataforseo import _is_configured as _is_dataforseo_configured, search_amazon_products as dataforseo_search
from backend.scrapers.alibaba_api import search_suppliers as alibaba_search

from .provider_interface import (
    ProviderType,
    ProviderStatus,
    DataSourceConfig,
    ProviderRouter,
)

logger = logging.getLogger(__name__)


class DataSourceRouterImpl(ProviderRouter):
    """
    Concrete implementation of ProviderRouter.

    Automatically initializes based on environment and wires up real providers.
    """

    def __init__(self):
        """
        Initialize router with auto-detection of configured providers.

        Checks environment for DataForSEO, Alibaba, etc.
        Builds fallback chains intelligently.
        """
        # ── Detect available providers ─────────────────────────────────────────
        dataforseo_enabled = _is_dataforseo_configured()
        alibaba_enabled = os.getenv('ALIBABA_ICBU_ENABLED', 'false').lower() == 'true'
        ai_enabled = AI_AVAILABLE

        # ── Build configs ──────────────────────────────────────────────────────
        configs = {
            # Primary real data sources
            ProviderType.DATAFORSEO: DataSourceConfig(
                provider=ProviderType.DATAFORSEO,
                enabled=dataforseo_enabled,
                priority=1,  # Highest priority
                rate_limit_per_day=1000,
                cost_per_request=0.001,
                fallback_chain=[
                    ProviderType.AI_ESTIMATE,
                    ProviderType.KEYWORD_ESTIMATE,
                    ProviderType.STUB,
                ],
            ),
            ProviderType.ALIBABA_API: DataSourceConfig(
                provider=ProviderType.ALIBABA_API,
                enabled=alibaba_enabled,
                priority=1,  # Tie with DataForSEO (first to connect wins)
                rate_limit_per_day=500,
                cost_per_request=0.0,  # Usually free
                fallback_chain=[
                    ProviderType.FALLBACK_ESTIMATE,
                    ProviderType.STUB,
                ],
            ),
            ProviderType.GLOBAL_SOURCES: DataSourceConfig(
                provider=ProviderType.GLOBAL_SOURCES,
                enabled=False,  # Not yet integrated
                priority=2,
                rate_limit_per_day=500,
                fallback_chain=[ProviderType.FALLBACK_ESTIMATE, ProviderType.STUB],
            ),
            ProviderType.MADEINCHINA: DataSourceConfig(
                provider=ProviderType.MADEINCHINA,
                enabled=False,  # Not yet integrated
                priority=3,
                rate_limit_per_day=500,
                fallback_chain=[ProviderType.FALLBACK_ESTIMATE, ProviderType.STUB],
            ),
            # Fallback / estimate sources
            ProviderType.AI_ESTIMATE: DataSourceConfig(
                provider=ProviderType.AI_ESTIMATE,
                enabled=ai_enabled,
                priority=10,  # Lower priority
                rate_limit_per_day=10000,  # High limit, cheap
                cost_per_request=0.0001,
                fallback_chain=[ProviderType.KEYWORD_ESTIMATE, ProviderType.STUB],
            ),
            ProviderType.KEYWORD_ESTIMATE: DataSourceConfig(
                provider=ProviderType.KEYWORD_ESTIMATE,
                enabled=True,  # Always available as fallback
                priority=20,
                rate_limit_per_day=100000,
                fallback_chain=[ProviderType.STUB],
            ),
            ProviderType.FALLBACK_ESTIMATE: DataSourceConfig(
                provider=ProviderType.FALLBACK_ESTIMATE,
                enabled=True,  # Always available
                priority=20,
                rate_limit_per_day=100000,
                fallback_chain=[ProviderType.STUB],
            ),
            ProviderType.STUB: DataSourceConfig(
                provider=ProviderType.STUB,
                enabled=True,  # Always available as absolute fallback
                priority=100,  # Lowest priority
                rate_limit_per_day=100000,
                fallback_chain=[],
            ),
        }

        super().__init__(configs)

    async def search_products(
        self,
        keyword: str,
        marketplace: str = "US",
        max_results: int = 15,
    ) -> Dict[str, Any]:
        """
        Search for products using available providers in priority order.

        Automatically falls back through chain if primary provider fails.

        Returns: {
            "products": [
                {
                    "title": "...",
                    "price": 29.99,
                    "source": "dataforseo",  ← Indicates data source
                    ...
                }
            ],
            "data_source": "dataforseo",  ← Overall source
        }
        """
        # Try providers in order: DataForSEO → AI → Keyword Estimate → Stub
        provider_chain = self.get_provider_chain(ProviderType.DATAFORSEO)

        for provider_type in provider_chain:
            try:
                result = await self._search_products_with_provider(
                    provider_type, keyword, marketplace, max_results
                )
                await self.increment_usage(provider_type)
                return result
            except Exception as e:
                logger.warning(f"Provider {provider_type} failed: {str(e)}, trying next in chain")
                continue

        # Should not reach here (STUB always available), but safe fallback
        return {"products": [], "data_source": "error"}

    async def search_suppliers(
        self,
        product: str,
        marketplace: str = "US",
        max_unit_price: Optional[float] = None,
        max_moq: Optional[int] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for suppliers using available providers in priority order.

        Returns: {
            "suppliers": [
                {
                    "title": "...",
                    "supplier": "Factory XYZ",
                    "source": "alibaba_api",  ← Indicates data source
                    ...
                }
            ],
            "data_source": "alibaba_api",  ← Overall source
        }
        """
        # Try providers in order: Alibaba → Global Sources → Fallback → Stub
        provider_chain = self.get_provider_chain(ProviderType.ALIBABA_API)

        for provider_type in provider_chain:
            try:
                result = await self._search_suppliers_with_provider(
                    provider_type, product, marketplace, max_unit_price, max_moq, max_results
                )
                await self.increment_usage(provider_type)
                return result
            except Exception as e:
                logger.warning(f"Supplier provider {provider_type} failed: {str(e)}, trying next")
                continue

        return {"suppliers": [], "data_source": "error"}

    async def _search_products_with_provider(
        self,
        provider_type: ProviderType,
        keyword: str,
        marketplace: str,
        max_results: int,
    ) -> Dict[str, Any]:
        """Execute product search with a specific provider."""
        if provider_type == ProviderType.DATAFORSEO:
            if not self.configs[provider_type].is_available():
                raise RuntimeError("DataForSEO rate limit reached")
            products = await dataforseo_search(keyword, marketplace, max_results)
            return {"products": products, "data_source": "dataforseo"}

        elif provider_type == ProviderType.AI_ESTIMATE:
            # Would call backend/modules/product_physical.py
            raise NotImplementedError("AI estimate for products not yet implemented")

        elif provider_type == ProviderType.KEYWORD_ESTIMATE:
            # Would call backend/scrapers/amazon.py fallback
            raise NotImplementedError("Keyword estimate products not yet routed")

        elif provider_type == ProviderType.STUB:
            # Minimal stub
            return {
                "products": [
                    {
                        "title": f"Simulated {keyword}",
                        "price": 29.99,
                        "rating": 4.5,
                        "review_count": 500,
                        "source": "stub",
                    }
                ],
                "data_source": "stub",
            }

        raise ValueError(f"Unknown provider: {provider_type}")

    async def _search_suppliers_with_provider(
        self,
        provider_type: ProviderType,
        product: str,
        marketplace: str,
        max_unit_price: Optional[float],
        max_moq: Optional[int],
        max_results: int,
    ) -> Dict[str, Any]:
        """Execute supplier search with a specific provider."""
        if provider_type == ProviderType.ALIBABA_API:
            if not self.configs[provider_type].is_available():
                raise RuntimeError("Alibaba rate limit reached")
            suppliers = await alibaba_search(product, marketplace, max_unit_price, max_moq, max_results)
            return {"suppliers": suppliers, "data_source": "alibaba_api"}

        elif provider_type == ProviderType.GLOBAL_SOURCES:
            # Would call backend/scrapers/globalsources.py (not yet implemented)
            raise NotImplementedError("Global Sources not yet implemented")

        elif provider_type == ProviderType.MADEINCHINA:
            # Would call backend/scrapers/madeinchina.py (not yet implemented)
            raise NotImplementedError("Made-in-China not yet implemented")

        elif provider_type == ProviderType.FALLBACK_ESTIMATE:
            # Deterministic placeholder suppliers
            return {
                "suppliers": [
                    {
                        "title": f"Factory XYZ - {product}",
                        "supplier": "Estimated Supplier",
                        "price_range": (5.0, 15.0),
                        "moq": 100,
                        "rating": 4.2,
                        "verified": False,
                        "source": "fallback_estimate",
                    }
                ],
                "data_source": "fallback_estimate",
            }

        elif provider_type == ProviderType.STUB:
            return {
                "suppliers": [
                    {
                        "title": f"Stub Supplier - {product}",
                        "supplier": "Test Supplier",
                        "price_range": (4.0, 12.0),
                        "moq": 100,
                        "rating": None,
                        "verified": False,
                        "source": "stub",
                    }
                ],
                "data_source": "stub",
            }

        raise ValueError(f"Unknown supplier provider: {provider_type}")

    def get_status_report(self) -> Dict[str, Any]:
        """
        Get status report of all providers for Settings screen.

        Returns: {
            "providers": [
                {
                    "type": "dataforseo",
                    "name": "DataForSEO",
                    "status": "available",
                    "enabled": True,
                    "priority": 1,
                    "daily_usage": 42/1000,
                    "cost_per_request": 0.001,
                },
                ...
            ],
            "overall_data_quality": "mixed",  ← real + estimates
        }
        """
        report = {
            "providers": [],
            "real_data_available": False,
            "ai_estimate_available": AI_AVAILABLE,
        }

        for ptype, config in sorted(self.configs.items(), key=lambda x: x[1].priority):
            status = config.get_status()
            report["providers"].append({
                "type": ptype.value,
                "status": status.value,
                "enabled": config.enabled,
                "priority": config.priority,
                "daily_usage": f"{config.daily_requests_used}/{config.rate_limit_per_day}",
                "cost_per_request": config.cost_per_request,
            })
            if status == ProviderStatus.AVAILABLE and ptype in [ProviderType.DATAFORSEO, ProviderType.ALIBABA_API]:
                report["real_data_available"] = True

        return report


# Singleton instance
_router_instance: Optional[DataSourceRouterImpl] = None


def get_router() -> DataSourceRouterImpl:
    """Get or create the singleton router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = DataSourceRouterImpl()
    return _router_instance
