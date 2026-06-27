"""
Recraft AI logo generation client.

Uses Recraft V3 vector model to produce high-quality vector logos.
Cost: 80 API units per image (~$0.08 at $1/1000 units).

Docs: https://www.recraft.ai/docs
API:  https://external.api.recraft.ai/v1
"""
import os
from typing import Optional
import httpx

RECRAFT_BASE = "https://external.api.recraft.ai/v1"

# All brand styles map to vector_illustration (Recraft V3 vector model)
_STYLE_MAP: dict[str, str] = {
    "modern":  "vector_illustration",
    "premium": "vector_illustration",
    "playful": "vector_illustration",
    "minimal": "vector_illustration",
    "luxury":  "vector_illustration",
    "eco":     "vector_illustration",
    "bold":    "vector_illustration",
}

# Color hints for logo generation prompts
_COLOR_HINTS: dict[str, str] = {
    "blue":   "blue and navy color scheme",
    "green":  "green and teal color scheme",
    "purple": "purple and violet color scheme",
    "warm":   "warm amber and orange color scheme",
    "dark":   "dark monochrome, black and white",
    "earth":  "earthy brown and terracotta color scheme",
}


def _is_configured() -> bool:
    return bool(os.environ.get("RECRAFT_API_TOKEN"))


async def generate_logo_url(
    brand_name: str,
    style: str = "modern",
    color_palette: Optional[str] = None,
) -> Optional[str]:
    """
    Generate a vector logo via Recraft V3.
    Returns the image URL, or None if unconfigured or on error.
    """
    token = os.environ.get("RECRAFT_API_TOKEN")
    if not token:
        return None

    recraft_style = _STYLE_MAP.get(style, "vector_illustration")
    color_hint = _COLOR_HINTS.get(color_palette or "", "")
    color_part = f", {color_hint}" if color_hint else ""

    prompt = (
        f"Professional brand logo for '{brand_name}'. "
        f"Clean vector logo design{color_part}. "
        f"Simple, bold, memorable. Geometric shapes. "
        f"Suitable for e-commerce product brand. White background."
    )

    payload = {
        "model":  "recraftv3",
        "prompt": prompt,
        "style":  recraft_style,
        "n":      1,
    }

    async with httpx.AsyncClient(timeout=35.0) as client:
        resp = await client.post(
            f"{RECRAFT_BASE}/images/generations",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    images = data.get("data", [])
    if images:
        return images[0].get("url")
    return None
