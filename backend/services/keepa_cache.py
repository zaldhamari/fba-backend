"""
Supabase-backed cache for Keepa product data.

Cache strategy
--------------
1. Check keepa_cache for a fresh row (age < max_age_hours, default 24h).
   → Return (product, "cache") immediately.
2. On miss or stale: call Keepa live, upsert fresh row.
   → Return (product, "live").
3. On KeepaRateLimitError:
   → If a stale row exists, return it with source="stale" (degrade gracefully).
   → If no row at all, re-raise — caller must handle the token exhaustion.

Batch variant splits cache hits from misses and fetches all misses in one
Keepa call, keeping token spend proportional to truly unseen ASINs.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from backend.services.keepa import (
    KeepaProduct,
    KeepaRateLimitError,
    get_product_by_asin,
    get_products_by_asins,
)
from backend.services.supabase_client import get_supabase

log = logging.getLogger("siftly.keepa_cache")

# Type alias for readability
ProductWithSource = Tuple[KeepaProduct, str]  # source: "live" | "cache" | "stale"


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _to_payload(p: KeepaProduct) -> dict:
    return {
        "asin":                p.asin,
        "title":               p.title,
        "brand":               p.brand,
        "category":            p.category,
        "current_bsr":         p.current_bsr,
        "current_price_cents": p.current_price_cents,
        "avg90_price_cents":   p.avg90_price_cents,
        "rating":              p.rating,
        "review_count":        p.review_count,
        "bsr_history":         p.bsr_history,
        "price_history_cents": p.price_history_cents,
    }


def _from_payload(payload: dict) -> KeepaProduct:
    return KeepaProduct(
        asin=payload["asin"],
        title=payload.get("title", ""),
        brand=payload.get("brand", ""),
        category=payload.get("category", ""),
        current_bsr=payload.get("current_bsr"),
        current_price_cents=payload.get("current_price_cents"),
        avg90_price_cents=payload.get("avg90_price_cents"),
        rating=payload.get("rating"),
        review_count=payload.get("review_count"),
        bsr_history=payload.get("bsr_history"),
        price_history_cents=payload.get("price_history_cents"),
    )


def _parse_fetched_at(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_fresh(fetched_at: datetime, max_age_hours: int) -> bool:
    age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
    return age < max_age_hours * 3600


# ── Single ASIN ───────────────────────────────────────────────────────────────

async def get_cached_product(
    asin:          str,
    domain:        int = 1,
    max_age_hours: int = 24,
) -> ProductWithSource:
    """
    Fetch a single product, using the cache as the first line of defence.

    Returns (KeepaProduct, source) where source ∈ {"live", "cache", "stale"}.
    Raises KeepaRateLimitError only when Keepa is exhausted AND there is no
    cached fallback (even a stale one) for this ASIN.
    """
    sb  = get_supabase()
    now = datetime.now(timezone.utc)

    result     = sb.table("keepa_cache").select("*").eq("asin", asin).eq("domain", domain).maybe_single().execute()
    cached_row = result.data

    if cached_row:
        fetched_at = _parse_fetched_at(cached_row["fetched_at"])
        if _is_fresh(fetched_at, max_age_hours):
            log.debug("Cache hit for ASIN %s (age %ds)", asin, (now - fetched_at).seconds)
            return _from_payload(cached_row["payload"]), "cache"

    # Cache miss or stale — attempt live fetch
    try:
        product = await get_product_by_asin(asin, domain=domain)
        sb.table("keepa_cache").upsert({
            "asin":       asin,
            "domain":     domain,
            "payload":    _to_payload(product),
            "fetched_at": now.isoformat(),
        }).execute()
        log.info("Keepa live fetch + cached ASIN %s", asin)
        return product, "live"

    except KeepaRateLimitError:
        if cached_row:
            log.warning("Keepa rate limit; returning stale cache for ASIN %s", asin)
            return _from_payload(cached_row["payload"]), "stale"
        raise


# ── Batch ASINs ───────────────────────────────────────────────────────────────

async def get_cached_products_batch(
    asins:         List[str],
    domain:        int = 1,
    max_age_hours: int = 24,
) -> List[ProductWithSource]:
    """
    Batch cache-aware fetch.
    - Fresh cache hits are returned immediately (zero Keepa token cost).
    - All misses are fetched in a single Keepa batch call (one call, many ASINs).
    - On rate-limit error, stale rows are returned for any ASIN that has one;
      ASINs with no cached row at all are omitted from the result.
    - Result order matches the input order (missing ASINs are silently dropped).
    """
    if not asins:
        return []

    sb  = get_supabase()
    now = datetime.now(timezone.utc)

    # Bulk cache lookup
    rows       = (sb.table("keepa_cache").select("*").in_("asin", asins).eq("domain", domain).execute()).data or []
    rows_by_asin: Dict[str, dict] = {r["asin"]: r for r in rows}

    hits:       Dict[str, ProductWithSource] = {}
    misses:     List[str]                    = []
    stale_rows: Dict[str, dict]              = {}

    for asin in asins:
        row = rows_by_asin.get(asin)
        if row:
            fetched_at = _parse_fetched_at(row["fetched_at"])
            if _is_fresh(fetched_at, max_age_hours):
                hits[asin] = (_from_payload(row["payload"]), "cache")
            else:
                stale_rows[asin] = row
                misses.append(asin)
        else:
            misses.append(asin)

    hit_count = len(hits)
    log.info("Batch: %d cache hits, %d Keepa misses for %d ASINs", hit_count, len(misses), len(asins))

    if misses:
        try:
            live_products = await get_products_by_asins(misses, domain=domain)
            for product in live_products:
                sb.table("keepa_cache").upsert({
                    "asin":       product.asin,
                    "domain":     domain,
                    "payload":    _to_payload(product),
                    "fetched_at": now.isoformat(),
                }).execute()
                hits[product.asin] = (product, "live")
        except KeepaRateLimitError:
            # Degrade to stale for any ASIN that has a cached row
            for asin in misses:
                if asin in stale_rows:
                    hits[asin] = (_from_payload(stale_rows[asin]["payload"]), "stale")
            log.warning(
                "Keepa rate limit on batch; %d ASINs served stale, %d dropped",
                len([a for a in misses if a in stale_rows]),
                len([a for a in misses if a not in stale_rows]),
            )

    # Return in original input order, omitting any ASIN without data
    return [hits[asin] for asin in asins if asin in hits]
