import random
import re

# Maps product-related words to relevant FBA/SEO keywords
KEYWORD_MAP = {
    # Kitchen / Home
    "cutting board": ["kitchen", "wooden", "bamboo", "non-slip", "large", "eco-friendly", "dishwasher safe", "chopping board", "food prep"],
    "knife": ["sharp", "stainless steel", "chef", "kitchen", "blade", "non-stick", "ergonomic handle", "professional"],
    "pan": ["non-stick", "cookware", "oven safe", "stainless steel", "frying pan", "kitchen", "induction", "dishwasher safe"],
    "pot": ["stainless steel", "non-stick", "cooking pot", "kitchen", "oven safe", "soup pot", "stockpot"],
    "mug": ["ceramic", "insulated", "travel mug", "coffee", "tea", "leak-proof", "microwave safe", "large capacity"],
    "bottle": ["water bottle", "insulated", "leak-proof", "BPA-free", "stainless steel", "reusable", "sports", "gym"],
    "organizer": ["storage", "space saving", "desk organizer", "kitchen organizer", "closet", "bamboo", "adjustable", "drawer"],
    "mat": ["non-slip", "anti-fatigue", "waterproof", "easy clean", "durable", "thick", "floor mat"],

    # Health / Fitness
    "yoga": ["non-slip", "thick", "eco-friendly", "exercise", "pilates", "meditation", "workout", "anti-tear", "fitness"],
    "posture": ["adjustable", "back support", "spine alignment", "ergonomic", "pain relief", "office", "brace", "corrector"],
    "resistance band": ["exercise", "workout", "strength training", "gym", "stretching", "set", "latex", "home gym"],
    "foam roller": ["massage", "muscle recovery", "physical therapy", "deep tissue", "workout", "gym", "trigger point"],
    "massager": ["electric", "deep tissue", "muscle relief", "rechargeable", "handheld", "neck", "back", "vibration"],
    "supplement": ["natural", "organic", "vitamin", "health", "wellness", "capsule", "non-GMO", "third party tested"],

    # Electronics / Tech
    "phone": ["case", "protection", "compatible", "drop-proof", "slim", "wireless", "charging", "shockproof"],
    "charger": ["fast charging", "USB-C", "wireless", "portable", "compatible", "cable", "power bank", "wall charger"],
    "stand": ["adjustable", "ergonomic", "desk", "phone stand", "laptop stand", "portable", "foldable", "non-slip"],
    "headphone": ["wireless", "noise cancelling", "Bluetooth", "over-ear", "earbuds", "bass", "microphone", "foldable"],
    "speaker": ["Bluetooth", "portable", "wireless", "waterproof", "bass", "outdoor", "rechargeable", "loud"],

    # Pet
    "dog": ["pet", "adjustable", "durable", "comfortable", "leash", "harness", "collar", "training", "reflective"],
    "cat": ["pet", "interactive", "toy", "scratcher", "comfortable", "indoor", "bed", "feeder"],
    "pet": ["durable", "washable", "comfortable", "adjustable", "safe", "non-toxic", "easy clean"],

    # Beauty / Personal Care
    "skin": ["natural", "organic", "moisturizing", "anti-aging", "gentle", "hypoallergenic", "dermatologist tested", "cruelty-free"],
    "hair": ["natural", "sulfate-free", "moisturizing", "strengthening", "growth", "nourishing", "argan oil"],
    "nail": ["gel", "long lasting", "quick dry", "non-toxic", "professional", "nail polish", "manicure"],

    # Kids / Toys
    "toy": ["educational", "age appropriate", "safe", "BPA-free", "durable", "non-toxic", "kids", "interactive", "STEM"],
    "puzzle": ["educational", "cognitive", "kids", "age appropriate", "colorful", "durable", "brain teaser"],
    "baby": ["BPA-free", "soft", "safe", "non-toxic", "washable", "infant", "toddler", "gentle"],

    # Outdoor / Sports
    "hiking": ["lightweight", "waterproof", "durable", "outdoor", "trail", "breathable", "backpack", "trekking"],
    "camping": ["portable", "lightweight", "waterproof", "durable", "outdoor", "survival", "compact"],
    "fishing": ["durable", "weather resistant", "professional", "beginner", "lightweight", "rod", "tackle"],

    # Office
    "desk": ["ergonomic", "adjustable", "space saving", "office", "home office", "sturdy", "laptop", "monitor"],
    "chair": ["ergonomic", "adjustable", "lumbar support", "comfortable", "office chair", "back support", "mesh"],
    "notebook": ["hardcover", "lined", "dotted", "journal", "planner", "spiral", "A5", "writing"],
}

UNIVERSAL_KEYWORDS = ["premium", "high quality", "durable", "best seller", "gift idea", "fast shipping", "easy to use"]


def generate_keywords(product_type: str) -> list[str]:
    product_lower = product_type.lower()
    keywords = []

    # Match against known product keywords
    for key, kws in KEYWORD_MAP.items():
        if key in product_lower:
            keywords.extend(kws)
            break

    # Always include the product words themselves (minus stop words)
    stop = {"a", "an", "the", "for", "with", "and", "or", "of", "in", "on", "at", "to", "by"}
    product_words = [w for w in product_lower.split() if w not in stop and len(w) > 2]
    keywords = product_words + keywords

    # Add a few universal ones
    keywords.extend(random.sample(UNIVERSAL_KEYWORDS, min(3, len(UNIVERSAL_KEYWORDS))))

    # Deduplicate while preserving order
    seen = set()
    result = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)

    return result[:20]


PREFIXES = {
    "modern": ["Apex", "Nova", "Flux", "Zeno", "Arc", "Vex", "Lux", "Eon", "Hex", "Omni"],
    "premium": ["Aurum", "Elara", "Solara", "Vanta", "Crest", "Luxe", "Vela", "Orin", "Seren", "Mira"],
    "playful": ["Zappy", "Breezo", "Snappy", "Popi", "Zippy", "Bingo", "Wingo", "Frizz", "Bizzy", "Nifty"],
    "minimal": ["Alto", "Form", "Bare", "Pure", "Line", "Edge", "Core", "Base", "Void", "Even"],
}

SUFFIXES = {
    "modern": ["Labs", "Tech", "Gear", "Works", "Hub", "Pro", "X", "One", "Go", "Plus"],
    "premium": ["Co", "Studio", "House", "Guild", "Atelier", "Maison", "& Co", "Collective", "Group", "Craft"],
    "playful": ["Buddy", "Zone", "Land", "World", "Club", "Fun", "Pal", "Crew", "Gang", "Squad"],
    "minimal": ["", "", ".", "-", "Co", "Studio", "Works", "Made", "Co", ""],
}

TAGLINES = {
    "modern": [
        "Built for what's next.",
        "Engineered for life.",
        "Designed to perform.",
        "Innovation in your hands.",
        "Next level, every day.",
    ],
    "premium": [
        "Crafted for the exceptional.",
        "Where quality meets elegance.",
        "Excellence, delivered.",
        "The finest, always.",
        "Elevate every moment.",
    ],
    "playful": [
        "Life's better with a little fun.",
        "Smile more. Worry less.",
        "Because boring is overrated.",
        "Adventure starts here.",
        "Bright ideas, bigger smiles.",
    ],
    "minimal": [
        "Less, but better.",
        "Simply made. Simply great.",
        "Clarity in every detail.",
        "Nothing extra. Nothing missing.",
        "Made well. Full stop.",
    ],
}


def _generate_name(product_type: str, keywords: list[str], style: str) -> str:
    style = style if style in PREFIXES else "modern"
    prefix_pool = PREFIXES[style]
    suffix_pool = SUFFIXES[style]

    keyword_parts = [k.strip().title() for k in keywords if k.strip()]
    prefix = random.choice(prefix_pool)
    suffix = random.choice(suffix_pool)

    strategies = [
        f"{prefix}{suffix}",
        f"{prefix} {suffix}".strip(),
        f"{prefix}{random.choice(keyword_parts)}" if keyword_parts else f"{prefix}",
        f"{random.choice(keyword_parts)}{suffix}".strip() if keyword_parts else f"{prefix}{suffix}",
    ]
    return random.choice(strategies).strip().rstrip(".")


def _generate_names(product_type: str, keywords: list[str], style: str, count: int = 5) -> list[str]:
    seen = set()
    names = []
    attempts = 0
    while len(names) < count and attempts < 50:
        name = _generate_name(product_type, keywords, style)
        if name not in seen and len(name) >= 3:
            seen.add(name)
            names.append(name)
        attempts += 1
    return names


def _generate_logo_svg(brand_name: str, style: str) -> str:
    COLOR_SCHEMES = {
        "modern": {"bg": "#1a1a2e", "accent": "#e94560", "text": "#ffffff"},
        "premium": {"bg": "#2c2c2c", "accent": "#d4af37", "text": "#ffffff"},
        "playful": {"bg": "#ff6b6b", "accent": "#ffd93d", "text": "#ffffff"},
        "minimal": {"bg": "#ffffff", "accent": "#000000", "text": "#000000"},
    }
    colors = COLOR_SCHEMES.get(style, COLOR_SCHEMES["modern"])
    initials = "".join(w[0].upper() for w in brand_name.split()[:2]) or brand_name[:2].upper()
    short_name = brand_name[:14] + ("…" if len(brand_name) > 14 else "")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100" viewBox="0 0 300 100">
  <rect width="300" height="100" rx="12" fill="{colors['bg']}"/>
  <circle cx="50" cy="50" r="30" fill="{colors['accent']}"/>
  <text x="50" y="57" font-family="Arial,sans-serif" font-size="22" font-weight="bold"
    fill="{colors['text']}" text-anchor="middle">{initials}</text>
  <text x="165" y="45" font-family="Arial,sans-serif" font-size="20" font-weight="bold"
    fill="{colors['text']}" text-anchor="middle">{short_name}</text>
  <rect x="90" y="52" width="150" height="2" fill="{colors['accent']}"/>
  <text x="165" y="72" font-family="Arial,sans-serif" font-size="11"
    fill="{colors['accent']}" text-anchor="middle" letter-spacing="2">BRAND</text>
</svg>"""
    return svg


def _generate_listing_copy(product_type: str, brand_name: str, keywords: list[str]) -> dict:
    kw_str = ", ".join(keywords) if keywords else product_type
    title = f"{brand_name} {product_type.title()} – Premium Quality | {keywords[0].title() if keywords else 'Top Rated'} | Fast Shipping"

    bullets = [
        f"PREMIUM QUALITY — Our {product_type} is built with superior materials for long-lasting performance and durability you can count on every day.",
        f"PERFECT FOR EVERYDAY USE — Whether at home, work, or on the go, {brand_name} delivers consistent results that make life easier.",
        f"THOUGHTFULLY DESIGNED — Engineered with the user in mind, featuring an ergonomic design that prioritizes comfort and ease of use.",
        f"TRUSTED BRAND — {brand_name} stands behind every product with a satisfaction guarantee. We make it right, every time.",
        f"GREAT GIFT IDEA — Makes the perfect gift for any occasion. Comes packaged and ready to give.",
    ]

    description = (
        f"Introducing {brand_name} — the {product_type} that changes the game. "
        f"We created {brand_name} because we believe you deserve a product that just works, "
        f"without compromise. Crafted with attention to every detail, our {product_type} combines "
        f"style and function in one seamless package. Whether you're a first-time buyer or a "
        f"seasoned enthusiast, {brand_name} is designed for you. "
        f"Join thousands of happy customers who've made the switch. "
        f"Order today and experience the {brand_name} difference."
    )

    backend_keywords = list({kw.lower() for kw in keywords}) + [
        product_type.lower(),
        "best",
        "premium",
        "quality",
        "buy",
        "top rated",
    ]

    return {
        "title": title[:200],
        "bullet_points": bullets,
        "description": description,
        "backend_keywords": backend_keywords[:10],
    }


def generate_brand(product_type: str, keywords: list[str], style: str = "modern") -> dict:
    style = style if style in PREFIXES else "modern"

    # Always auto-generate keywords; merge with any user-supplied ones
    auto_keywords = generate_keywords(product_type)
    merged_keywords = list(dict.fromkeys(keywords + auto_keywords))  # user first, then auto, deduped

    name_options = _generate_names(product_type, merged_keywords, style, count=5)
    primary_name = name_options[0]

    tagline = random.choice(TAGLINES[style])
    logo_svg = _generate_logo_svg(primary_name, style)
    listing = _generate_listing_copy(product_type, primary_name, merged_keywords)

    return {
        "brand_name": primary_name,
        "name_options": name_options,
        "tagline": tagline,
        "style": style,
        "logo_svg": logo_svg,
        "listing": listing,
        "generated_keywords": merged_keywords,
    }
