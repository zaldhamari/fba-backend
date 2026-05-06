from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

from backend.scrapers.amazon import search_amazon
from backend.scrapers.alibaba import search_alibaba
from backend.scrapers.trends import get_trends
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
    product_type: str
    keywords: list[str] = []
    style: Optional[str] = "modern"
    brand_name: Optional[str] = ""


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
    brand = generate_brand(req.product_type, req.keywords, req.style, req.brand_name or "")
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
    from backend.modules.ai_client import AI_AVAILABLE
    return {"status": "ok", "ai_enabled": AI_AVAILABLE}


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


@router.post("/ai/copilot")
async def ai_copilot(req: CopilotRequest):
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
