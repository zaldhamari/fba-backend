"""
FBA Fee calculator based on Amazon's published fee structure (2024).
https://sell.amazon.com/fulfillment-by-amazon/fba-fees
"""

REFERRAL_FEES = {
    "electronics": 0.08,
    "home": 0.15,
    "kitchen": 0.15,
    "sports": 0.15,
    "toys": 0.15,
    "beauty": 0.15,
    "clothing": 0.17,
    "tools": 0.15,
    "books": 0.15,
    "all": 0.15,
}

# Dimensional weight divisor (cubic inches / 139 = dim weight in lbs)
DIM_WEIGHT_DIVISOR = 139


def _calculate_dim_weight(dims: dict) -> float:
    l = dims.get("length", 0)
    w = dims.get("width", 0)
    h = dims.get("height", 0)
    return (l * w * h) / DIM_WEIGHT_DIVISOR


def _get_size_tier(weight_lbs: float, dims: dict) -> str:
    l = dims.get("length", 0)
    w = dims.get("width", 0)
    h = dims.get("height", 0)
    longest = max(l, w, h)
    median = sorted([l, w, h])[1]
    shortest = min(l, w, h)
    girth = 2 * (median + shortest)

    if weight_lbs <= 0.75 and longest <= 15 and median <= 12 and shortest <= 0.75:
        return "small_standard"
    elif weight_lbs <= 20 and longest <= 18 and median <= 14 and shortest <= 8:
        return "large_standard"
    elif weight_lbs <= 70 and longest <= 60 and (longest + girth) <= 130:
        return "small_oversize"
    elif weight_lbs <= 150 and longest <= 108 and (longest + girth) <= 165:
        return "medium_oversize"
    else:
        return "large_oversize"


def _get_fulfillment_fee(size_tier: str, billable_weight: float) -> float:
    # Amazon FBA fee schedule 2024 (approximate)
    if size_tier == "small_standard":
        if billable_weight <= 2:
            return 3.22
        return 3.22 + max(0, (billable_weight - 2)) * 0.51
    elif size_tier == "large_standard":
        if billable_weight <= 1:
            return 3.86
        elif billable_weight <= 2:
            return 4.08
        elif billable_weight <= 3:
            return 4.24
        elif billable_weight <= 20:
            return 4.24 + (billable_weight - 3) * 0.32
        return 4.24 + 17 * 0.32 + (billable_weight - 20) * 0.32
    elif size_tier == "small_oversize":
        return 9.39 + max(0, (billable_weight - 2)) * 0.53
    elif size_tier == "medium_oversize":
        return 14.35 + max(0, (billable_weight - 2)) * 0.53
    else:
        return 137.32 + max(0, (billable_weight - 90)) * 0.83


def calculate_fba_fees(
    selling_price: float,
    supplier_cost: float,
    weight_lbs: float,
    dimensions: dict,
    category: str = "all",
) -> dict:
    referral_rate = REFERRAL_FEES.get(category, 0.15)
    referral_fee = round(selling_price * referral_rate, 2)
    referral_fee = max(referral_fee, 0.30)  # $0.30 minimum

    dim_weight = _calculate_dim_weight(dimensions)
    billable_weight = max(weight_lbs, dim_weight)
    size_tier = _get_size_tier(weight_lbs, dimensions)
    fulfillment_fee = round(_get_fulfillment_fee(size_tier, billable_weight), 2)

    # Storage fee estimate: $0.87/cubic ft/month (standard)
    cubic_ft = (dimensions.get("length", 0) * dimensions.get("width", 0) * dimensions.get("height", 0)) / 1728
    monthly_storage = round(cubic_ft * 0.87, 2)

    total_fees = referral_fee + fulfillment_fee + monthly_storage
    profit = selling_price - supplier_cost - total_fees
    margin_pct = round((profit / selling_price) * 100, 1) if selling_price > 0 else 0
    roi = round((profit / supplier_cost) * 100, 1) if supplier_cost > 0 else 0

    return {
        "selling_price": selling_price,
        "supplier_cost": supplier_cost,
        "fees": {
            "referral_fee": referral_fee,
            "fulfillment_fee": fulfillment_fee,
            "monthly_storage": monthly_storage,
            "total_fees": round(total_fees, 2),
        },
        "profit": round(profit, 2),
        "margin_pct": margin_pct,
        "roi_pct": roi,
        "size_tier": size_tier,
        "billable_weight_lbs": round(billable_weight, 2),
        "viable": margin_pct >= 25,
        "verdict": (
            "Excellent" if margin_pct >= 40 else
            "Good" if margin_pct >= 25 else
            "Marginal" if margin_pct >= 15 else
            "Not viable"
        ),
    }
