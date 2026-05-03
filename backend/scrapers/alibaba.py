import httpx
import re
from typing import Optional
from bs4 import BeautifulSoup

from backend.scrapers.keywords import to_query_string

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.com/",
}


def _parse_price_range(text: str) -> dict:
    text = text.replace("$", "").replace(",", "").strip()
    nums = re.findall(r"\d+\.?\d*", text)
    if len(nums) >= 2:
        return {"min": float(nums[0]), "max": float(nums[1])}
    elif len(nums) == 1:
        return {"min": float(nums[0]), "max": float(nums[0])}
    return {"min": None, "max": None}


def _parse_price(text: str) -> Optional[float]:
    m = re.search(r"(\d+\.?\d*)", text.replace("$", "").replace(",", ""))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


async def search_alibaba(product: str, max_price: Optional[float] = None) -> list[dict]:
    """
    Searches DHgate for wholesale suppliers.
    DHgate is a Chinese B2B wholesale platform with server-friendly responses.
    """
    query = to_query_string(product)

    # Try DHgate first (wholesale B2B, simpler structure)
    results = await _search_dhgate(query, max_price)
    if results and not any("error" in r for r in results):
        return results

    # Fall back to AliExpress bulk/wholesale listings
    return await _search_aliexpress(query, max_price)


async def _search_dhgate(query: str, max_price: Optional[float]) -> list[dict]:
    url = f"https://www.dhgate.com/wholesale/search.do?searchkey={query}&pageNo=1&orderType=hotsales"
    results = []

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0,
            headers=_HEADERS,
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "lxml")

            # DHgate product cards
            cards = soup.select(".pcard, .productCon, [class*='product-card'], [class*='pcard']")
            if not cards:
                cards = soup.select("ul.list-items li, .search-main li")

            for card in cards[:14]:
                title_el = card.select_one(
                    "[class*='title'] a, h2, h3, a[title], .product-title"
                )
                price_el = card.select_one("[class*='price'], .price")
                moq_el = card.select_one("[class*='moq'], [class*='min'], .min-order")
                supplier_el = card.select_one("[class*='store'], [class*='supplier'], [class*='company']")
                img_el = card.select_one("img")
                link_el = card.select_one("a[href*='product'], a[href*='dhgate']")

                title = ""
                if title_el:
                    title = title_el.get("title") or title_el.get_text(strip=True)
                if not title or len(title) < 4:
                    continue

                price_text = price_el.get_text(strip=True) if price_el else ""
                price_range = _parse_price_range(price_text)

                if max_price and price_range["min"] and price_range["min"] > max_price:
                    continue

                moq = moq_el.get_text(strip=True) if moq_el else "N/A"
                supplier = supplier_el.get_text(strip=True) if supplier_el else ""
                image = ""
                if img_el:
                    image = img_el.get("src") or img_el.get("data-src") or ""
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.dhgate.com" + href

                results.append({
                    "title": title[:120],
                    "price_range": price_range,
                    "price_display": price_text or "Contact supplier",
                    "moq": moq,
                    "supplier": supplier,
                    "image": image,
                    "url": href,
                })

    except Exception:
        pass

    return results


async def _search_aliexpress(query: str, max_price: Optional[float]) -> list[dict]:
    """
    Fallback: scrape AliExpress wholesale search via httpx.
    AliExpress has partial SSR for search pages.
    """
    url = f"https://www.aliexpress.com/wholesale?SearchText={query}&SortType=BESTSELLING"
    results = []

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0,
            headers={**_HEADERS, "Referer": "https://www.aliexpress.com/"},
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return [{"error": f"Supplier search returned status {resp.status_code}"}]

            soup = BeautifulSoup(resp.text, "lxml")

            # AliExpress product cards in their SSR HTML
            cards = soup.select(
                "[class*='manhattan--container'], "
                "[class*='product-card'], "
                "div[data-aer-item]"
            )

            if not cards:
                # Try extracting from JSON embedded in the page
                scripts = soup.find_all("script")
                for script in scripts:
                    text = script.get_text()
                    if "listItem" in text or "productList" in text:
                        price_matches = re.findall(r'"salePrice":\s*\{[^}]*"value":\s*"?(\d+\.?\d*)"?', text)
                        title_matches = re.findall(r'"title":\s*"([^"]{10,120})"', text)
                        img_matches = re.findall(r'"imageUrl":\s*"([^"]+)"', text)
                        url_matches = re.findall(r'"productDetailUrl":\s*"([^"]+)"', text)

                        for i in range(min(10, len(title_matches))):
                            title = title_matches[i] if i < len(title_matches) else ""
                            if not title:
                                continue
                            price = float(price_matches[i]) if i < len(price_matches) else None
                            if max_price and price and price > max_price:
                                continue
                            price_range = {"min": price, "max": price} if price else {"min": None, "max": None}
                            results.append({
                                "title": title[:120],
                                "price_range": price_range,
                                "price_display": f"${price:.2f}" if price else "Contact supplier",
                                "moq": "1 piece",
                                "supplier": "AliExpress Supplier",
                                "image": img_matches[i] if i < len(img_matches) else "",
                                "url": url_matches[i] if i < len(url_matches) else "",
                            })
                        if results:
                            return results
                        break

            for card in cards[:14]:
                title_el = card.select_one("[class*='title'], h1, h2, h3")
                price_el = card.select_one("[class*='price']")
                img_el = card.select_one("img")
                link_el = card.select_one("a[href]")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title or len(title) < 4:
                    continue

                price_text = price_el.get_text(strip=True) if price_el else ""
                price_range = _parse_price_range(price_text)

                if max_price and price_range["min"] and price_range["min"] > max_price:
                    continue

                image = ""
                if img_el:
                    image = img_el.get("src") or img_el.get("data-src") or ""

                href = link_el.get("href", "") if link_el else ""
                if href and href.startswith("//"):
                    href = "https:" + href

                results.append({
                    "title": title[:120],
                    "price_range": price_range,
                    "price_display": price_text or "Contact supplier",
                    "moq": "1 piece",
                    "supplier": "AliExpress Supplier",
                    "image": image,
                    "url": href,
                })

    except Exception as e:
        results.append({"error": f"Supplier search failed: {str(e)}"})

    return results
