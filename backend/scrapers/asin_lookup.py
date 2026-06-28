"""
Resolve an Amazon ASIN (or product URL) to a product title + category.

Fetches the Amazon product page using mobile browser headers — mobile pages
are lighter and less aggressively bot-gated than desktop pages.

Falls back gracefully: if Amazon blocks the request (captcha / datacenter IP),
returns the raw ASIN as the product name so the AI analysis can still run.
"""
import re
import httpx

AMAZON_DOMAINS = [
    "amazon.com", "amazon.co.uk", "amazon.de", "amazon.ca",
    "amazon.co.jp", "amazon.com.au", "amazon.in", "amazon.fr",
    "amazon.es", "amazon.it",
]

MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
}

# Simple keyword → category mapping
CATEGORY_HINTS: list[tuple[str, str]] = [
    (r"\bblender|juicer|kettle|toaster|air fryer|coffee|espresso\b", "Kitchen"),
    (r"\bheadphone|earbud|speaker|audio|bluetooth\b", "Electronics"),
    (r"\bphone case|charger|cable|power bank|laptop\b", "Electronics"),
    (r"\byoga|fitness|dumbbell|resistance band|foam roller\b", "Sports"),
    (r"\bdog|cat|pet\b", "Pet Supplies"),
    (r"\bbaby|infant|toddler\b", "Baby"),
    (r"\bvitamin|supplement|protein|probiotic\b", "Health"),
    (r"\bskin|face|moisturizer|serum|shampoo\b", "Beauty"),
    (r"\bbook|journal|planner|notebook\b", "Office"),
    (r"\btoy|game|puzzle|lego\b", "Toys"),
    (r"\bcamping|hiking|backpack|tent\b", "Outdoor"),
    (r"\bdesk|chair|lamp|shelf|storage\b", "Home & Office"),
]


def extract_asin(raw: str) -> str | None:
    """Return the 10-char ASIN from a URL or bare ASIN string, or None."""
    raw = raw.strip()
    # Try /dp/XXXXXXXXXX or /gp/product/XXXXXXXXXX in a URL
    m = re.search(r"(?:/dp/|/gp/product/)([A-Z0-9]{10})", raw, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Bare ASIN
    if re.fullmatch(r"[A-Z0-9]{10}", raw, re.IGNORECASE):
        return raw.upper()
    return None


def _guess_category(title: str) -> str:
    t = title.lower()
    for pattern, cat in CATEGORY_HINTS:
        if re.search(pattern, t, re.IGNORECASE):
            return cat
    return "General"


def _extract_title(html: str) -> str | None:
    # 1. productTitle span (desktop pages)
    m = re.search(r'id=["\']productTitle["\'][^>]*>\s*([^<]{10,200})', html)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    # 2. Page <title> — "Amazon.com: {Product Name} : ..."
    m = re.search(r"<title>\s*Amazon\.com\s*:\s*(.+?)(?:\s*:\s*|\s*\|\s*|\s*-\s*Amazon)", html)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        # Remove HTML entities
        title = title.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
        if len(title) > 10:
            return title
    return None


async def _lookup_via_dataforseo(asin: str) -> dict | None:
    """
    Resolve ASIN to title/category using DataForSEO merchant product endpoint.
    Works from datacenter IPs (unlike Amazon page scraping).
    Returns None if DataForSEO is not configured or the request fails.
    """
    try:
        from backend.scrapers.dataforseo import _is_configured, _auth_header, DATAFORSEO_BASE, MARKETPLACE_TO_LOCATION
        if not _is_configured():
            return None
        location_code, language_code = MARKETPLACE_TO_LOCATION.get("US", (2840, "en_US"))
        payload = [{"asin": asin.upper(), "location_code": location_code, "language_code": language_code}]
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{DATAFORSEO_BASE}/merchant/amazon/products/live/advanced",
                headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        items = (
            data.get("tasks", [{}])[0]
                .get("result", [{}])[0]
                .get("items", [])
        ) or []
        product = next((i for i in items if i.get("asin", "").upper() == asin.upper()), items[0] if items else None)
        if not product or not product.get("title"):
            return None
        categories = product.get("categories") or []
        category = categories[0].get("name") if categories else _guess_category(product["title"])
        return {
            "asin":     asin,
            "title":    product["title"],
            "category": category,
            "url":      f"https://www.amazon.com/dp/{asin}",
            "source":   "dataforseo",
        }
    except Exception:
        return None


async def lookup_asin(asin: str) -> dict:
    """
    Returns:
        { asin, title, category, url, source }
    Tries DataForSEO first (reliable from datacenter), then Amazon page scraping,
    then falls back to the raw ASIN as name.
    """
    url = f"https://www.amazon.com/dp/{asin}"

    # 1. DataForSEO — works reliably from Railway's datacenter IP
    result = await _lookup_via_dataforseo(asin)
    if result:
        return result

    # 2. Amazon page scrape — often bot-gated on datacenter IPs
    try:
        async with httpx.AsyncClient(
            headers=MOBILE_HEADERS,
            follow_redirects=True,
            timeout=10.0,
        ) as client:
            r = await client.get(url)

        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code}")

        html = r.text

        if any(s in html for s in ["Robot Check", "api-services-support", "captcha", "Type the characters"]):
            raise ValueError("Bot gate")

        title = _extract_title(html)
        if not title:
            raise ValueError("Title not found in page")

        category = _guess_category(title)
        return {"asin": asin, "title": title, "category": category, "url": url, "source": "scraped"}

    except Exception:
        return {"asin": asin, "title": asin, "category": "General", "url": url, "source": "fallback"}
