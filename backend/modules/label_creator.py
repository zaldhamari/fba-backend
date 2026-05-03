import random


def generate_product_label(
    brand_name: str,
    product_name: str,
    weight: str = "1 oz (28g)",
    warnings: list[str] = None,
    style: str = "minimal",
) -> str:
    COLOR_SCHEMES = {
        "modern":  {"bg": "#1a1a2e", "accent": "#e94560", "text": "#ffffff", "sub": "#aaaaaa"},
        "premium": {"bg": "#1c1c1c", "accent": "#d4af37", "text": "#ffffff", "sub": "#888888"},
        "playful": {"bg": "#ff6b6b", "accent": "#ffd93d", "text": "#ffffff", "sub": "#fff0f0"},
        "minimal": {"bg": "#ffffff", "accent": "#000000", "text": "#000000", "sub": "#666666"},
    }
    c = COLOR_SCHEMES.get(style, COLOR_SCHEMES["minimal"])
    warnings = warnings or ["Keep out of reach of children.", "Made in China."]
    warning_text = " | ".join(warnings)
    short_product = product_name[:30] + ("…" if len(product_name) > 30 else "")
    short_brand = brand_name[:20]

    # Barcode bars (decorative — placeholder for real barcode)
    bars = ""
    widths = [1,2,1,3,1,2,2,1,3,1,2,1,1,3,2,1,1,2,3,1,2,1,3,1,2,2,1,1,3,2]
    x = 20
    for w in widths:
        bars += f'<rect x="{x}" y="155" width="{w}" height="30" fill="{c["accent"]}"/>'
        x += w + 1

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200">
  <!-- Background -->
  <rect width="300" height="200" rx="10" fill="{c['bg']}"/>
  <rect x="1" y="1" width="298" height="198" rx="9" fill="none" stroke="{c['accent']}" stroke-width="1.5"/>

  <!-- Brand name -->
  <text x="150" y="30" font-family="Arial,sans-serif" font-size="11" font-weight="700"
    fill="{c['accent']}" text-anchor="middle" letter-spacing="3">{short_brand.upper()}</text>

  <!-- Divider -->
  <rect x="20" y="38" width="260" height="1" fill="{c['accent']}" opacity="0.4"/>

  <!-- Product name -->
  <text x="150" y="72" font-family="Arial,sans-serif" font-size="18" font-weight="800"
    fill="{c['text']}" text-anchor="middle">{short_product}</text>

  <!-- Net weight -->
  <text x="150" y="95" font-family="Arial,sans-serif" font-size="10"
    fill="{c['sub']}" text-anchor="middle">NET WT. {weight}</text>

  <!-- Divider -->
  <rect x="20" y="108" width="260" height="1" fill="{c['accent']}" opacity="0.4"/>

  <!-- Barcode area -->
  <rect x="15" y="118" width="180" height="60" rx="4" fill="{c['bg']}"/>
  {bars}
  <text x="105" y="200" font-family="Arial,sans-serif" font-size="7"
    fill="{c['sub']}" text-anchor="middle">000000000000</text>

  <!-- QR placeholder -->
  <rect x="210" y="120" width="70" height="70" rx="4" fill="{c['accent']}" opacity="0.08"/>
  <text x="245" y="152" font-family="Arial,sans-serif" font-size="8"
    fill="{c['sub']}" text-anchor="middle">QR</text>
  <text x="245" y="164" font-family="Arial,sans-serif" font-size="8"
    fill="{c['sub']}" text-anchor="middle">CODE</text>

  <!-- Warning / country of origin -->
  <text x="150" y="185" font-family="Arial,sans-serif" font-size="6.5"
    fill="{c['sub']}" text-anchor="middle">{warning_text}</text>
</svg>"""
    return svg


def generate_insert_card(brand_name: str, product_name: str, style: str = "minimal") -> str:
    COLOR_SCHEMES = {
        "modern":  {"bg": "#1a1a2e", "accent": "#e94560", "text": "#ffffff", "sub": "#aaaaaa"},
        "premium": {"bg": "#1c1c1c", "accent": "#d4af37", "text": "#ffffff", "sub": "#888888"},
        "playful": {"bg": "#ff6b6b", "accent": "#ffd93d", "text": "#ffffff", "sub": "#fff0f0"},
        "minimal": {"bg": "#ffffff", "accent": "#000000", "text": "#000000", "sub": "#666666"},
    }
    c = COLOR_SCHEMES.get(style, COLOR_SCHEMES["minimal"])

    messages = [
        f"Thank you for choosing {brand_name}.",
        f"Your {product_name} was carefully inspected before shipping.",
        "We stand behind every product we make.",
        "If you're not 100% happy, reach out and we'll make it right.",
    ]

    review_ask = (
        "Enjoying your purchase? We'd love to hear from you.\n"
        "Leave us a review on Amazon — it takes 30 seconds\n"
        "and means the world to a small brand like ours."
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="180" viewBox="0 0 300 180">
  <rect width="300" height="180" rx="10" fill="{c['bg']}"/>
  <rect x="1" y="1" width="298" height="178" rx="9" fill="none" stroke="{c['accent']}" stroke-width="1.5"/>

  <!-- Brand -->
  <text x="150" y="28" font-family="Arial,sans-serif" font-size="10" font-weight="700"
    fill="{c['accent']}" text-anchor="middle" letter-spacing="3">{brand_name.upper()}</text>

  <rect x="20" y="35" width="260" height="1" fill="{c['accent']}" opacity="0.3"/>

  <!-- Main message -->
  <text x="150" y="60" font-family="Georgia,serif" font-size="15" font-style="italic"
    fill="{c['text']}" text-anchor="middle">Thank you.</text>

  <!-- Body lines -->
  <text x="150" y="82" font-family="Arial,sans-serif" font-size="8.5"
    fill="{c['sub']}" text-anchor="middle">{messages[1]}</text>
  <text x="150" y="96" font-family="Arial,sans-serif" font-size="8.5"
    fill="{c['sub']}" text-anchor="middle">{messages[2]}</text>
  <text x="150" y="110" font-family="Arial,sans-serif" font-size="8.5"
    fill="{c['sub']}" text-anchor="middle">{messages[3]}</text>

  <rect x="20" y="120" width="260" height="1" fill="{c['accent']}" opacity="0.3"/>

  <!-- Review ask -->
  <text x="150" y="136" font-family="Arial,sans-serif" font-size="8"
    fill="{c['text']}" text-anchor="middle" font-weight="600">Enjoying your purchase?</text>
  <text x="150" y="150" font-family="Arial,sans-serif" font-size="7.5"
    fill="{c['sub']}" text-anchor="middle">Leave us a review on Amazon — it takes 30 seconds</text>
  <text x="150" y="162" font-family="Arial,sans-serif" font-size="7.5"
    fill="{c['sub']}" text-anchor="middle">and means everything to a small brand like ours.</text>

  <!-- Star rating visual -->
  <text x="150" y="176" font-family="Arial,sans-serif" font-size="10"
    fill="{c['accent']}" text-anchor="middle">★ ★ ★ ★ ★</text>
</svg>"""
    return svg
