import asyncio
import re
from typing import Optional
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from backend.scrapers.keywords import to_query_string

AMAZON_BASE = "https://www.amazon.com"

CATEGORY_NODES = {
    "electronics": "172282",
    "home": "1055398",
    "kitchen": "284507",
    "sports": "3375251",
    "toys": "165793011",
    "beauty": "3760911",
    "clothing": "7141123011",
    "tools": "228013",
}


def _parse_price(text: str) -> Optional[float]:
    m = re.search(r"[\d,]+\.?\d*", text.replace("$", ""))
    if m:
        try:
            return float(m.group().replace(",", ""))
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
    query = to_query_string(keyword)
    url = f"{AMAZON_BASE}/s?k={query}"
    if category in CATEGORY_NODES:
        url += f"&rh=n%3A{CATEGORY_NODES[category]}"

    results = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            # Hide webdriver flag
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for product grid or detect block
            try:
                await page.wait_for_selector(
                    "div[data-component-type='s-search-result'], .s-no-outline",
                    timeout=10000,
                )
            except PWTimeout:
                pass

            await page.wait_for_timeout(1500)

            # Check for CAPTCHA / robot check
            content = await page.content()
            if "captcha" in content.lower() or "robot" in content.lower() or "To discuss automated access" in content:
                await browser.close()
                return [{"error": "Amazon is asking for a CAPTCHA. Wait a minute then try again."}]

            items = await page.query_selector_all("div[data-component-type='s-search-result']")

            for item in items[:15]:
                try:
                    title_el = await item.query_selector("h2 a span, h2 span")
                    price_el = await item.query_selector("span.a-price span.a-offscreen")
                    rating_el = await item.query_selector("span.a-icon-alt")
                    reviews_el = await item.query_selector("span.a-size-base.s-underline-text")
                    image_el = await item.query_selector("img.s-image")
                    asin = await item.get_attribute("data-asin") or "N/A"

                    title = (await title_el.inner_text()).strip() if title_el else "N/A"
                    price_text = await price_el.inner_text() if price_el else ""
                    rating_text = await rating_el.inner_text() if rating_el else ""
                    reviews_text = await reviews_el.inner_text() if reviews_el else ""
                    image = await image_el.get_attribute("src") if image_el else ""

                    price = _parse_price(price_text)
                    rating = _parse_price(rating_text)
                    review_count = _parse_int(reviews_text)

                    rc = review_count or 0
                    competition = "Low" if rc < 50 else "Medium" if rc < 500 else "High"

                    results.append({
                        "title": title,
                        "price": price,
                        "rating": rating,
                        "review_count": review_count,
                        "asin": asin,
                        "image": image,
                        "competition": competition,
                        "opportunity": _opportunity(review_count, price),
                        "url": f"{AMAZON_BASE}/dp/{asin}" if asin != "N/A" else "",
                    })
                except Exception:
                    continue

            await browser.close()

    except Exception as e:
        results.append({"error": f"Search failed: {str(e)}"})

    return results
