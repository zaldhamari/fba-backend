"""
Profit Simulation Engine — simulates multiple price/ad-spend scenarios.
Pure rule-based logic, no external API calls needed.
"""
from backend.modules.fba_calculator import calculate_fba_fees


def simulate(
    supplier_cost: float,
    weight_lbs: float,
    category: str,
    dimensions: dict = None,
    price_min: float = None,
    price_max: float = None,
    price_steps: int = 8,
    monthly_units_est: int = 150,
) -> dict:
    if dimensions is None:
        dimensions = {"length": 10, "width": 6, "height": 2}

    # Auto price range: 1.8x to 4.5x supplier cost, clamped to $8–$120
    lo = max(8.0, price_min or round(supplier_cost * 1.8, 2))
    hi = min(120.0, price_max or round(supplier_cost * 4.5, 2))
    step = (hi - lo) / max(price_steps - 1, 1)

    scenarios = []
    for i in range(price_steps):
        price = round(lo + step * i, 2)
        fba = calculate_fba_fees(
            selling_price=price,
            supplier_cost=supplier_cost,
            weight_lbs=weight_lbs,
            dimensions=dimensions,
            category=category,
        )

        # PPC estimate: ~15-25% of revenue at launch (tapers as reviews grow)
        ppc_rate = 0.20 if price < 25 else 0.18 if price < 50 else 0.15
        ppc_cost = round(price * ppc_rate, 2)

        profit_after_ppc = round(fba["profit"] - ppc_cost, 2)
        monthly_profit = round(profit_after_ppc * monthly_units_est, 2)
        monthly_revenue = round(price * monthly_units_est, 2)
        break_even_units = (
            round(supplier_cost * monthly_units_est / max(profit_after_ppc, 0.01))
            if profit_after_ppc > 0 else 9999
        )

        scenarios.append({
            "price": price,
            "margin_pct": fba["margin_pct"],
            "profit_per_unit": fba["profit"],
            "profit_after_ppc": profit_after_ppc,
            "ppc_cost_per_unit": ppc_cost,
            "monthly_revenue": monthly_revenue,
            "monthly_profit": monthly_profit,
            "break_even_units": min(break_even_units, 9999),
            "verdict": fba["verdict"],
            "viable": profit_after_ppc > 0 and fba["margin_pct"] >= 20,
        })

    # Identify sweet spot (best monthly profit with viable margin)
    viable = [s for s in scenarios if s["viable"]]
    sweet_spot = max(viable, key=lambda s: s["monthly_profit"]) if viable else None

    # Shipping variation estimates
    shipping_scenarios = _shipping_scenarios(supplier_cost, weight_lbs, monthly_units_est)

    return {
        "scenarios": scenarios,
        "sweet_spot": sweet_spot,
        "shipping_scenarios": shipping_scenarios,
        "assumptions": {
            "monthly_units": monthly_units_est,
            "ppc_rate": "15–20% of revenue",
            "storage": "standard size, monthly estimate",
        },
    }


def _shipping_scenarios(supplier_cost: float, weight_lbs: float, monthly_units: int) -> list[dict]:
    methods = [
        {"method": "Sea Freight", "days": "25–35", "cost_per_kg": 3.5},
        {"method": "Air Freight", "days": "5–7",   "cost_per_kg": 8.0},
        {"method": "Express",     "days": "3–5",   "cost_per_kg": 16.0},
    ]
    kg = weight_lbs * 0.453592
    results = []
    for m in methods:
        shipping_per_unit = round(kg * m["cost_per_kg"], 2)
        monthly_shipping = round(shipping_per_unit * monthly_units, 2)
        results.append({
            "method": m["method"],
            "transit_days": m["days"],
            "cost_per_unit": shipping_per_unit,
            "monthly_cost": monthly_shipping,
            "impact_on_margin": f"-{round((shipping_per_unit / max(supplier_cost, 1)) * 100, 1)}%",
        })
    return results
