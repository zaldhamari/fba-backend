"""
Keepa API client — fetches and normalises Amazon product data.
No business logic here; only fetch + parse.

Keepa time convention
---------------------
Keepa encodes timestamps as minutes since 2011-01-01 00:00:00 UTC.
  Unix epoch for that date = 1_293_840_000 seconds = 21_564_000 minutes.
  Real Unix time (seconds) = (keepa_minute + 21_564_000) * 60

Price convention
----------------
Keepa stores prices as integers in **cents** (multiply by 0.01 for USD).
-1 means "not available"; we return None for those.

Token accounting
----------------
Each API call costs tokens (shown in response["tokensLeft"]).
When exhausted, raise KeepaRateLimitError — never spin in a loop.
"""
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

log = logging.getLogger("siftly.keepa")

KEEPA_API_BASE = "https://api.keepa.com"
KEEPA_API_KEY  = os.environ.get("KEEPA_API_KEY", "")

# Keepa epoch offset in minutes (2011-01-01 00:00 UTC)
_KEEPA_EPOCH_MIN = 21_564_000


# ── Errors ────────────────────────────────────────────────────────────────────

class KeepaRateLimitError(Exception):
    """Raised when Keepa's token bucket is exhausted."""
    def __init__(self, tokens_left: int = 0, refill_rate: float = 3.0):
        self.tokens_left = tokens_left
        self.refill_rate = refill_rate
        super().__init__(
            f"Keepa token limit reached: {tokens_left} tokens left, "
            f"refilling at {refill_rate:.1f}/min."
        )


class KeepaError(Exception):
    """Raised for non-rate-limit Keepa API errors."""


# ── Normalised product type ───────────────────────────────────────────────────

@dataclass
class KeepaProduct:
    asin:                str
    title:               str
    brand:               str
    category:            str              # top-level category name (e.g. "Home & Kitchen")
    current_bsr:         Optional[int]   # Best Sellers Rank in root category
    current_price_cents: Optional[int]   # current NEW price in cents
    avg90_price_cents:   Optional[int]   # 90-day average NEW price in cents
    rating:              Optional[float] # star rating (e.g. 4.5)
    review_count:        Optional[int]
    bsr_history:         Optional[List[int]]  # list of BSR values (newest last)
    price_history_cents: Optional[List[int]]  # list of new-price values in cents


# ── Internal helpers ──────────────────────────────────────────────────────────

def _cents_or_none(raw: Optional[int]) -> Optional[int]:
    """Return the raw cent value, or None if Keepa signals N/A (-1 or missing)."""
    if raw is None or raw < 0:
        return None
    return raw


def _extract_current_price_and_bsr(stats: Optional[Dict]) -> tuple:
    """
    Keepa stats arrays use a fixed index layout:
      index 1 → NEW price (cents)
      index 3 → sales rank in root category
      index 7 → 90-day avg NEW price
    Returns (current_price_cents, avg90_price_cents, current_bsr).
    """
    if not stats:
        return None, None, None

    cur  = stats.get("current") or []
    avg90 = stats.get("avg90")  or []

    current_price = _cents_or_none(cur[1]   if len(cur)   > 1 else None)
    avg90_price   = _cents_or_none(avg90[1] if len(avg90) > 1 else None)

    # Sales rank sits at index 3 in Keepa's current[] array
    raw_bsr = cur[3] if len(cur) > 3 else None
    current_bsr = int(raw_bsr) if raw_bsr is not None and raw_bsr > 0 else None

    return current_price, avg90_price, current_bsr


def _extract_history_values(csv_row: Optional[List]) -> Optional[List[int]]:
    """
    Keepa time-series format: [keepaTime, value, keepaTime, value, ...]
    We extract just the values (odd indices), dropping -1 (unavailable).
    """
    if not csv_row or len(csv_row) < 2:
        return None
    values = [csv_row[i] for i in range(1, len(csv_row), 2) if csv_row[i] >= 0]
    return values or None


def _extract_bsr_history_from_sales_ranks(sales_ranks: Optional[Dict]) -> Optional[List[int]]:
    """
    salesRanks is a dict keyed by root-category ID:
      { "1055398": [keepaTime, rank, keepaTime, rank, ...] }
    We return the rank values from the first (root) category entry.
    """
    if not sales_ranks:
        return None
    for _, rank_array in sales_ranks.items():
        if rank_array and len(rank_array) >= 2:
            values = [rank_array[i] for i in range(1, len(rank_array), 2) if rank_array[i] > 0]
            return values or None
    return None


def _parse_product(raw: Dict) -> KeepaProduct:
    """Normalise a single raw Keepa product dict into a KeepaProduct."""
    asin  = raw.get("asin")  or ""
    title = raw.get("title") or ""
    brand = raw.get("brand") or ""

    # Top-level category name — prefer categoryTree root
    cat_tree = raw.get("categoryTree") or []
    category = cat_tree[0].get("name", "") if cat_tree else (raw.get("categoryName") or "")

    stats = raw.get("stats") or {}
    current_price, avg90_price, current_bsr = _extract_current_price_and_bsr(stats)

    # Fall back to salesRanks for BSR if stats didn't have it
    if current_bsr is None:
        sales_ranks = raw.get("salesRanks") or {}
        for _, rank_array in sales_ranks.items():
            if rank_array and len(rank_array) >= 2:
                last = rank_array[-1]
                if last and last > 0:
                    current_bsr = int(last)
                    break

    # Rating: Keepa stores as integer × 10 (e.g. 45 = 4.5 stars)
    raw_rating = raw.get("avgRating")
    rating = round(raw_rating / 10.0, 1) if raw_rating is not None and raw_rating >= 0 else None

    review_count = raw.get("reviewCount")
    if review_count is not None and review_count < 0:
        review_count = None

    # Price history from csv[1] (NEW price time-series)
    csv = raw.get("csv") or []
    price_history_cents = _extract_history_values(csv[1] if len(csv) > 1 else None)

    # BSR history from salesRanks (cleaner than csv[3])
    bsr_history = _extract_bsr_history_from_sales_ranks(raw.get("salesRanks"))

    return KeepaProduct(
        asin=asin,
        title=title,
        brand=brand,
        category=category,
        current_bsr=current_bsr,
        current_price_cents=current_price,
        avg90_price_cents=avg90_price,
        rating=rating,
        review_count=review_count,
        bsr_history=bsr_history,
        price_history_cents=price_history_cents,
    )


def _assert_tokens(data: Dict) -> None:
    """Raise KeepaRateLimitError if the response signals token exhaustion."""
    tokens_left = data.get("tokensLeft")
    refill_rate = float(data.get("refillRate") or 3.0)

    error_obj = data.get("error") or {}
    error_type = error_obj.get("type") if isinstance(error_obj, dict) else None

    if error_type in ("REQUEST_LIMIT", "PAYMENT_REQUIRED"):
        raise KeepaRateLimitError(tokens_left or 0, refill_rate)
    if tokens_left is not None and tokens_left <= 0:
        raise KeepaRateLimitError(int(tokens_left), refill_rate)


# ── Public API ────────────────────────────────────────────────────────────────

async def get_product_by_asin(asin: str, domain: int = 1) -> KeepaProduct:
    """
    Fetch a single product by ASIN.
    domain: 1=US (default), 2=UK, 3=DE, 6=CA, 8=FR, 9=JP, 10=IT, 11=ES
    Raises KeepaError if no data is returned for the ASIN.
    Raises KeepaRateLimitError if tokens are exhausted.
    """
    results = await get_products_by_asins([asin], domain=domain)
    if not results:
        raise KeepaError(f"Keepa returned no data for ASIN {asin!r}")
    return results[0]


async def get_products_by_asins(
    asins:  List[str],
    domain: int = 1,
) -> List[KeepaProduct]:
    """
    Fetch up to 100 ASINs per Keepa call (Keepa's batch limit).
    Larger lists are split into 100-ASIN batches automatically.
    This is more token-efficient than individual calls — always prefer it.

    Raises KeepaError  for HTTP errors or missing API key.
    Raises KeepaRateLimitError when the token bucket is empty.
    """
    if not asins:
        return []
    if not KEEPA_API_KEY:
        raise KeepaError("KEEPA_API_KEY environment variable is not set.")

    BATCH = 100
    all_products: List[KeepaProduct] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(asins), BATCH):
            batch = asins[i : i + BATCH]
            params = {
                "key":     KEEPA_API_KEY,
                "domain":  str(domain),
                "asin":    ",".join(batch),
                "stats":   "1",   # include current/avg30/avg90 stats
                "history": "1",   # include time-series arrays (uses more tokens)
                "buybox":  "1",   # include buy-box price
                "offers":  "0",   # skip offer listings (saves tokens)
            }
            resp = await client.get(f"{KEEPA_API_BASE}/product", params=params)

            if resp.status_code != 200:
                raise KeepaError(
                    f"Keepa HTTP {resp.status_code} for batch starting at index {i}: "
                    f"{resp.text[:300]}"
                )

            data = resp.json()
            _assert_tokens(data)

            raw_list = data.get("products") or []
            if not raw_list:
                log.warning("Keepa returned 0 products for batch: %s", batch)

            all_products.extend(_parse_product(p) for p in raw_list)

    return all_products
