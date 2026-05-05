"""
Product Differentiation Generator — suggests improvements and niches.
Uses AI when available, falls back to category knowledge base.
"""
from backend.modules.ai_client import chat_json, AI_AVAILABLE

CATEGORY_IDEAS = {
    "kitchen": {
        "improvements": ["Add non-slip base", "Include storage case", "Dishwasher-safe design", "Premium wood/bamboo variant"],
        "bundles": ["Cutting board + knife set", "Cutting board + oil conditioning kit"],
        "niches": ["Left-handed variant", "RV/camper size", "Gift set with engraving"],
    },
    "fitness": {
        "improvements": ["Heavier gauge material", "Anti-snap warranty", "Eco-friendly latex alternative"],
        "bundles": ["Resistance band set + carry bag + exercise guide"],
        "niches": ["Senior/rehabilitation market", "Prenatal fitness", "Travel/compact version"],
    },
    "pet": {
        "improvements": ["Chew-resistant material", "Easy-clean surface", "Reflective safety strip"],
        "bundles": ["Collar + leash + waste bag dispenser"],
        "niches": ["Large breed specific", "Senior dog comfort", "Anxiety/calming focus"],
    },
    "beauty": {
        "improvements": ["Fragrance-free variant", "Travel size", "Refillable packaging"],
        "bundles": ["Skincare starter kit (3 products)"],
        "niches": ["Sensitive skin", "Teen market", "Men's grooming"],
    },
    "electronics": {
        "improvements": ["Longer cable", "Universal compatibility", "USB-C instead of micro"],
        "bundles": ["Charger + cable + adapter"],
        "niches": ["Gaming setup", "WFH/desk setup", "Travel tech kit"],
    },
}
DEFAULT_IDEAS = {
    "improvements": ["Higher quality materials", "Better packaging and unboxing", "Include quick-start guide", "Add 1-year warranty"],
    "bundles": ["Product + complementary accessory", "Multi-pack value bundle"],
    "niches": ["Premium/pro version", "Eco-friendly variant", "Personalized/custom version"],
}


def generate_differentiation(
    product_name: str,
    category: str,
    top_complaints: list[str] = None,
) -> dict:
    if AI_AVAILABLE:
        return _ai_differentiation(product_name, category, top_complaints or [])
    return _knowledge_base_differentiation(product_name, category)


def _ai_differentiation(product_name, category, complaints):
    system = "You are a product development expert specializing in Amazon FBA differentiation."
    complaints_text = "\n".join(f"- {c}" for c in complaints) if complaints else "No specific complaints provided."
    user = f"""Product: {product_name} | Category: {category}

Known customer complaints about similar products:
{complaints_text}

Return JSON:
{{
  "product_improvements": ["specific, concrete improvement 1", "improvement 2", "improvement 3", "improvement 4"],
  "bundle_ideas": ["bundle concept 1", "bundle concept 2"],
  "niche_angles": ["specific niche or audience to target 1", "niche 2", "niche 3"],
  "listing_angle": "one-sentence unique value proposition for this product",
  "price_positioning": "Premium | Mid-range | Value — with one reason why"
}}"""

    try:
        result = chat_json(system, user, max_tokens=450)
        result["source"] = "ai"
        return result
    except Exception:
        return _knowledge_base_differentiation(product_name, category)


def _knowledge_base_differentiation(product_name, category):
    cat_lower = category.lower()
    data = DEFAULT_IDEAS
    for key, val in CATEGORY_IDEAS.items():
        if key in cat_lower:
            data = val
            break

    return {
        "product_improvements": data["improvements"],
        "bundle_ideas": data["bundles"],
        "niche_angles": data["niches"],
        "listing_angle": f"The last {product_name} you'll ever need to buy — built to outlast the competition.",
        "price_positioning": "Mid-range — enough margin for PPC while undercutting premium competitors",
        "source": "knowledge_base",
    }
