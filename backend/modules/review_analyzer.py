"""
Review Analyzer — extracts pain points and opportunities from product reviews.
Uses AI when available; falls back to a category-based knowledge base.
"""
from backend.modules.ai_client import chat_json, AI_AVAILABLE

# Known pain points by category (used as fallback and to seed AI context)
CATEGORY_PAIN_POINTS = {
    "kitchen": {
        "complaints": ["Broke after a few uses", "Smaller than pictured", "Hard to clean", "Cheap material"],
        "opportunities": ["Premium materials with durability guarantee", "Accurate sizing with real photos", "Dishwasher-safe design", "Reinforced weak points"],
    },
    "fitness": {
        "complaints": ["Snapped under load", "Sizing runs small", "No instructions included", "Poor grip"],
        "opportunities": ["Show strength testing in images", "Full size guide with body type examples", "QR-code setup guide included", "Textured anti-slip grip"],
    },
    "pet": {
        "complaints": ["Dog chewed through it", "Sizing off", "Hard to assemble", "Cheap smell"],
        "opportunities": ["Heavy-duty chew-resistant materials", "Breed-specific sizing chart", "Tool-free assembly", "Non-toxic certified"],
    },
    "electronics": {
        "complaints": ["Stopped working after a month", "Incompatible with some devices", "Weak battery", "Poor instructions"],
        "opportunities": ["2-year warranty prominently displayed", "Wide compatibility list", "High-capacity battery", "Video setup guide via QR"],
    },
    "beauty": {
        "complaints": ["Caused breakouts", "Fragrance too strong", "Didn't last long", "Leaked in bag"],
        "opportunities": ["Fragrance-free or hypoallergenic variant", "Long-wear formula claim", "Leak-proof packaging", "Dermatologist-tested certification"],
    },
    "baby": {
        "complaints": ["BPA concerns", "Too small for older babies", "Hard to clean", "Fell apart quickly"],
        "opportunities": ["BPA/BPS-free certification front and center", "Size range clearly stated", "Dishwasher-safe top rack", "Reinforced construction with warranty"],
    },
}
DEFAULT_PAIN_POINTS = {
    "complaints": ["Quality below expectation", "Poor packaging", "Missing instructions", "Sizing issues"],
    "opportunities": ["Premium materials", "Better packaging", "Clear instructions included", "Accurate size guide"],
}


def analyze_reviews(product_name: str, category: str, sample_reviews: list[str] = None) -> dict:
    if AI_AVAILABLE and sample_reviews:
        return _ai_analyze(product_name, category, sample_reviews)
    return _knowledge_base_analyze(product_name, category)


def _ai_analyze(product_name: str, category: str, sample_reviews: list[str]) -> dict:
    from backend.modules.ai_client import chat_json
    system = (
        "You are an Amazon product analyst. Extract actionable insights from customer reviews. "
        "Focus on patterns, not individual complaints."
    )
    reviews_text = "\n".join(f"- {r}" for r in sample_reviews[:20])
    user = f"""Product: {product_name} (Category: {category})

Customer reviews:
{reviews_text}

Return JSON:
{{
  "top_complaints": ["complaint 1", "complaint 2", "complaint 3", "complaint 4"],
  "opportunities": ["specific fix or differentiation 1", "fix 2", "fix 3", "fix 4"],
  "sentiment_score": 0-100,
  "most_praised": ["what customers love 1", "love 2"],
  "recommended_improvements": ["concrete product change 1", "change 2", "change 3"],
  "bundling_ideas": ["bundle idea 1", "bundle idea 2"]
}}"""

    try:
        result = chat_json(system, user, max_tokens=500)
        result["source"] = "ai"
        return result
    except Exception:
        return _knowledge_base_analyze(product_name, category)


def _knowledge_base_analyze(product_name: str, category: str) -> dict:
    cat_lower = category.lower()
    data = DEFAULT_PAIN_POINTS

    for key, val in CATEGORY_PAIN_POINTS.items():
        if key in cat_lower:
            data = val
            break

    return {
        "top_complaints": data["complaints"],
        "opportunities": data["opportunities"],
        "sentiment_score": 62,
        "most_praised": ["Value for money", "Fast shipping"],
        "recommended_improvements": [
            f"Source higher-grade materials for {product_name}",
            "Improve packaging with clear instructions",
            "Add warranty card to build trust",
        ],
        "bundling_ideas": [
            f"{product_name} + care/cleaning kit",
            f"{product_name} + complementary accessory",
        ],
        "source": "knowledge_base",
    }
