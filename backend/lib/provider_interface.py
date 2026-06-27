"""
Base interfaces and abstract classes for data providers.

All data providers (DataForSEO, Alibaba, Global Sources, etc.) implement
these interfaces so the router can swap between them seamlessly.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


class ProviderType(str, Enum):
    """Supported data provider types."""
    DATAFORSEO = "dataforseo"
    ALIBABA_API = "alibaba_api"
    GLOBAL_SOURCES = "globalsources"
    MADEINCHINA = "madeinchina"
    TRADEKEY = "tradekey"
    AI_ESTIMATE = "ai_estimate"
    FALLBACK_ESTIMATE = "fallback_estimate"
    KEYWORD_ESTIMATE = "keyword_estimate"
    STUB = "stub"


class ProviderStatus(str, Enum):
    """Operational status of a provider."""
    AVAILABLE = "available"        # Ready to use
    DEGRADED = "degraded"          # Working but slow/limited
    RATE_LIMITED = "rate_limited"  # Hit daily limit
    UNAVAILABLE = "unavailable"    # API down or credentials invalid
    NOT_CONFIGURED = "not_configured"  # Credentials not provided


class DataSourceConfig:
    """
    Configuration for a single data provider.

    Example:
        config = DataSourceConfig(
            provider=ProviderType.DATAFORSEO,
            enabled=True,
            api_key="xyz123",
            priority=1,  # Try this first
            rate_limit_per_day=1000,
            cost_per_request=0.001,
            fallback_chain=[ProviderType.ALIBABA_API, ProviderType.AI_ESTIMATE],
        )
    """

    def __init__(
        self,
        provider: ProviderType,
        enabled: bool = False,
        api_key: Optional[str] = None,
        priority: int = 100,  # 1 = highest priority
        rate_limit_per_day: int = 10000,
        cost_per_request: float = 0.0,
        fallback_chain: Optional[List[ProviderType]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.provider = provider
        self.enabled = enabled
        self.api_key = api_key
        self.priority = priority
        self.rate_limit_per_day = rate_limit_per_day
        self.cost_per_request = cost_per_request
        self.fallback_chain = fallback_chain or []
        self.metadata = metadata or {}
        self.daily_requests_used = 0
        self.daily_reset_at = datetime.utcnow().isoformat()

    def is_available(self) -> bool:
        """Check if provider is enabled and has capacity."""
        return self.enabled and self.daily_requests_used < self.rate_limit_per_day

    def get_status(self) -> ProviderStatus:
        """Get current operational status."""
        if not self.enabled:
            return ProviderStatus.NOT_CONFIGURED
        if not self.api_key and self.provider not in [ProviderType.AI_ESTIMATE, ProviderType.FALLBACK_ESTIMATE, ProviderType.STUB]:
            return ProviderStatus.NOT_CONFIGURED
        if self.daily_requests_used >= self.rate_limit_per_day:
            return ProviderStatus.RATE_LIMITED
        return ProviderStatus.AVAILABLE


class ProductProvider(ABC):
    """Base class for product search providers."""

    @abstractmethod
    async def search_products(
        self,
        keyword: str,
        marketplace: str = "US",
        max_results: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Search for products.

        Returns list of dicts with keys:
        - title (str)
        - price (float)
        - rating (float, optional)
        - review_count (int, optional)
        - asin (str, optional)
        - url (str)
        - source (str) — should be set to self.provider_type()
        - [other provider-specific fields]
        """
        pass

    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the provider type constant."""
        pass


class SupplierProvider(ABC):
    """Base class for supplier search providers."""

    @abstractmethod
    async def search_suppliers(
        self,
        product: str,
        marketplace: str = "US",
        max_unit_price: Optional[float] = None,
        max_moq: Optional[int] = None,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search for suppliers.

        Returns list of dicts with keys:
        - title (str) — supplier/product name
        - supplier (str) — company name
        - price_range (tuple) — (min, max) unit price
        - moq (int) — minimum order quantity
        - rating (float, optional)
        - verified (bool, optional)
        - trade_assurance (bool, optional)
        - years_on_platform (int, optional)
        - source (str) — should be set to self.provider_type()
        - [other provider-specific fields]
        """
        pass

    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the provider type constant."""
        pass


class ProviderRouter:
    """
    Routes requests to providers based on configuration and fallback chain.

    Usage:
        router = ProviderRouter(config_dict)

        # Search products — tries primary provider, falls back automatically
        products = await router.search_products("yoga mat")

        # Get provider status for UI
        status = router.get_provider_status(ProviderType.DATAFORSEO)
    """

    def __init__(self, providers_config: Dict[ProviderType, DataSourceConfig]):
        """
        Initialize router with provider configs.

        Args:
            providers_config: {
                ProviderType.DATAFORSEO: DataSourceConfig(...),
                ProviderType.ALIBABA_API: DataSourceConfig(...),
                ...
            }
        """
        self.configs = providers_config
        self.providers = {}  # Will be populated by subclass/factory

    def get_provider_chain(self, provider_type: ProviderType) -> List[ProviderType]:
        """
        Get the full fallback chain for a provider.

        Returns: [provider_type, fallback_1, fallback_2, ..., stub]
        """
        config = self.configs.get(provider_type)
        if not config:
            return [ProviderType.STUB]
        return [provider_type] + config.fallback_chain + [ProviderType.STUB]

    def get_provider_status(self, provider_type: ProviderType) -> ProviderStatus:
        """Get current status of a provider."""
        config = self.configs.get(provider_type)
        if not config:
            return ProviderStatus.NOT_CONFIGURED
        return config.get_status()

    def get_available_providers(self, category: str) -> List[ProviderType]:
        """
        Get list of available providers in priority order.

        Args:
            category: "products" or "suppliers"

        Returns: [ProviderType, ...] sorted by priority (1 = highest)
        """
        available = [
            (ptype, cfg.priority)
            for ptype, cfg in self.configs.items()
            if cfg.is_available() and self._provider_supports_category(ptype, category)
        ]
        available.sort(key=lambda x: x[1])
        return [ptype for ptype, _ in available]

    @staticmethod
    def _provider_supports_category(provider_type: ProviderType, category: str) -> bool:
        """Check if provider supports the requested category."""
        # This would be expanded to map providers to capabilities
        if category == "products":
            return provider_type in [
                ProviderType.DATAFORSEO,
                ProviderType.AI_ESTIMATE,
                ProviderType.KEYWORD_ESTIMATE,
            ]
        elif category == "suppliers":
            return provider_type in [
                ProviderType.ALIBABA_API,
                ProviderType.GLOBAL_SOURCES,
                ProviderType.MADEINCHINA,
                ProviderType.FALLBACK_ESTIMATE,
            ]
        return False

    async def increment_usage(self, provider_type: ProviderType, cost: Optional[float] = None) -> None:
        """Track usage for rate limiting and billing."""
        config = self.configs.get(provider_type)
        if config:
            config.daily_requests_used += 1
            if cost:
                # TODO: accumulate cost for billing
                pass
