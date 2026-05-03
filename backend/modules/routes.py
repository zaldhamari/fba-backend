from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from backend.scrapers.amazon import search_amazon
from backend.scrapers.alibaba import search_alibaba
from backend.scrapers.trends import get_trends
from backend.scrapers.keywords_scraper import research_keywords
from backend.modules.fba_calculator import calculate_fba_fees
from backend.modules.brand_creator import generate_brand
from backend.modules.opportunity import score_opportunity
from backend.modules.label_creator import generate_product_label, generate_insert_card
from backend.modules.supplier_email import generate_supplier_email

router = APIRouter()


class ProductSearchRequest(BaseModel):
    keyword: str
    category: Optional[str] = "all"


class SupplierSearchRequest(BaseModel):
    product: str
    max_price: Optional[float] = None


class FBACalcRequest(BaseModel):
    product_name: str
    selling_price: float
    supplier_cost: float
    weight_lbs: float
    dimensions: dict
    category: str


class BrandRequest(BaseModel):
    product_type: str
    keywords: list[str] = []
    style: Optional[str] = "modern"


class KeywordRequest(BaseModel):
    product: str


class OpportunityRequest(BaseModel):
    amazon_price: float
    supplier_price: float
    review_count: Optional[int] = 0
    trend_direction: Optional[str] = "Stable"
    weight_lbs: Optional[float] = 1.0
    category: Optional[str] = "all"


@router.post("/research/amazon")
async def amazon_research(req: ProductSearchRequest):
    products = await search_amazon(req.keyword, req.category)
    trends = await get_trends(req.keyword)
    return {"products": products, "trends": trends, "keyword": req.keyword}


@router.post("/research/suppliers")
async def supplier_search(req: SupplierSearchRequest):
    suppliers = await search_alibaba(req.product, req.max_price)
    return {"suppliers": suppliers, "product": req.product}


@router.post("/research/keywords")
async def keyword_research(req: KeywordRequest):
    result = await research_keywords(req.product)
    return result


@router.post("/calculate/fba")
async def fba_calculate(req: FBACalcRequest):
    result = calculate_fba_fees(
        selling_price=req.selling_price,
        supplier_cost=req.supplier_cost,
        weight_lbs=req.weight_lbs,
        dimensions=req.dimensions,
        category=req.category,
    )
    return result


@router.post("/calculate/opportunity")
async def opportunity_score(req: OpportunityRequest):
    result = score_opportunity(
        amazon_price=req.amazon_price,
        supplier_price=req.supplier_price,
        review_count=req.review_count or 0,
        trend_direction=req.trend_direction or "Stable",
        weight_lbs=req.weight_lbs or 1.0,
        category=req.category or "all",
    )
    return result


@router.post("/brand/create")
async def brand_create(req: BrandRequest):
    brand = generate_brand(req.product_type, req.keywords, req.style)
    return brand


class LabelRequest(BaseModel):
    brand_name: str
    product_name: str
    weight: Optional[str] = "1 oz (28g)"
    style: Optional[str] = "minimal"


class SupplierEmailRequest(BaseModel):
    product: str
    quantity: Optional[int] = 500
    brand_name: Optional[str] = ""


@router.post("/brand/label")
async def brand_label(req: LabelRequest):
    label = generate_product_label(req.brand_name, req.product_name, req.weight or "1 oz (28g)", style=req.style or "minimal")
    insert = generate_insert_card(req.brand_name, req.product_name, style=req.style or "minimal")
    return {"label_svg": label, "insert_svg": insert}


@router.post("/supplier/email")
async def supplier_email(req: SupplierEmailRequest):
    return generate_supplier_email(req.product, req.quantity or 500, req.brand_name or "")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/debug/scrape")
async def debug_scrape():
    """Temporary: check what Google Shopping returns from Railway's IP."""
    from playwright.async_api import async_playwright
    result = {}
    try:
        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=True)
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
                viewport={"width": 1280, "height": 768},
            )
            page = await ctx.new_page()
            await page.route("**/*.{png,jpg,jpeg,gif,webp,ico,svg,woff,woff2,ttf,otf,eot}", lambda r: r.abort())
            await page.goto("https://www.google.com/search?q=bamboo+cutting+board&tbm=shop&hl=en&gl=us", wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2000)
            html = await page.content()
            await browser.close()
            result = {
                "length": len(html),
                "has_captcha": "captcha" in html.lower() or "unusual traffic" in html.lower(),
                "first_500": html[:500],
                "selectors_found": {},
            }
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            for sel in [".sh-dgr__content", ".sh-pr__product-results-grid", ".KZmu8e", ".u30d4", "[data-sh-or]", ".mnr-c"]:
                result["selectors_found"][sel] = len(soup.select(sel))
    except Exception as e:
        result = {"error": str(e)[:300]}
    return result
