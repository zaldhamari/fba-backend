import httpx
import re
from typing import Optional
from bs4 import BeautifulSoup

from backend.scrapers.keywords import to_query_string

EBAY_CATEGORIES = {
    "electronics": "58058",
    "home": "11700",
    "kitchen": "20625",
    "sports": "888",
    "toys": "220",
    "beauty": "26395",
    "clothing": "11450",
    "tools": "20081",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


def _parse_price(text: str) -> Optional[float]:
    cleaned = text.replace("$", "").replace(",", "").strip()
    # Handle price ranges like "12.99 to 24.99" — take the lower
    m = re.search(r"(\d+\.?\d*)", cleaned)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _parse_int(text: str) -> Optional[int]:
    m = re.search(r"[\d,]+", text)
    if m:
        try:
            return int(m.group().replace(",", ""))
        except ValueError:
            pass
    return None


def _opportunity(review_count: Optional[int], price: Optional[float]) -> str:
    rc = review_count or 0
    p = price or 0
    if rc < 200 and p > 20:
        return "Good"
    elif rc > 1000:
        return "Saturated"
    return "Moderate"


async def search_amazon(keyword: str, category: str = "all") -> list[dict]:
    """
    Searches eBay (server-rendered, cloud-IP-friendly) to get product
    market data — pricing, competition signals, and listing images.
    """
    query = to_query_string(keyword)
    sacat = EBAY_CATEGORIES.get(category, "0")
    url = f"https://www.ebay.com/sch/i.html?_nkw={query}&_sacat={sacat}&LH_BIN=1"

    results = []

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0,
            headers=_HEADERS,
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return [{"error": f"Search returned status {resp.status_code}"}]

            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select("li.s-item")

            for item in items[:15]:
                title_el = item.select_one(".s-item__title")
                price_el = item.select_one(".s-item__price")
                img_el = item.select_one("img.s-item__image-img")
                link_el = item.select_one("a.s-item__link")
                reviews_el = item.select_one(".s-item__reviews-count")
                rating_el = item.select_one(".s-item__reviews .s-item__seller-info-text, [class*='star']")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title or title.lower() == "shop on ebay":
                    continue

                price_text = price_el.get_text(strip=True) if price_el else ""
                price = _parse_price(price_text)

                image = ""
                if img_el:
                    image = img_el.get("src") or img_el.get("data-src") or ""

                href = link_el.get("href", "") if link_el else ""

                review_text = reviews_el.get_text(strip=True) if reviews_el else ""
                review_count = _parse_int(review_text) if review_text else None

                rc = review_count or 0
                competition = "Low" if rc < 50 else "Medium" if rc < 500 else "High"

                results.append({
                    "title": title[:120],
                    "price": price,
                    "rating": None,
                    "review_count": review_count,
                    "asin": "",
                    "image": image,
                    "competition": competition,
                    "opportunity": _opportunity(review_count, price),
                    "url": href,
                })

    except Exception as e:
        results.append({"error": f"Search failed: {str(e)}"})

    return results
