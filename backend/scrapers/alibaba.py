import re
from typing import Optional
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from backend.scrapers.keywords import to_query_string

ALIBABA_BASE = "https://www.alibaba.com"


def _parse_price_range(text: str) -> dict:
    text = text.replace("$", "").replace(",", "").strip()
    nums = re.findall(r"\d+\.?\d*", text)
    if len(nums) >= 2:
        return {"min": float(nums[0]), "max": float(nums[1])}
    elif len(nums) == 1:
        return {"min": float(nums[0]), "max": float(nums[0])}
    return {"min": None, "max": None}


async def search_alibaba(product: str, max_price: Optional[float] = None) -> list[dict]:
    query = to_query_string(product)
    url = f"{ALIBABA_BASE}/trade/search?SearchText={query}&viewtype=G&tab=all"

    results = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)

            # Wait for product cards to appear
            try:
                await page.wait_for_selector(
                    '[class*="search-card"], [class*="organic-offer"], [class*="product-card"]',
                    timeout=12000,
                )
            except PWTimeout:
                pass

            await page.wait_for_timeout(2500)

            # Extract product data via JS evaluation for reliability
            items_data = await page.evaluate("""
                () => {
                    const selectors = [
                        '[class*="search-card"]',
                        '[class*="organic-offer"]',
                        '[class*="J-offer-wrapper"]',
                        '[class*="product-card"]',
                        'a[href*="product-detail"]'
                    ];

                    let cards = [];
                    for (const sel of selectors) {
                        const found = document.querySelectorAll(sel);
                        if (found.length > 2) {
                            cards = Array.from(found).slice(0, 14);
                            break;
                        }
                    }

                    return cards.map(card => {
                        const getText = (s) => {
                            const el = card.querySelector(s);
                            return el ? el.innerText.trim() : '';
                        };
                        const getAttr = (s, attr) => {
                            const el = card.querySelector(s);
                            return el ? (el.getAttribute(attr) || '') : '';
                        };

                        const titleSelectors = ['[class*="title"]', 'h2', 'a[title]'];
                        let title = '';
                        for (const s of titleSelectors) {
                            const el = card.querySelector(s);
                            if (el && el.innerText.trim().length > 5) {
                                title = el.innerText.trim();
                                break;
                            }
                        }
                        if (!title) {
                            const a = card.querySelector('a');
                            title = a ? (a.getAttribute('title') || a.innerText.trim()) : '';
                        }

                        const priceSelectors = ['[class*="price"]', '[class*="Price"]'];
                        let price = '';
                        for (const s of priceSelectors) {
                            const el = card.querySelector(s);
                            if (el && el.innerText.includes('$')) {
                                price = el.innerText.trim();
                                break;
                            }
                        }

                        const moqSelectors = ['[class*="moq"]', '[class*="min-order"]', '[class*="MOQ"]'];
                        let moq = '';
                        for (const s of moqSelectors) {
                            const el = card.querySelector(s);
                            if (el) { moq = el.innerText.trim(); break; }
                        }

                        const supplierSelectors = ['[class*="company"]', '[class*="supplier"]', '[class*="store"]'];
                        let supplier = '';
                        for (const s of supplierSelectors) {
                            const el = card.querySelector(s);
                            if (el) { supplier = el.innerText.trim(); break; }
                        }

                        const img = card.querySelector('img');
                        const image = img ? (img.getAttribute('src') || img.getAttribute('data-src') || '') : '';

                        const link = card.querySelector('a[href*="product-detail"]') || card.querySelector('a[href*="alibaba.com"]') || card.querySelector('a');
                        const href = link ? link.getAttribute('href') : '';
                        const url = href && href.startsWith('http') ? href : (href ? 'https:' + href : '');

                        return { title, price, moq, supplier, image, url };
                    });
                }
            """)

            await browser.close()

            for item in items_data:
                title = item.get("title", "").strip()
                price_text = item.get("price", "").strip()
                moq = item.get("moq", "N/A").strip() or "N/A"
                supplier = item.get("supplier", "").strip()
                image = item.get("image", "")
                url = item.get("url", "")

                if not title or len(title) < 3:
                    continue

                price_range = _parse_price_range(price_text)

                if max_price and price_range["min"] and price_range["min"] > max_price:
                    continue

                results.append({
                    "title": title[:120],
                    "price_range": price_range,
                    "price_display": price_text or "Contact supplier",
                    "moq": moq,
                    "supplier": supplier,
                    "image": image,
                    "url": url,
                })

    except Exception as e:
        results.append({"error": f"Supplier search failed: {str(e)}"})

    return results
