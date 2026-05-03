import httpx
import asyncio
import re
from backend.scrapers.keywords import to_keywords

AMAZON_SUGGEST_URL = "https://completion.amazon.com/api/2017/suggestions"


async def _fetch_suggestions(keyword: str, client: httpx.AsyncClient) -> list[str]:
    try:
        resp = await client.get(
            AMAZON_SUGGEST_URL,
            params={
                "limit": 11,
                "prefix": keyword,
                "suggestion-type": "KEYWORD",
                "page-type": "Search",
                "alias": "aps",
                "site-variant": "desktop",
                "version": 3,
                "event": "onKeyPress",
                "wc": "",
                "lop": "en_US",
                "last-prefix": keyword,
                "avg-ks-time": 600,
                "fb": 1,
                "mid": "ATVPDKIKX0DER",
                "plain-mid": 1,
                "client-info": "amazon-search-ui",
            },
            timeout=8.0,
        )
        data = resp.json()
        return [s["value"] for s in data.get("suggestions", [])]
    except Exception:
        return []


async def research_keywords(product: str) -> dict:
    base_keywords = to_keywords(product)
    product_clean = " ".join(base_keywords[:3])

    # Generate variations to query
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    queries = [product_clean] + [f"{product_clean} {c}" for c in alphabet[:10]]

    all_suggestions: list[str] = []

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }
    ) as client:
        tasks = [_fetch_suggestions(q, client) for q in queries]
        results = await asyncio.gather(*tasks)
        for r in results:
            all_suggestions.extend(r)

    # Deduplicate and filter
    seen = set()
    unique = []
    for s in all_suggestions:
        sl = s.lower().strip()
        if sl not in seen and len(sl) > 3:
            seen.add(sl)
            unique.append(s.strip())

    # Score by relevance — prefer shorter, more specific
    scored = sorted(unique, key=lambda x: (len(x.split()), len(x)))

    # Separate long-tail (3+ words) from head terms
    head = [k for k in scored if len(k.split()) <= 2][:10]
    long_tail = [k for k in scored if len(k.split()) >= 3][:20]

    # Competition estimate based on keyword length & specificity
    def competition(kw: str) -> str:
        words = len(kw.split())
        if words >= 4:
            return "Low"
        elif words == 3:
            return "Medium"
        return "High"

    keywords_with_data = [
        {
            "keyword": kw,
            "competition": competition(kw),
            "type": "Long-tail" if len(kw.split()) >= 3 else "Head",
        }
        for kw in (head + long_tail)
    ]

    # SEO score for the product title
    title_words = set(product_clean.lower().split())
    matched = sum(1 for k in scored[:20] if any(w in k.lower() for w in title_words))
    seo_score = min(100, int((matched / max(len(scored[:20]), 1)) * 100) + 30)

    return {
        "keywords": keywords_with_data,
        "head_terms": head,
        "long_tail": long_tail,
        "total_found": len(unique),
        "seo_score": seo_score,
        "top_ppc": scored[:5],
    }
