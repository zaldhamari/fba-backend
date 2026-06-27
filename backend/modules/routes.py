from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from backend.scrapers.asin_lookup import lookup_asin, extract_asin
from backend.scrapers.trends import get_trends
# Use orchestrator for all data searches (handles fallback chains + data_source tagging)
from backend.lib.search_orchestrator import (
    search_amazon_products,
    search_suppliers,
    get_data_sources_status,
)
from backend.scrapers.keywords_scraper import research_keywords
from backend.modules.fba_calculator import calculate_fba_fees
from backend.modules.brand_creator import generate_brand
from backend.modules.opportunity import score_opportunity
from backend.modules.label_creator import generate_product_label, generate_insert_card
from backend.modules.supplier_email import generate_supplier_email
from backend.modules.ai_copilot import analyze_product
from backend.modules.review_analyzer import analyze_reviews
from backend.modules.profit_simulator import simulate
from backend.modules.supplier_scorer import score_supplier
from backend.modules.differentiation import generate_differentiation
from backend.modules.analyze_product import analyze_product_quick
from backend.modules.feasibility_report import generate_feasibility_report
from backend.modules.niche_analyzer import analyze_niche
from backend.modules.freight_estimator import estimate_freight
from backend.modules.analytics_store import store_events
from backend.modules.product_physical import estimate_physical_attributes

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
    quantity: Optional[int] = 1


class BrandRequest(BaseModel):
    product_type:    str
    keywords:        list[str]       = []
    style:           Optional[str]   = "modern"
    brand_name:      Optional[str]   = ""
    brand_direction: Optional[str]   = None
    color_palette:   Optional[str]   = None
    font_style:      Optional[str]   = None
    packaging_mood:  Optional[str]   = None
    tagline:         Optional[str]   = None
    target_audience: Optional[str]   = None
    brand_tone:      Optional[str]   = None


class KeywordRequest(BaseModel):
    product: str


class OpportunityRequest(BaseModel):
    amazon_price: float
    supplier_price: float
    review_count: Optional[int] = 0
    trend_direction: Optional[str] = "Stable"
    weight_lbs: Optional[float] = 1.0
    category: Optional[str] = "all"


@router.get("/debug/dataforseo")
async def debug_dataforseo():
    """Debug: check account info, supported languages, and try various endpoints."""
    import os, base64, httpx
    login = os.environ.get("DATAFORSEO_LOGIN", "")
    password = os.environ.get("DATAFORSEO_PASSWORD", "")
    if not (login and password):
        return {"configured": False}
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
    results = {}
    async with httpx.AsyncClient(timeout=25.0) as client:
        # Check account info / subscription
        try:
            r = await client.get("https://api.dataforseo.com/v3/appendix/user_data", headers=headers)
            ud = r.json()
            results["account"] = ud.get("tasks", [{}])[0].get("result", [{}])[0]
        except Exception as e:
            results["account_error"] = str(e)
        # Get valid merchant amazon languages
        try:
            r = await client.get("https://api.dataforseo.com/v3/merchant/amazon/languages", headers=headers)
            langs = r.json()
            lang_list = langs.get("tasks", [{}])[0].get("result", [])
            results["languages_sample"] = lang_list[:5] if lang_list else langs
        except Exception as e:
            results["languages_error"] = str(e)
        # Try serp/amazon endpoint (the one that works as per old code)
        for endpoint in [
            "/v3/merchant/amazon/products/live/advanced",
            "/v3/serp/amazon/organic/live/advanced",
            "/v3/merchant/amazon/asin/task_post",
        ]:
            try:
                r = await client.post(
                    f"https://api.dataforseo.com{endpoint}",
                    headers=headers,
                    json=[{"keyword": "yoga mat", "location_code": 2840, "depth": 3}],
                )
                rj = r.json()
                task = rj.get("tasks", [{}])[0]
                results[endpoint] = {"code": task.get("status_code"), "msg": task.get("status_message")}
            except Exception as e:
                results[endpoint] = {"error": str(e)}
    return {"configured": True, "deployed_at": "2026-06-27-v5", "login": login, "results": results}


@router.post("/research/amazon")
async def amazon_research(req: ProductSearchRequest, user_id: str = None):
    # Check quota
    from backend.modules.usage_quotas import get_user_quota
    from fastapi import HTTPException

    if user_id:
        quota = get_user_quota(user_id)
        allowed, error = quota.check_product_search()
        if not allowed:
            raise HTTPException(status_code=429, detail=error)

    # Use orchestrator: auto-routes through DataForSEO → AI → Keyword → Stub
    result = await search_amazon_products(req.keyword, req.category or "all", max_results=15)
    trends = await get_trends(req.keyword)
    response = {
        **result,  # Includes data_source + products with source tags
        "trends": trends,
        "keyword": req.keyword
    }

    # Track quota
    if user_id:
        quota.increment_product_search()

    return response


@router.post("/research/suppliers")
async def supplier_search(req: SupplierSearchRequest):
    # Use orchestrator: auto-routes through Alibaba → Global Sources → Fallback → Stub
    result = await search_suppliers(
        product=req.product,
        marketplace="US",
        max_unit_price=req.max_price,
        max_results=10
    )
    return {
        **result,  # Includes data_source + suppliers with source tags
        "product": req.product
    }


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
        quantity=req.quantity or 1,
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
    brand = generate_brand(
        product_type    = req.product_type,
        keywords        = req.keywords,
        style           = req.style or "modern",
        brand_name      = req.brand_name or "",
        brand_direction = req.brand_direction,
        color_palette   = req.color_palette,
        font_style      = req.font_style,
        packaging_mood  = req.packaging_mood,
        tagline         = req.tagline,
        target_audience = req.target_audience,
        brand_tone      = req.brand_tone,
    )
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


# ─── Brand Insert (standalone — does not regenerate the label) ────────────────

class InsertRequest(BaseModel):
    brand_name:       str
    product_name:     str
    weight:           Optional[str] = "1 oz (28g)"
    style:            Optional[str] = "minimal"
    brand_direction:  Optional[str] = None
    color_palette:    Optional[str] = None
    font_style:       Optional[str] = None
    packaging_type:   Optional[str] = None
    tagline:          Optional[str] = None
    support_url:      Optional[str] = None
    qr_text:          Optional[str] = None


@router.post("/brand/insert")
async def brand_insert(req: InsertRequest):
    """Returns only the packaging insert SVG without touching the label."""
    insert_svg = generate_insert_card(
        req.brand_name,
        req.product_name,
        style=req.style or "minimal",
    )
    return {"insert_svg": insert_svg}


# ─── Brand Asset (barcode, packaging, listing-prep assets) ───────────────────

class BrandAssetRequest(BaseModel):
    prompt:         str
    type:           str                  # e.g. "barcode", "packaging", "badge"
    brand_name:     Optional[str] = ""
    primary_color:  Optional[str] = "#2563EB"
    style:          Optional[str] = "modern"


@router.post("/brand/asset")
async def brand_asset(req: BrandAssetRequest):
    """
    Generates a brand asset SVG (barcode placeholder, packaging badge, etc.)
    Uses label_creator's barcode/decorative SVG generator — no AI required.
    """
    from backend.modules.ai_client import AI_AVAILABLE, chat
    asset_type = (req.type or "barcode").lower()

    # ── Barcode placeholder (deterministic, no AI) ────────────────────────────
    if asset_type in ("barcode", "upc", "ean"):
        import hashlib
        seed_str = f"{req.brand_name or ''}{req.prompt or ''}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:6], 16)
        color = req.primary_color or "#2563EB"
        bars = ""
        widths = [1,2,1,3,1,2,2,1,3,1,2,1,1,3,2,1,1,2,3,1,2,1,3,1,2,2,1,1,3,2]
        # Vary widths slightly using seed
        x = 10
        for i, w in enumerate(widths):
            w2 = max(1, w + (((seed >> i) & 1)))
            bars += f'<rect x="{x}" y="20" width="{w2}" height="60" fill="{color}"/>'
            x += w2 + 1
        digits = str(seed)[:12].ljust(12, "0")
        svg = (
            f'<svg viewBox="0 0 {x+10} 100" xmlns="http://www.w3.org/2000/svg">'
            f'<rect width="100%" height="100%" fill="white"/>'
            f'{bars}'
            f'<text x="{(x+10)//2}" y="95" text-anchor="middle" '
            f'font-size="8" font-family="monospace" fill="#333">{digits}</text>'
            f'</svg>'
        )
        return {"svg": svg, "url": None, "type": asset_type, "source": "generated"}

    # ── AI-generated asset description → simple SVG badge ────────────────────
    if AI_AVAILABLE:
        try:
            description = chat(
                system=(
                    "You are a brand asset designer. Given a brand asset request, "
                    "return a brief one-line description of the visual asset (max 20 words). "
                    "Do not include any SVG or code — just the description."
                ),
                user=f"Asset type: {req.type}\nBrand: {req.brand_name}\nPrompt: {req.prompt}",
                max_tokens=60,
            )
        except Exception:
            description = req.prompt or req.type
    else:
        description = req.prompt or req.type

    color = req.primary_color or "#2563EB"
    brand = (req.brand_name or "BRAND")[:12].upper()
    label = (req.type or "ASSET").upper()[:10]
    svg = (
        f'<svg viewBox="0 0 200 120" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="200" height="120" rx="12" fill="{color}"/>'
        f'<text x="100" y="45" text-anchor="middle" font-size="22" font-weight="bold" '
        f'font-family="sans-serif" fill="white">{brand}</text>'
        f'<text x="100" y="70" text-anchor="middle" font-size="11" '
        f'font-family="sans-serif" fill="rgba(255,255,255,0.85)">{label}</text>'
        f'<rect x="20" y="82" width="160" height="1" fill="rgba(255,255,255,0.3)"/>'
        f'<text x="100" y="105" text-anchor="middle" font-size="8" '
        f'font-family="sans-serif" fill="rgba(255,255,255,0.7)">siftly.ai</text>'
        f'</svg>'
    )
    return {"svg": svg, "url": None, "type": asset_type, "source": "generated", "description": description}


# ─── AI Estimate Physical Attributes ──────────────────────────────────────────

class EstimatePhysicalRequest(BaseModel):
    title:    str
    price:    Optional[float] = None
    category: Optional[str]  = None


@router.post("/ai/estimate-physical")
async def ai_estimate_physical(req: EstimatePhysicalRequest):
    """
    Estimates weight, dimensions, and category for a product from its title.
    Used to pre-fill the FBA profit calculator — always tagged as ai_estimate/fallback.
    """
    return estimate_physical_attributes(
        title=req.title,
        price=req.price,
        category=req.category,
    )


@router.get("/health")
async def health():
    from backend.modules.ai_client import AI_AVAILABLE
    return {"status": "ok", "ai_enabled": AI_AVAILABLE}


# ─── ASIN / Product URL Lookup ────────────────────────────────────────────────

class ProductLookupRequest(BaseModel):
    input: str  # bare ASIN or full Amazon URL


@router.post("/research/product")
async def product_lookup(req: ProductLookupRequest):
    asin = extract_asin(req.input)
    if not asin:
        return {"error": "Could not find a valid ASIN in the input.", "title": None, "category": None}
    result = await lookup_asin(asin)
    return result


# ─── AI Copilot ──────────────────────────────────────────────────────────────

class CopilotRequest(BaseModel):
    product_name: str
    amazon_price: float
    supplier_price: float
    review_count: Optional[int] = 0
    trend_direction: Optional[str] = "Stable"
    weight_lbs: Optional[float] = 1.0
    category: Optional[str] = "all"
    competition: Optional[str] = "Medium"
    monthly_sales_est: Optional[int] = 150
    marketplace: Optional[str] = "US"
    currency: Optional[str] = "USD"
    financial_context: Optional[Dict[str, Any]] = None
    # Keepa enrichment — optional; when provided the analysis uses real market data
    asin: Optional[str] = None
    tier: Optional[str] = None   # RC entitlement slug for Keepa gating


@router.post("/ai/copilot")
async def ai_copilot(req: CopilotRequest):
    # ── Keepa-enriched path (Prompt 6) ────────────────────────────────────────
    asin = (req.asin or "").strip().upper()
    tier = (req.tier or "").strip().lower()
    if asin and tier in {"builder", "operator"}:
        import logging
        from backend.services.keepa import KeepaRateLimitError, KeepaError
        from backend.services.keepa_cache import get_cached_product
        from backend.services.bsr_sales_model import estimateMonthlySales
        from backend.modules.ai_copilot import analyze_product_with_keepa

        log = logging.getLogger("siftly.routes.copilot")
        domain = _DOMAIN_MAP.get((req.marketplace or "US").upper(), 1)
        try:
            product, source = await get_cached_product(asin, domain=domain)
            sales_est = None
            if product.current_bsr:
                try:
                    sales_est = estimateMonthlySales(product.current_bsr, product.category or "default")
                except Exception:
                    pass
            result = analyze_product_with_keepa(
                product=product,
                sales_est=sales_est,
                supplier_price=req.supplier_price,
                marketplace=req.marketplace or "US",
                currency=req.currency or "USD",
                competition=req.competition or "Medium",
                financial_context=req.financial_context,
            )
            result["keepa_source"] = source
            return result
        except (KeepaRateLimitError, KeepaError) as exc:
            log.warning("Keepa unavailable for copilot ASIN %s (%s) — falling back to estimates", asin, exc)
            # Fall through to legacy path below

    # ── Legacy estimated path (no ASIN or Keepa unavailable) ─────────────────
    return analyze_product(
        product_name=req.product_name,
        amazon_price=req.amazon_price,
        supplier_price=req.supplier_price,
        review_count=req.review_count or 0,
        trend_direction=req.trend_direction or "Stable",
        weight_lbs=req.weight_lbs or 1.0,
        category=req.category or "all",
        competition=req.competition or "Medium",
        monthly_sales_est=req.monthly_sales_est or 150,
        marketplace=req.marketplace or "US",
        currency=req.currency or "USD",
        financial_context=req.financial_context,
    )


# ─── Review Analyzer ─────────────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    product_name: str
    category: Optional[str] = "all"
    sample_reviews: Optional[List[str]] = []


@router.post("/ai/reviews")
async def review_analysis(req: ReviewRequest):
    return analyze_reviews(
        product_name=req.product_name,
        category=req.category or "all",
        sample_reviews=req.sample_reviews or [],
    )


# ─── Differentiation Generator ───────────────────────────────────────────────

class DiffRequest(BaseModel):
    product_name: str
    category: Optional[str] = "all"
    top_complaints: Optional[List[str]] = []


@router.post("/ai/differentiate")
async def differentiate(req: DiffRequest):
    return generate_differentiation(
        product_name=req.product_name,
        category=req.category or "all",
        top_complaints=req.top_complaints or [],
    )


# ─── Profit Simulator ────────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    supplier_cost: float
    weight_lbs: Optional[float] = 1.0
    category: Optional[str] = "all"
    dimensions: Optional[dict] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    monthly_units_est: Optional[int] = 150


@router.post("/calculate/simulate")
async def profit_simulate(req: SimulateRequest):
    return simulate(
        supplier_cost=req.supplier_cost,
        weight_lbs=req.weight_lbs or 1.0,
        category=req.category or "all",
        dimensions=req.dimensions,
        price_min=req.price_min,
        price_max=req.price_max,
        monthly_units_est=req.monthly_units_est or 150,
    )


# ─── Supplier Scorer ─────────────────────────────────────────────────────────

class SupplierScoreRequest(BaseModel):
    supplier_name: str
    price_per_unit: float
    moq: int
    years_experience: Optional[int] = 0
    response_time_hours: Optional[int] = 24
    has_certifications: Optional[bool] = False
    product_name: Optional[str] = ""
    target_order_qty: Optional[int] = 500


@router.post("/suppliers/score")
async def supplier_score(req: SupplierScoreRequest):
    return score_supplier(
        supplier_name=req.supplier_name,
        price_per_unit=req.price_per_unit,
        moq=req.moq,
        years_experience=req.years_experience or 0,
        response_time_hours=req.response_time_hours or 24,
        has_certifications=req.has_certifications or False,
        product_name=req.product_name or "",
        target_order_qty=req.target_order_qty or 500,
    )


# ─── Analyze Product (Killer Feature) ────────────────────────────────────────

class AnalyzeProductRequest(BaseModel):
    price: float
    reviews: int
    competition: str
    trend: str
    currency: Optional[str] = "USD"
    marketplace: Optional[str] = "US"


# ─── Feasibility Report ──────────────────────────────────────────────────────

class FeasibilityReportRequest(BaseModel):
    product_name: str
    amazon_price: Optional[float] = None
    supplier_analysis: Optional[Dict[str, Any]] = None
    calculation: Optional[Dict[str, Any]] = None
    brand: Optional[Dict[str, Any]] = None
    keywords: Optional[Dict[str, Any]] = None
    freight: Optional[Dict[str, Any]] = None
    marketplace: Optional[str] = "US"
    currency: Optional[str] = "USD"


@router.post("/ai/feasibility-report")
async def feasibility_report(req: FeasibilityReportRequest):
    return generate_feasibility_report(
        product_name=req.product_name,
        amazon_price=req.amazon_price,
        supplier_analysis=req.supplier_analysis,
        calculation=req.calculation,
        brand=req.brand,
        keywords=req.keywords,
        freight=req.freight,
        marketplace=req.marketplace or "US",
        currency=req.currency or "USD",
    )


@router.post("/ai/analyze-product")
async def analyze_product_endpoint(req: AnalyzeProductRequest):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"analyze-product: marketplace={req.marketplace}, currency={req.currency}, price={req.price}, reviews={req.reviews}")
    return analyze_product_quick(
        price=req.price,
        reviews=req.reviews,
        competition=req.competition,
        trend=req.trend,
        currency=req.currency or "USD",
        marketplace=req.marketplace or "US",
    )


# ─── AI Ask (generic copilot Q&A) ────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    context:  Optional[Dict[str, Any]] = None


@router.post("/ai/ask")
async def ai_ask(req: AskRequest):
    from backend.modules.ai_client import chat, AI_AVAILABLE
    if not AI_AVAILABLE:
        return {"answer": "AI is not configured on this server.", "available": False}

    context_str = ""
    if req.context:
        context_str = "\n\nContext:\n" + "\n".join(f"- {k}: {v}" for k, v in req.context.items())

    try:
        answer = chat(
            system="You are Siftly's AI co-pilot for Amazon FBA sellers. Answer concisely and practically. If you're unsure, say so.",
            user=req.question + context_str,
            max_tokens=600,
        )
        return {"answer": answer, "available": True}
    except Exception as e:
        return {"answer": f"Error: {str(e)}", "available": False}


# ─── Niche Intelligence Report ────────────────────────────────────────────────

class NicheResearchRequest(BaseModel):
    keyword:                str
    marketplace:            Optional[str]  = "US"
    price_min:              Optional[float] = 15.0
    price_max:              Optional[float] = 60.0
    max_top_seller_reviews: Optional[int]   = 300
    budget:                 Optional[int]   = 1000


@router.post("/research/niche")
async def niche_research(req: NicheResearchRequest, user_id: str = None):
    # Check quota
    from backend.modules.usage_quotas import get_user_quota
    from fastapi import HTTPException

    if user_id:
        quota = get_user_quota(user_id)
        allowed, error = quota.check_niche_search()
        if not allowed:
            raise HTTPException(status_code=429, detail=error)

    marketplace = req.marketplace or "US"
    # Use orchestrator: auto-routes through DataForSEO → AI → Keyword → Stub
    search_result = await search_amazon_products(req.keyword, marketplace, max_results=20)
    products = search_result.get("products", [])
    data_source = search_result.get("data_source", "unknown")

    report = analyze_niche(
        keyword=req.keyword,
        products=products,
        budget=req.budget or 1000,
        price_min=req.price_min or 15.0,
        price_max=req.price_max or 60.0,
        max_top_seller_reviews=req.max_top_seller_reviews or 300,
        marketplace=marketplace,
    )
    # Tag report with data source
    report["data_source"] = data_source

    # Track quota
    if user_id:
        quota.increment_niche_search()

    return report


# ─── Suppliers v2 (real Alibaba API) ─────────────────────────────────────────

class SuppliersV2Request(BaseModel):
    product:        str
    marketplace:    Optional[str]   = "US"
    max_unit_price: Optional[float] = None
    max_moq:        Optional[int]   = None


@router.post("/research/suppliers-v2")
async def suppliers_v2(req: SuppliersV2Request):
    # Use orchestrator: auto-routes through Alibaba → Global Sources → Fallback → Stub
    result = await search_suppliers(
        product=req.product,
        marketplace=req.marketplace or "US",
        max_unit_price=req.max_unit_price,
        max_moq=req.max_moq,
        max_results=10,
    )
    return {
        **result,  # Includes data_source + suppliers with source tags
        "product": req.product
    }


# ─── Freight Estimates ────────────────────────────────────────────────────────

class FreightRequest(BaseModel):
    product_name:       str
    marketplace:        Optional[str]   = "US"
    units:              Optional[int]   = 200
    weight_kg_per_unit: Optional[float] = 0.5
    length_cm:          Optional[float] = 20.0
    width_cm:           Optional[float] = 15.0
    height_cm:          Optional[float] = 10.0


# ─── Analytics Ingest ─────────────────────────────────────────────────────────

class AnalyticsEventPayload(BaseModel):
    event:      str
    userId:     Optional[str] = None
    appVersion: Optional[str] = None
    screen:     Optional[str] = None
    ts:         Optional[str] = None
    properties: Optional[Dict[str, Any]] = None


class AnalyticsBatchRequest(BaseModel):
    events: List[AnalyticsEventPayload]


@router.post("/analytics/events")
async def analytics_ingest(req: AnalyticsBatchRequest):
    if not req.events:
        return {"accepted": 0}
    valid = [ev.model_dump() for ev in req.events if ev.event and ev.event.strip()]
    store_events(valid)
    return {"accepted": len(valid)}


@router.post("/research/freight")
async def freight_estimate(req: FreightRequest):
    return estimate_freight(
        product_name=req.product_name,
        marketplace=req.marketplace or "US",
        units=req.units or 200,
        weight_kg_per_unit=req.weight_kg_per_unit or 0.5,
        length_cm=req.length_cm or 20.0,
        width_cm=req.width_cm or 15.0,
        height_cm=req.height_cm or 10.0,
    )


# ─── Freight Intelligence ─────────────────────────────────────────────────────

class FreightIntelRequest(BaseModel):
    product_name:       Optional[str]   = "Product"
    unit_cost:          Optional[float] = 5.0
    units:              Optional[int]   = 200
    weight_kg_per_unit: Optional[float] = None
    weight_kg:          Optional[float] = None   # convenience alias
    length_cm:          Optional[float] = 20.0
    width_cm:           Optional[float] = 15.0
    height_cm:          Optional[float] = 10.0
    marketplace:        Optional[str]   = "US"
    selling_price:      Optional[float] = None
    category:           Optional[str]   = None


@router.post("/research/freight-intel")
async def freight_intel(req: FreightIntelRequest):
    weight  = req.weight_kg_per_unit or req.weight_kg or 0.5
    units   = req.units or 200
    freight = estimate_freight(
        product_name=req.product_name or "Product",
        marketplace=req.marketplace or "US",
        units=units,
        weight_kg_per_unit=weight,
        length_cm=req.length_cm or 20.0,
        width_cm=req.width_cm or 15.0,
        height_cm=req.height_cm or 10.0,
    )
    best_mode_key  = freight["recommended"]
    best_mode      = freight["modes"].get(best_mode_key) or freight["modes"]["air"]
    rough_freight  = best_mode["total_cost"] if best_mode else 0
    unit_cost      = req.unit_cost or 0.0
    investment     = round(unit_cost * units + rough_freight + freight["prep_cost"], 2)
    landed         = round(unit_cost * units + rough_freight + freight["fba_inbound_est"], 2)
    fba_fee_est    = round(req.selling_price * 0.15 + 3.22, 2) if req.selling_price else None

    risk_signals: list = [
        {
            "type": "info",
            "label": "Transit",
            "detail": f"{best_mode['transit_days']} days via {best_mode['mode']}",
        }
    ]
    if units < 100:
        risk_signals.append({
            "type": "warning",
            "label": "Low volume",
            "detail": "Per-unit freight cost is high for orders under 100 units",
        })
    if unit_cost > 0 and req.selling_price and req.selling_price > 0:
        margin = (req.selling_price - landed / units) / req.selling_price
        if margin < 0.25:
            risk_signals.append({
                "type": "warning",
                "label": "Thin margin",
                "detail": f"Estimated net margin ~{margin*100:.0f}% — aim for 30%+",
            })

    return {
        "investment_usd":    investment,
        "landed_cost_usd":   landed,
        "rough_freight_usd": rough_freight,
        "fba_inbound_est":   freight["fba_inbound_est"],
        "prep_cost":         freight["prep_cost"],
        "modes":             freight["modes"],
        "risk_signals":      risk_signals,
        "negotiation_note":  (
            f"At {units} units via {best_mode['mode']}, aim for a unit cost "
            f"under ${round(rough_freight / units * 0.5, 2)} to maintain 30%+ net margin."
        ),
    }


# ─── Supplier Analysis ────────────────────────────────────────────────────────

class AnalyzeSupplierRequest(BaseModel):
    product_name:  Optional[str]       = None
    name:          Optional[str]       = None   # supplier name alias
    platform:      Optional[str]       = "Alibaba"
    unit_cost:     Optional[float]     = None
    moq:           Optional[int]       = None
    selling_price: Optional[float]     = None
    country:       Optional[str]       = "CN"
    years:         Optional[int]       = None
    products:      Optional[List[str]] = None
    rating:        Optional[float]     = None


@router.post("/research/analyze-supplier")
async def analyze_supplier(req: AnalyzeSupplierRequest):
    supplier_name = req.name or req.product_name or "Supplier"
    score = 70
    if req.years and req.years >= 3:
        score += 10
    if req.rating and req.rating >= 4.5:
        score += 10
    if req.moq and req.moq <= 200:
        score += 5
    score = min(score, 100)

    flags: list = []
    if req.years and req.years < 2:
        flags.append("New supplier — request samples before committing")
    if req.moq and req.moq > 1000:
        flags.append("High MOQ — negotiate down or split with another buyer")

    margin = None
    if req.unit_cost and req.selling_price:
        landed_unit = req.unit_cost * 1.4
        margin = round((req.selling_price - landed_unit) / req.selling_price * 100, 1)

    moq_units  = req.moq or 200
    investment = round(req.unit_cost * moq_units, 2)       if req.unit_cost else None
    landed     = round(req.unit_cost * 1.4 * moq_units, 2) if req.unit_cost else None
    fba_fee    = round(req.selling_price * 0.15 + 3.22, 2)  if req.selling_price else None

    return {
        "supplier":              supplier_name,
        "platform":              req.platform,
        "score":                 score,
        "recommendation":        "proceed" if score >= 70 else "caution",
        "flags":                 flags,
        "estimated_margin_pct":  margin,
        "investment_usd":        investment,
        "landed_cost_usd":       landed,
        "rough_freight_usd":     None,
        "fba_fee_est_usd":       fba_fee,
    }


# ─── Keepa Product Data ───────────────────────────────────────────────────────

# Keepa domain codes (US default; extend as needed)
_DOMAIN_MAP = {"US": 1, "UK": 2, "DE": 3, "CA": 6, "FR": 8, "JP": 9, "IT": 10, "ES": 11}

# Paid tiers — subject to daily quota
_PAID_TIERS = {"builder", "operator"}
# Free tiers — subject to monthly allowance
_FREE_TIERS = {"explorer", "free", ""}


class ProductDataRequest(BaseModel):
    asin:        str
    user_id:     str
    tier:        str          # RC entitlement: "builder" | "operator" | "explorer" | "free"
    marketplace: Optional[str] = "US"


@router.post("/product/data")
async def product_data(req: ProductDataRequest):
    """
    Fetch enriched product data for a single ASIN.

    Auth:    X-API-Key header (enforced by APIKeyMiddleware in main.py)
    Paid:    builder/operator — subject to daily quota
    Free:    explorer/free — full real data, capped at KEEPA_FREE_MONTHLY_LOOKUPS/month
             Cache hits are free for ALL tiers (never decremented from any quota).
    Returns: product + sales estimate + history signals
    """
    import logging
    from fastapi import HTTPException
    from backend.services.keepa import KeepaRateLimitError, KeepaError
    from backend.services.keepa_cache import get_cached_product
    from backend.services.bsr_sales_model import estimateMonthlySales
    from backend.services.keepa_signals import compute_signals
    from backend.services.keepa_quota import check_and_record, QuotaExceededError
    from backend.services.keepa_free_quota import (
        check_and_record_free, FreeLookupExhaustedError,
    )

    log = logging.getLogger("siftly.routes.product_data")

    tier = (req.tier or "").strip().lower()
    asin = req.asin.strip().upper()

    if not asin or len(asin) < 10 or not asin.isalnum():
        raise HTTPException(status_code=422, detail="Invalid ASIN format.")

    domain = _DOMAIN_MAP.get((req.marketplace or "US").upper(), 1)

    is_paid = tier in _PAID_TIERS
    is_free = tier in _FREE_TIERS

    if not is_paid and not is_free:
        raise HTTPException(
            status_code=403,
            detail=f"Unknown tier '{req.tier}'. Expected builder, operator, explorer, or free.",
        )

    # ── Pre-flight quota check ────────────────────────────────────────────────
    if is_paid:
        try:
            check_and_record(req.user_id, tier, dry_run=True)
        except QuotaExceededError as exc:
            raise HTTPException(
                status_code=429,
                detail={"error": "quota_exceeded", "scope": exc.scope,
                        "used": exc.used, "limit": exc.limit, "message": str(exc)},
            )
    else:  # free tier
        try:
            check_and_record_free(req.user_id, dry_run=True)
        except FreeLookupExhaustedError as exc:
            raise HTTPException(
                status_code=402,
                detail={
                    "reason":    "free_lookup_limit",
                    "used":      exc.used,
                    "limit":     exc.limit,
                    "message":   (
                        f"You've used your {exc.limit} free product lookups this month. "
                        "Upgrade to Builder for more."
                    ),
                    "resets_on": exc.resets_on,
                },
            )

    # ── Keepa fetch (cache-first) ─────────────────────────────────────────────
    try:
        product, source = await get_cached_product(asin, domain=domain)
    except KeepaRateLimitError as exc:
        log.warning("Keepa token exhausted for ASIN %s — no cache fallback", asin)
        raise HTTPException(
            status_code=503,
            detail={"error": "keepa_rate_limit",
                    "message": "Keepa token bucket exhausted. Retry after tokens refill.",
                    "tokens_left": exc.tokens_left, "refill_rate": exc.refill_rate},
        )
    except KeepaError as exc:
        log.error("Keepa error for ASIN %s: %s", asin, exc)
        raise HTTPException(status_code=502, detail={"error": "keepa_error", "message": str(exc)})

    # ── Record quota (only for live/stale; cache hits are free for all tiers) ─
    if source != "cache":
        if is_paid:
            try:
                check_and_record(req.user_id, tier, dry_run=False)
            except QuotaExceededError:
                pass
        else:
            try:
                check_and_record_free(req.user_id, dry_run=False)
            except FreeLookupExhaustedError:
                pass

    # ── BSR → sales estimate ──────────────────────────────────────────────────
    sales_estimate = None
    if product.current_bsr:
        try:
            est = estimateMonthlySales(product.current_bsr, product.category or "default")
            sales_estimate = {
                "monthly_sales":    est.monthly_sales,
                "low":              est.low,
                "high":             est.high,
                "confidence":       est.confidence,
                "confidence_score": est.confidence_score,
                "note":             est.note,
                "category_key":     est.category_key,
            }
        except Exception:
            pass

    # ── History signals ───────────────────────────────────────────────────────
    signals = compute_signals(product)

    # ── Analytics (best-effort) ───────────────────────────────────────────────
    try:
        store_events([{
            "event":      "keepa_product_data",
            "userId":     req.user_id,
            "properties": {
                "asin": asin, "domain": domain, "source": source, "tier": tier,
                "has_bsr": product.current_bsr is not None,
                "has_sales_est": sales_estimate is not None,
                "bsr_trend": signals["bsr"]["trend"],
                "price_direction": signals["price"]["direction"],
                "spike_flag": signals["bsr"]["spike_flag"],
            },
        }])
    except Exception:
        pass

    # ── Response ──────────────────────────────────────────────────────────────
    current_price_usd = round(product.current_price_cents / 100, 2) if product.current_price_cents is not None else None
    avg90_price_usd   = round(product.avg90_price_cents   / 100, 2) if product.avg90_price_cents   is not None else None

    return {
        "asin":   asin,
        "source": source,
        "product": {
            "title":             product.title,
            "brand":             product.brand,
            "category":          product.category,
            "current_bsr":       product.current_bsr,
            "current_price_usd": current_price_usd,
            "avg90_price_usd":   avg90_price_usd,
            "rating":            product.rating,
            "review_count":      product.review_count,
        },
        "sales_estimate": sales_estimate,
        "signals":        signals,
    }


# ─── Free Allowance Status ────────────────────────────────────────────────────

class FreeAllowanceRequest(BaseModel):
    user_id: str


@router.get("/product/free-allowance")
async def free_allowance(user_id: str):
    """
    Return how many free monthly Keepa lookups a user has left.
    Auth: X-API-Key middleware (same as all /api routes).
    Response: { used, limit, resets_on }
    """
    from backend.services.keepa_free_quota import get_free_allowance
    return get_free_allowance(user_id)


# ─── Keepa Metrics ────────────────────────────────────────────────────────────

@router.get("/metrics/keepa")
async def keepa_metrics():
    """
    Returns today's Keepa quota usage.
    Protected by the same X-API-Key middleware as all /api routes.
    """
    from backend.services.keepa_quota import get_stats
    return get_stats()


# ─── Data Sources Status (for Settings screen) ───────────────────────────────

@router.get("/data-sources/status")
async def data_sources_status():
    """
    Returns status of all configured data providers.

    Used by Settings → Data Sources screen to show:
    - Which providers are connected (DataForSEO, Alibaba, etc.)
    - Connection status (available, rate-limited, unavailable)
    - Usage stats (X / daily limit)
    - Cost per request

    Returns: {
        "providers": [
            {
                "type": "dataforseo",
                "name": "DataForSEO — Real Amazon Data",
                "status": "available|unavailable",
                "enabled": true,
                "priority": 1,
                "daily_usage": "42/1000",
                "cost_per_request": 0.001,
                "category": "products",
                "connect_url": "https://app.dataforseo.com/...",
                "docs": "https://docs.dataforseo.com/amazon"
            },
            ...
        ],
        "real_data_available": true,
        "ai_estimate_available": true,
        "summary": "✓ Live data connected. Using DataForSEO + AI estimates."
    }
    """
    return await get_data_sources_status()


# ─── User Quotas & Tiers ──────────────────────────────────────────────────

@router.get("/user/quota")
async def get_user_quota_endpoint(user_id: str):
    """
    Returns current user's quota usage and limits.

    Example response:
    {
      "tier": "professional",
      "niche_searches": { "used": 8, "limit": 100, "remaining": "92/100 remaining" },
      "product_searches": { "used": 15, "limit": 200, "remaining": "185/200 remaining" },
      "keepa_lookups": { "used": 3, "limit": 50, "remaining": "47/50 remaining" },
      "teardowns": { "used": 5, "limit": 100, "remaining": "95/100 remaining" },
      "reset_date": "2026-07-01T00:00:00",
      "days_until_reset": 9
    }
    """
    from backend.modules.usage_quotas import get_user_quota
    quota = get_user_quota(user_id)
    return quota.get_usage_summary()


@router.post("/user/tier")
async def update_user_tier(user_id: str, new_tier: str):
    """
    Update user's subscription tier.
    Tier options: free, starter, professional, power
    """
    from backend.modules.usage_quotas import update_user_tier, TIER_QUOTAS

    if new_tier not in TIER_QUOTAS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown tier: {new_tier}")

    update_user_tier(user_id, new_tier)
    return {"status": "ok", "user_id": user_id, "tier": new_tier}


# ─── Keepa Enrichment ─────────────────────────────────────────────────────

@router.get("/product/keepa-insights")
async def product_keepa_insights(asin: str, user_id: str):
    """
    Get Keepa-enriched insights for a product.

    Returns:
    {
      "sales_estimate": { "monthly_sales": 150, "low": 100, "high": 200, "confidence": "Medium" },
      "price_sustainability": { "margin_room": 2.4, "sustainability": "high", "risk": "none" },
      "market_saturation": { "market_age_months": 34, "saturation": "moderate", "spike_risk": "low" },
      "monthly_revenue_est": 5250,
      "bsr_trend": "stable",
      "spike_flag": false,
      "summary": { ... }
    }
    """
    from backend.modules.usage_quotas import get_user_quota
    from backend.modules.keepa_enrichment import compile_keepa_insights
    from backend.services.keepa_cache import get_cached_product

    # Check quota
    quota = get_user_quota(user_id)
    allowed, error = quota.check_keepa_lookup()
    if not allowed:
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail=error)

    # Fetch Keepa data
    try:
        domain = 1  # US
        product, source = await get_cached_product(asin.upper(), domain=domain)

        # Convert to dict format for enrichment
        product_data = {
            "current_bsr": product.current_bsr,
            "current_price_usd": (product.current_price_cents / 100) if product.current_price_cents else None,
            "floor_price_usd": None,  # Calculated from signals
            "review_count": product.review_count,
            "category": product.category or "default",
            "signals": {
                "bsr": {
                    "trend": "stable",  # From keepa_signals.py
                    "volatility": 0.15,
                },
                "price": {
                    "direction": "flat",
                },
            },
        }

        # Add floor price from signals if available
        if product.price_history_cents:
            floor_cents = min([p for p in product.price_history_cents if p > 0])
            product_data["floor_price_usd"] = floor_cents / 100

        # Compile insights
        insights = compile_keepa_insights(product_data)
        insights["keepa_source"] = source

        # Track quota
        quota.increment_keepa_lookup()

        return insights
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Keepa lookup failed: {str(e)}")
