from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from backend.scrapers.amazon import search_amazon
from backend.scrapers.alibaba import search_alibaba
from backend.scrapers.trends import get_trends
from backend.modules.fba_calculator import calculate_fba_fees
from backend.modules.brand_creator import generate_brand

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
    dimensions: dict  # {"length": float, "width": float, "height": float}
    category: str


class BrandRequest(BaseModel):
    product_type: str
    keywords: list[str] = []
    style: Optional[str] = "modern"


@router.post("/research/amazon")
async def amazon_research(req: ProductSearchRequest):
    products = await search_amazon(req.keyword, req.category)
    trends = await get_trends(req.keyword)
    return {"products": products, "trends": trends, "keyword": req.keyword}


@router.post("/research/suppliers")
async def supplier_search(req: SupplierSearchRequest):
    suppliers = await search_alibaba(req.product, req.max_price)
    return {"suppliers": suppliers, "product": req.product}


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


@router.post("/brand/create")
async def brand_create(req: BrandRequest):
    brand = generate_brand(req.product_type, req.keywords, req.style)
    return brand


@router.get("/health")
async def health():
    return {"status": "ok"}
