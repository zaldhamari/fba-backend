"""
Usage quota system — track and enforce per-user API limits.

Tier-based limits:
- Free: 5 niche, 10 product, 3 teardown searches/month
- Starter: 30 niche, 50 product, 20 teardown (Keepa limited to 5)
- Professional: 100 niche, 200 product, 100 teardown (Keepa 50)
- Power: Unlimited

Resets on: First day of month (or user's subscription renew date)
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# Tier definitions
TIER_QUOTAS = {
    "free": {
        "niche_searches": 5,
        "product_searches": 10,
        "keepa_lookups": 0,
        "teardowns": 3,
        "monthly_cost_usd": 0,
    },
    "starter": {
        "niche_searches": 30,
        "product_searches": 50,
        "keepa_lookups": 5,
        "teardowns": 20,
        "monthly_cost_usd": 4.99,
    },
    "professional": {
        "niche_searches": 100,
        "product_searches": 200,
        "keepa_lookups": 50,
        "teardowns": 100,
        "monthly_cost_usd": 9.99,
    },
    "power": {
        "niche_searches": -1,  # unlimited
        "product_searches": -1,
        "keepa_lookups": -1,
        "teardowns": -1,
        "monthly_cost_usd": 19.99,
    },
}


class UserQuota:
    """Track a user's monthly usage and enforce limits."""

    def __init__(self, user_id: str, tier: str = "free"):
        self.user_id = user_id
        self.tier = tier
        self.reset_date = self._next_reset_date()

        # Initialize current usage
        self.niche_searches_used = 0
        self.product_searches_used = 0
        self.keepa_lookups_used = 0
        self.teardowns_used = 0

    def _next_reset_date(self) -> datetime:
        """Calculate next reset date (1st of next month)."""
        today = datetime.now()
        if today.month == 12:
            return datetime(today.year + 1, 1, 1)
        return datetime(today.year, today.month + 1, 1)

    def _check_reset(self) -> None:
        """Reset quota if past reset date."""
        if datetime.now() >= self.reset_date:
            self.niche_searches_used = 0
            self.product_searches_used = 0
            self.keepa_lookups_used = 0
            self.teardowns_used = 0
            self.reset_date = self._next_reset_date()
            logger.info(f"Quota reset for user {self.user_id}")

    def get_limits(self) -> Dict[str, int]:
        """Get quota limits for this user's tier."""
        return TIER_QUOTAS.get(self.tier, TIER_QUOTAS["free"])

    def check_niche_search(self) -> Tuple[bool, Optional[str]]:
        """Check if user can do a niche search. Returns (allowed, error_msg)."""
        self._check_reset()
        limits = self.get_limits()
        limit = limits["niche_searches"]

        # -1 means unlimited
        if limit == -1:
            return True, None

        if self.niche_searches_used >= limit:
            return (
                False,
                f"Niche search limit reached ({limit}/month). Upgrade to continue.",
            )
        return True, None

    def check_product_search(self) -> Tuple[bool, Optional[str]]:
        """Check if user can do a product search."""
        self._check_reset()
        limits = self.get_limits()
        limit = limits["product_searches"]

        if limit == -1:
            return True, None

        if self.product_searches_used >= limit:
            return (
                False,
                f"Product search limit reached ({limit}/month). Upgrade to continue.",
            )
        return True, None

    def check_keepa_lookup(self) -> Tuple[bool, Optional[str]]:
        """Check if user can do a Keepa lookup."""
        self._check_reset()
        limits = self.get_limits()
        limit = limits["keepa_lookups"]

        # Free tier never gets Keepa
        if self.tier == "free":
            return (
                False,
                "Keepa data not available on Free tier. Upgrade to Starter.",
            )

        if limit == -1:
            return True, None

        if self.keepa_lookups_used >= limit:
            return (
                False,
                f"Keepa lookup limit reached ({limit}/month). Upgrade to continue.",
            )
        return True, None

    def check_teardown(self) -> Tuple[bool, Optional[str]]:
        """Check if user can do a teardown."""
        self._check_reset()
        limits = self.get_limits()
        limit = limits["teardowns"]

        if limit == -1:
            return True, None

        if self.teardowns_used >= limit:
            return (
                False,
                f"Teardown limit reached ({limit}/month). Upgrade to continue.",
            )
        return True, None

    def increment_niche_search(self) -> None:
        """Track a niche search."""
        self._check_reset()
        self.niche_searches_used += 1

    def increment_product_search(self) -> None:
        """Track a product search."""
        self._check_reset()
        self.product_searches_used += 1

    def increment_keepa_lookup(self) -> None:
        """Track a Keepa lookup."""
        self._check_reset()
        self.keepa_lookups_used += 1

    def increment_teardown(self) -> None:
        """Track a teardown."""
        self._check_reset()
        self.teardowns_used += 1

    def get_usage_summary(self) -> Dict[str, any]:
        """Get current usage summary for display."""
        self._check_reset()
        limits = self.get_limits()

        def format_remaining(used: int, limit: int) -> str:
            if limit == -1:
                return "Unlimited"
            remaining = limit - used
            return f"{remaining}/{limit} remaining"

        return {
            "tier": self.tier,
            "niche_searches": {
                "used": self.niche_searches_used,
                "limit": limits["niche_searches"],
                "remaining": format_remaining(
                    self.niche_searches_used, limits["niche_searches"]
                ),
            },
            "product_searches": {
                "used": self.product_searches_used,
                "limit": limits["product_searches"],
                "remaining": format_remaining(
                    self.product_searches_used, limits["product_searches"]
                ),
            },
            "keepa_lookups": {
                "used": self.keepa_lookups_used,
                "limit": limits["keepa_lookups"],
                "remaining": format_remaining(
                    self.keepa_lookups_used, limits["keepa_lookups"]
                ),
            },
            "teardowns": {
                "used": self.teardowns_used,
                "limit": limits["teardowns"],
                "remaining": format_remaining(
                    self.teardowns_used, limits["teardowns"]
                ),
            },
            "reset_date": self.reset_date.isoformat(),
            "days_until_reset": (self.reset_date - datetime.now()).days,
        }


# In-memory quota storage (TODO: migrate to database)
_user_quotas: Dict[str, UserQuota] = {}


def get_user_quota(user_id: str, tier: str = "free") -> UserQuota:
    """Get or create a user's quota tracker."""
    if user_id not in _user_quotas:
        _user_quotas[user_id] = UserQuota(user_id, tier)
    return _user_quotas[user_id]


def update_user_tier(user_id: str, new_tier: str) -> None:
    """Update a user's tier (e.g., from free to starter)."""
    if user_id in _user_quotas:
        _user_quotas[user_id].tier = new_tier
        logger.info(f"User {user_id} upgraded to {new_tier}")
