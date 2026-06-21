"""
FBA Fee calculator based on Amazon's published fee structure.

Rates last verified: 2026 rate card, effective Jan 15 2026, non-apparel,
non-dangerous-goods, non-peak season — price-banded (<$10 / $10-$50 / >$50),
includes the 3.5% fuel and logistics surcharge effective Apr 17 2026.
Source: Amazon Seller Central > Reports > Fulfillment > Fee Preview.

Re-verify periodically — Amazon revises this schedule at least annually, and
publishes corrections during the year. Not modeled yet: apparel/dangerous-goods
fee variants, inbound placement service fees, aged-inventory surcharges,
low-inventory-level fees, return-processing fees, and the Q4 peak storage
multiplier. These are real Amazon fee line items this calculator doesn't
account for — flagged here rather than silently omitted.
"""
import math

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

# Fuel and logistics-related surcharge, effective Apr 17 2026 — layers on top
# of every published FBA fulfillment fee.
FUEL_SURCHARGE_RATE = 0.035

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


def _price_band(selling_price: float) -> int:
    """0 = <$10 (Low Price FBA discount already baked into these rates),
       1 = $10-$50, 2 = >$50."""
    if selling_price < 10:
        return 0
    if selling_price <= 50:
        return 1
    return 2


# Each entry: (weight upper bound in lbs, (fee at <$10, fee at $10-50, fee at >$50))
_SMALL_STANDARD = [
    (2 / 16,  (2.43, 3.32, 3.58)),
    (4 / 16,  (2.49, 3.42, 3.68)),
    (6 / 16,  (2.56, 3.45, 3.71)),
    (8 / 16,  (2.66, 3.54, 3.80)),
    (10 / 16, (2.77, 3.68, 3.94)),
    (12 / 16, (2.82, 3.78, 4.04)),
    (14 / 16, (2.92, 3.91, 4.17)),
    (1.0,     (2.95, 3.96, 4.22)),
]

_LARGE_STANDARD = [
    (4 / 16,  (2.91, 3.73, 3.99)),
    (8 / 16,  (3.13, 3.95, 4.21)),
    (12 / 16, (3.38, 4.20, 4.46)),
    (1.0,     (3.78, 4.60, 4.86)),
    (1.25,    (4.22, 5.04, 5.30)),
    (1.5,     (4.60, 5.42, 5.68)),
    (1.75,    (4.75, 5.57, 5.83)),
    (2.0,     (5.00, 5.82, 6.08)),
    (2.25,    (5.10, 5.92, 6.18)),
    (2.5,     (5.28, 6.10, 6.36)),
    (2.75,    (5.44, 6.26, 6.52)),
    (3.0,     (5.85, 6.67, 6.93)),
]
# Base fee for >3lb up to 20lb, then +$0.08 per 4oz increment above 3lb
_LARGE_STANDARD_OVER_3LB_BASE = (6.15, 6.97, 7.23)

# Oversize tiers: (base fee per price band, $/lb above free_lb, free_lb threshold)
_SMALL_BULKY  = ((6.78, 7.55, 7.55), 0.38, 1)
_LARGE_BULKY  = ((8.58, 9.35, 9.35), 0.38, 1)
_XL_0_50      = ((25.56, 26.33, 26.33), 0.38, 1)
_XL_50_70     = ((36.55, 37.32, 37.32), 0.75, 51)
_XL_70_150    = ((50.55, 51.32, 51.32), 0.75, 71)
_XL_150_PLUS  = ((194.18, 194.95, 194.95), 0.19, 151)


def _lookup_tiered(weight_lbs: float, table: list, band: int):
    for upper, fees in table:
        if weight_lbs <= upper:
            return fees[band]
    return None


def _get_fulfillment_fee(size_tier: str, billable_weight: float, selling_price: float) -> float:
    band = _price_band(selling_price)

    if size_tier == "small_standard":
        fee = _lookup_tiered(billable_weight, _SMALL_STANDARD, band)
        if fee is None:
            fee = _SMALL_STANDARD[-1][1][band]

    elif size_tier == "large_standard":
        fee = _lookup_tiered(billable_weight, _LARGE_STANDARD, band)
        if fee is None:
            base = _LARGE_STANDARD_OVER_3LB_BASE[band]
            increments_over_3lb = max(0, math.ceil((billable_weight - 3) / 0.25))
            fee = base + increments_over_3lb * 0.08

    elif size_tier == "small_oversize":
        base, per_lb, free_lb = _SMALL_BULKY
        fee = base[band] + max(0, billable_weight - free_lb) * per_lb

    elif size_tier == "medium_oversize":
        base, per_lb, free_lb = _LARGE_BULKY
        fee = base[band] + max(0, billable_weight - free_lb) * per_lb

    else:  # large_oversize → Amazon's "Extra-large", weight-banded
        if billable_weight <= 50:
            base, per_lb, free_lb = _XL_0_50
        elif billable_weight <= 70:
            base, per_lb, free_lb = _XL_50_70
        elif billable_weight <= 150:
            base, per_lb, free_lb = _XL_70_150
        else:
            base, per_lb, free_lb = _XL_150_PLUS
        fee = base[band] + max(0, billable_weight - free_lb) * per_lb

    return fee * (1 + FUEL_SURCHARGE_RATE)


# Estimated cubic inches per pound when packaged (bulkiness by category)
_DENSITY: dict[str, float] = {
    "clothing": 160, "sports": 130, "toys": 140, "home": 120,
    "kitchen": 100, "beauty": 100, "electronics": 60, "tools": 70,
    "books": 50, "all": 110,
}

# Standard FBA cartons: (L, W, H) in inches — smallest to largest
_CARTONS = [
    (12, 10, 8), (16, 12, 10), (18, 14, 12),
    (20, 16, 12), (20, 20, 16), (24, 18, 14),
    (25, 25, 20), (25, 25, 25),  # Amazon max
]
_MAX_CARTON_WEIGHT = 50.0   # lbs
_PACK_EFF = 0.68            # 68% usable volume (packing material / gaps)


def calculate_shipment(
    weight_lbs: float,
    dimensions: dict,
    quantity: int,
    category: str = "all",
) -> dict:
    quantity = max(1, quantity)

    l, w, h = dimensions.get("length", 0), dimensions.get("width", 0), dimensions.get("height", 0)
    vol_per_item = (l * w * h) if (l > 0 and w > 0 and h > 0) else (
        weight_lbs * _DENSITY.get(category, 110)
    )
    vol_per_item = max(vol_per_item, 1.0)

    max_by_weight = max(1, int(_MAX_CARTON_WEIGHT / weight_lbs))

    # Pick the smallest carton that fits ≥ 4 items
    chosen = _CARTONS[-1]
    units_per = max(1, max_by_weight)
    for cl, cw, ch in _CARTONS:
        usable = cl * cw * ch * _PACK_EFF
        by_vol = max(1, int(usable / vol_per_item))
        upc = min(max_by_weight, by_vol)
        if upc >= 4:
            chosen = (cl, cw, ch)
            units_per = upc
            break

    carton_count = math.ceil(quantity / units_per)
    return {
        "quantity": quantity,
        "total_weight_lbs": round(weight_lbs * quantity, 1),
        "carton_count": carton_count,
        "carton_dims": {"length": chosen[0], "width": chosen[1], "height": chosen[2]},
        "units_per_carton": units_per,
        "carton_weight_lbs": round(weight_lbs * units_per, 1),
    }


def calculate_fba_fees(
    selling_price: float,
    supplier_cost: float,
    weight_lbs: float,
    dimensions: dict,
    category: str = "all",
    quantity: int = 1,
) -> dict:
    referral_rate = REFERRAL_FEES.get(category, 0.15)
    referral_fee = round(selling_price * referral_rate, 2)
    referral_fee = max(referral_fee, 0.30)  # $0.30 minimum

    dim_weight = _calculate_dim_weight(dimensions)
    billable_weight = max(weight_lbs, dim_weight)
    size_tier = _get_size_tier(weight_lbs, dimensions)
    fulfillment_fee = round(_get_fulfillment_fee(size_tier, billable_weight, selling_price), 2)

    # Storage fee estimate: $0.78/cubic ft/month (2026 standard off-peak rate,
    # below the 22-week storage-utilization-surcharge threshold). Real rate
    # varies by season (Q4 peak is ~3x) and utilization ratio — see module
    # docstring for what's not modeled here.
    cubic_ft = (dimensions.get("length", 0) * dimensions.get("width", 0) * dimensions.get("height", 0)) / 1728
    monthly_storage = round(cubic_ft * 0.78, 2)

    total_fees = referral_fee + fulfillment_fee + monthly_storage
    profit = selling_price - supplier_cost - total_fees
    margin_pct = round((profit / selling_price) * 100, 1) if selling_price > 0 else 0
    roi = round((profit / supplier_cost) * 100, 1) if supplier_cost > 0 else 0

    qty = max(1, quantity)
    shipment = calculate_shipment(weight_lbs, dimensions, qty, category)

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
        "shipment": {
            **shipment,
            "total_inventory_cost": round(supplier_cost * qty, 2),
            "total_revenue": round(selling_price * qty, 2),
            "total_profit": round(profit * qty, 2),
        },
    }
