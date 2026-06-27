"""
Backend library modules for data source abstraction and orchestration.

Provides:
- provider_interface: Base classes and configuration for data providers
- data_source_router: Concrete router implementation with fallback chains
- search_orchestrator: Unified entry points for product and supplier searches
"""

from .provider_interface import (
    ProviderType,
    ProviderStatus,
    DataSourceConfig,
    ProviderRouter,
)
from .data_source_router import DataSourceRouterImpl, get_router
from .search_orchestrator import (
    search_amazon_products,
    search_suppliers,
    get_data_sources_status,
)

__all__ = [
    "ProviderType",
    "ProviderStatus",
    "DataSourceConfig",
    "ProviderRouter",
    "DataSourceRouterImpl",
    "get_router",
    "search_amazon_products",
    "search_suppliers",
    "get_data_sources_status",
]
