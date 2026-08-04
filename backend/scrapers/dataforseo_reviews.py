"""
DataForSEO client for real Amazon product reviews.
Amazon Reviews has no synchronous live/advanced endpoint (unlike ASIN,
Products, and Sellers) — only the async task_post -> task_get/advanced flow.
Returns real customer review text, ratings, and metadata for a given ASIN.
"""
import asyncio
import time
import httpx
from backend.scrapers.dataforseo import _auth_header, _is_configured, DATAFORSEO_BASE, MARKETPLACE_TO_LOCATION

_REVIEW_CACHE: dict = {}
_REVIEW_CACHE_TTL = 86_400  # 24 hours
_POLL_INTERVAL = 3.0
_POLL_MAX_ATTEMPTS = 8


def _review_cache_get(key: str):
    entry = _REVIEW_CACHE.get(key)
    if entry and time.time() < entry[0]:
        return entry[1]
    return None


def _review_cache_set(key: str, result: list) -> None:
    _REVIEW_CACHE[key] = (time.time() + _REVIEW_CACHE_TTL, result)
    if len(_REVIEW_CACHE) > 300:
        oldest = min(_REVIEW_CACHE.items(), key=lambda x: x[1][0])
        _REVIEW_CACHE.pop(oldest[0], None)


def _parse_items(items: list) -> list[dict]:
    reviews = []
    for item in items:
        text = item.get("review_text") or ""
        if not text or len(text) < 15:
            continue
        # DataForSEO returns rating as {"value": 5, "votes_count": 0, "rating_max": 5}
        rating_raw = item.get("rating")
        rating = rating_raw.get("value") if isinstance(rating_raw, dict) else rating_raw
        reviews.append({
            "rating":        rating,
            "text":          text.strip(),
            "title":         item.get("title") or "",
            "verified":      bool(item.get("verified")),
            "helpful_votes": item.get("helpful_votes") or 0,
        })
    return reviews


async def fetch_amazon_reviews(
    asin: str,
    marketplace: str = "US",
    max_results: int = 50,
) -> list[dict]:
    """
    Fetch real Amazon customer reviews for an ASIN via DataForSEO's async
    Reviews API: POST task_post to queue the task, then poll
    task_get/advanced/{id} until the result is ready.
    Returns: [{ rating, text, title, verified, helpful_votes }]
    Falls back to [] if DataForSEO not configured, request fails, or the
    task doesn't complete within the poll budget.
    Cached 24h per ASIN to avoid redundant paid API calls.
    """
    if not _is_configured() or not asin:
        return []

    cache_key = f"reviews:{asin.upper()}:{marketplace}:{max_results}"
    cached = _review_cache_get(cache_key)
    if cached is not None:
        return cached

    location_code, language_code = MARKETPLACE_TO_LOCATION.get(marketplace, (2840, "en_US"))

    payload = [{
        "asin": asin.upper(),
        "location_code": location_code,
        "language_code": language_code,
        "depth": max_results,
    }]

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            post_resp = await client.post(
                f"{DATAFORSEO_BASE}/merchant/amazon/reviews/task_post",
                headers={
                    "Authorization": _auth_header(),
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            post_resp.raise_for_status()
            post_data = post_resp.json()
            task = (post_data.get("tasks") or [{}])[0]
            task_id = task.get("id")
            if not task_id or task.get("status_code", 0) >= 40000:
                return []

            for _ in range(_POLL_MAX_ATTEMPTS):
                await asyncio.sleep(_POLL_INTERVAL)
                get_resp = await client.get(
                    f"{DATAFORSEO_BASE}/merchant/amazon/reviews/task_get/advanced/{task_id}",
                    headers={
                        "Authorization": _auth_header(),
                        "Content-Type": "application/json",
                    },
                )
                get_resp.raise_for_status()
                get_data = get_resp.json()
                get_task = (get_data.get("tasks") or [{}])[0]
                if get_task.get("status_code") != 20000:
                    continue
                result = (get_task.get("result") or [{}])[0]
                items = result.get("items") or []
                if items:
                    reviews = _parse_items(items)
                    _review_cache_set(cache_key, reviews)
                    return reviews

            return []

    except Exception:
        return []


def split_reviews_by_sentiment(reviews: list[dict]) -> tuple[list[str], list[str]]:
    """
    Split reviews into negative (1-3 stars) and positive (4-5 stars) text lists.
    Returns (negative_texts, positive_texts) for AI analysis.
    """
    negative, positive = [], []
    for r in reviews:
        rating = r.get("rating")
        text   = r.get("text", "")
        if not text:
            continue
        if rating is not None and rating <= 3:
            negative.append(text)
        elif rating is not None and rating >= 4:
            positive.append(text)
    return negative, positive
