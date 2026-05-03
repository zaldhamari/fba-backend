import re
from typing import Optional
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from backend.scrapers.keywords import to_query_string

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-software-rasterizer",
    "--single-process",
    "--no-zygote",
]


def _parse_price(text: str) -> Optional[float]:
    cleaned = text.replace("$", "").replace(",", "").strip()
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
    Scrapes Google Shopping results (cloud-IP-friendly) to get product
    market data: pricing, competition signals, and listing images.
    """
    query = to_query_string(keyword)
    url = f"https://www.google.com/search?q={query}&tbm=shop&hl=en&gl=us"

    results = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            context = await browser.new_context(
                user_agent=_UA,
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            try:
                await page.wait_for_selector(
                    ".sh-dgr__content, .sh-pr__product-results-grid, [class*='sh-dlr']",
                    timeout=10000,
                )
            except PWTimeout:
                pass

            await page.wait_for_timeout(1500)

            content = await page.content()
            if "captcha" in content.lower() or "unusual traffic" in content.lower():
                await browser.close()
                return [{"error": "Google requires CAPTCHA. Please try again in a minute."}]

            items_data = await page.evaluate("""
                () => {
                    const cardSelectors = [
                        '.sh-dgr__content',
                        '.sh-pr__product-results-grid > div',
                        '[class*="sh-dlr"] [class*="mnr-c"]',
                        '[jsname][data-sh-or]',
                        '.u30d4'
                    ];

                    let cards = [];
                    for (const sel of cardSelectors) {
                        const found = document.querySelectorAll(sel);
                        if (found.length > 2) {
                            cards = Array.from(found).slice(0, 15);
                            break;
                        }
                    }

                    return cards.map(card => {
                        const titleSelectors = ['h3', 'h4', '[aria-label]', 'a[href]'];
                        let title = '';
                        for (const s of titleSelectors) {
                            const el = card.querySelector(s);
                            if (el) {
                                title = el.getAttribute('aria-label') || el.innerText.trim();
                                if (title && title.length > 5) break;
                            }
                        }

                        const priceSelectors = ['[aria-label*="$"]', '[class*="price"]', '[class*="Price"]'];
                        let price = '';
                        for (const s of priceSelectors) {
                            const el = card.querySelector(s);
                            if (el) {
                                price = el.getAttribute('aria-label') || el.innerText.trim();
                                if (price && (price.includes('$') || price.match(/\d+\.\d+/))) break;
                            }
                        }
                        if (!price) {
                            const allText = card.innerText || '';
                            const m = allText.match(/\$\s*(\d+\.?\d*)/);
                            if (m) price = m[0];
                        }

                        const ratingSelectors = ['[aria-label*="stars"], [aria-label*="rating"], [class*="rating"], [class*="star"]'];
                        let rating = '';
                        for (const s of ratingSelectors) {
                            const el = card.querySelector(s);
                            if (el) {
                                rating = el.getAttribute('aria-label') || el.innerText.trim();
                                break;
                            }
                        }

                        const img = card.querySelector('img');
                        const image = img ? (img.getAttribute('src') || img.getAttribute('data-src') || '') : '';

                        const link = card.querySelector('a[href]');
                        const href = link ? link.getAttribute('href') : '';
                        const url = href && href.startsWith('/url?')
                            ? new URLSearchParams(href.slice(5)).get('q') || href
                            : href;

                        const merchantSelectors = ['[class*="merchant"], [class*="store"], [class*="shop"]'];
                        let merchant = '';
                        for (const s of merchantSelectors) {
                            const el = card.querySelector(s);
                            if (el && el.innerText.trim()) { merchant = el.innerText.trim(); break; }
                        }

                        return { title, price, rating, image, url, merchant };
                    });
                }
            """)

            await browser.close()

            for item in items_data:
                title = (item.get("title") or "").strip()
                if not title or len(title) < 5:
                    continue

                price = _parse_price(item.get("price") or "")
                rating_text = item.get("rating") or ""
                rating = _parse_price(rating_text)
                if rating and rating > 5:
                    rating = None

                review_count = None
                rc_match = re.search(r"([\d,]+)\s*(?:reviews?|ratings?)", rating_text, re.I)
                if rc_match:
                    review_count = _parse_int(rc_match.group(1))

                rc = review_count or 0
                competition = "Low" if rc < 50 else "Medium" if rc < 500 else "High"

                results.append({
                    "title": title[:120],
                    "price": price,
                    "rating": rating,
                    "review_count": review_count,
                    "asin": "",
                    "image": item.get("image") or "",
                    "competition": competition,
                    "opportunity": _opportunity(review_count, price),
                    "url": item.get("url") or "",
                })

    except Exception as e:
        results.append({"error": f"Search failed: {str(e)}"})

    return results
