import re
from typing import Optional
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from backend.scrapers.keywords import to_query_string

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
)


def _parse_price_range(text: str) -> dict:
    text = text.replace("$", "").replace("US", "").replace(",", "").strip()
    nums = re.findall(r"\d+\.?\d*", text)
    if len(nums) >= 2:
        return {"min": float(nums[0]), "max": float(nums[1])}
    elif len(nums) == 1:
        return {"min": float(nums[0]), "max": float(nums[0])}
    return {"min": None, "max": None}


async def search_alibaba(product: str, max_price: Optional[float] = None) -> list[dict]:
    """
    Searches Google Shopping filtered to wholesale/supplier results.
    Google is cloud-IP-friendly and indexes AliExpress/DHgate/supplier pages.
    """
    query = to_query_string(product)
    # Search Google Shopping for wholesale/bulk results — surfaces AliExpress, DHgate, etc.
    url = f"https://www.google.com/search?q={query}+wholesale+bulk+supplier&tbm=shop&hl=en&gl=us"

    results = []

    try:
        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=True)
            context = await browser.new_context(
                user_agent=_UA,
                viewport={"width": 1280, "height": 768},
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )

            page = await context.new_page()
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,ico,svg,woff,woff2,ttf,otf,eot}",
                lambda route: route.abort(),
            )

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            try:
                await page.wait_for_selector(
                    ".sh-dgr__content, .sh-pr__product-results-grid > div, [class*='sh-dlr']",
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
                            cards = Array.from(found).slice(0, 14);
                            break;
                        }
                    }

                    return cards.map(card => {
                        const titleSelectors = ['h3', 'h4', '[aria-label]', 'a'];
                        let title = '';
                        for (const s of titleSelectors) {
                            const el = card.querySelector(s);
                            if (el) {
                                title = el.getAttribute('aria-label') || el.innerText.trim();
                                if (title && title.length > 5) break;
                            }
                        }

                        let price = '';
                        const priceEl = card.querySelector('[aria-label*="$"], [class*="price"], [class*="Price"]');
                        if (priceEl) {
                            price = priceEl.getAttribute('aria-label') || priceEl.innerText.trim();
                        }
                        if (!price) {
                            const m = (card.innerText || '').match(/\$\s*(\d+\.?\d*)/);
                            if (m) price = m[0];
                        }

                        const img = card.querySelector('img');
                        const image = img ? (img.getAttribute('src') || img.getAttribute('data-src') || '') : '';

                        const link = card.querySelector('a[href]');
                        const href = link ? link.getAttribute('href') : '';
                        const url = href && href.startsWith('/url?')
                            ? new URLSearchParams(href.slice(5)).get('q') || href
                            : href;

                        const merchantEl = card.querySelector('[class*="merchant"], [class*="store"], [class*="shop"]');
                        const merchant = merchantEl ? merchantEl.innerText.trim() : '';

                        return { title, price, image, url, merchant };
                    });
                }
            """)

            await browser.close()

            for item in items_data:
                title = (item.get("title") or "").strip()
                if not title or len(title) < 5:
                    continue

                price_text = item.get("price") or ""
                price_range = _parse_price_range(price_text)

                if max_price and price_range["min"] and price_range["min"] > max_price:
                    continue

                supplier = (item.get("merchant") or "").strip()
                href = item.get("url") or ""

                results.append({
                    "title": title[:120],
                    "price_range": price_range,
                    "price_display": price_text if price_text else "Contact supplier",
                    "moq": "Contact supplier",
                    "supplier": supplier,
                    "image": item.get("image") or "",
                    "url": href,
                })

    except Exception as e:
        results.append({"error": f"Supplier search failed: {str(e)}"})

    return results
