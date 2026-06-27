#!/usr/bin/env python3
"""
BSR → Sales Model Calibration Script
=====================================
Usage:
  python3 -m backend.scripts.calibrate_bsr --csv observations.csv [--enrich-bsr]

Input CSV columns (header required):
  category_key          — internal key from CATEGORY_COEFFICIENTS
                          (e.g. "home_kitchen", "electronics")
  asin                  — Amazon ASIN (used only for --enrich-bsr)
  bsr                   — Best Sellers Rank at time of observation
                          (leave blank to fetch via Keepa with --enrich-bsr)
  observed_monthly_sales — verified unit sales per month

Accepted data sources for observed_monthly_sales
-------------------------------------------------
  • Jungle Scout / Helium 10 / AMZScout CSV exports (operator-supplied)
  • Real seller data from Seller Central Business Reports
  • Keepa's own sales-estimate field (if available in your plan tier)
  DO NOT use scraped estimates from unauthorised tools — garbage in, garbage out.

Behaviour
---------
  • Groups observations by category_key.
  • Requires a MINIMUM of 5 data points per category before fitting.
    Categories below the threshold keep their current coefficient and are
    marked "INSUFFICIENT DATA — using rule-of-thumb default".
  • Prints a side-by-side comparison table including R² and % change in
    the BSR=10,000 prediction. Does NOT auto-edit bsr_sales_model.py.
  • Outputs a ready-to-paste CATEGORY_COEFFICIENTS block for human review.

Example
-------
  python3 -m backend.scripts.calibrate_bsr --csv data/observations.csv

Enrich mode (requires KEEPA_API_KEY + SUPABASE_* env vars):
  python3 -m backend.scripts.calibrate_bsr --csv data/observations.csv --enrich-bsr
"""
import argparse
import asyncio
import csv
import math
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

# ── Constants ──────────────────────────────────────────────────────────────────

MIN_POINTS_FOR_FIT = 5


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ols_fit(data_points: List[Tuple[int, int]]) -> Tuple[float, float, float]:
    """
    Fit sales = a * BSR^(-b) via OLS on the log-log form.
    Returns (a, b, r_squared).
    """
    valid = [(bsr, sales) for bsr, sales in data_points if bsr > 0 and sales > 0]
    if len(valid) < 2:
        raise ValueError(f"Need at least 2 valid points, got {len(valid)}")

    xs = [math.log(bsr)   for bsr, _     in valid]
    ys = [math.log(sales) for _,   sales in valid]
    n  = len(xs)

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n

    ss_xy = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    ss_xx = sum((xs[i] - x_mean) ** 2               for i in range(n))
    ss_yy = sum((ys[i] - y_mean) ** 2               for i in range(n))

    if ss_xx == 0:
        raise ValueError("All BSR values are identical — cannot fit a slope.")

    slope = ss_xy / ss_xx
    b     = -slope
    a     = math.exp(y_mean - slope * x_mean)

    r_squared = (ss_xy ** 2 / (ss_xx * ss_yy)) if ss_yy > 0 else 1.0

    return round(a, 2), round(b, 6), round(r_squared, 4)


def _predict(a: float, b: float, bsr: int = 10_000) -> float:
    return a * (bsr ** -b)


def _pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return round((new - old) / old * 100, 1)


async def _enrich_missing_bsr(rows: List[dict]) -> List[dict]:
    """Fetch missing BSR values from Keepa (admin run; respects quotas)."""
    try:
        from backend.services.keepa_cache import get_cached_product
    except ImportError:
        print("ERROR: Keepa services not importable. Run from the repo root.", file=sys.stderr)
        sys.exit(1)

    enriched = []
    for row in rows:
        if row.get("bsr"):
            enriched.append(row)
            continue
        asin = row.get("asin", "").strip().upper()
        if not asin:
            print(f"  SKIP: no ASIN and no BSR for row {row}", file=sys.stderr)
            continue
        try:
            product, source = await get_cached_product(asin)
            if product.current_bsr:
                row = {**row, "bsr": product.current_bsr}
                print(f"  Enriched {asin}: BSR={product.current_bsr} (source={source})")
            else:
                print(f"  SKIP {asin}: Keepa returned no BSR", file=sys.stderr)
                continue
        except Exception as exc:
            print(f"  SKIP {asin}: Keepa error — {exc}", file=sys.stderr)
            continue
        enriched.append(row)
    return enriched


def _load_csv(path: str) -> List[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"category_key", "asin", "bsr", "observed_monthly_sales"}
        missing  = required - set(reader.fieldnames or [])
        if missing:
            print(f"ERROR: CSV missing columns: {missing}", file=sys.stderr)
            sys.exit(1)
        for i, row in enumerate(reader, start=2):
            try:
                bsr   = int(row["bsr"].strip())   if row["bsr"].strip()   else 0
                sales = int(row["observed_monthly_sales"].strip())
            except ValueError:
                print(f"  SKIP row {i}: non-integer bsr or sales", file=sys.stderr)
                continue
            if sales <= 0:
                print(f"  SKIP row {i}: sales must be positive", file=sys.stderr)
                continue
            rows.append({
                "category_key": row["category_key"].strip().lower(),
                "asin":         row["asin"].strip().upper(),
                "bsr":          bsr,
                "sales":        sales,
            })
    return rows


def _print_table(results: List[dict]) -> None:
    header = (
        f"{'Category':<20} {'Old a':>10} {'Old b':>8} {'New a':>10} {'New b':>8} "
        f"{'N':>4} {'R²':>6} {'Δ@10k%':>8} {'Status'}"
    )
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))
    for r in results:
        print(
            f"{r['category']:<20} {r['old_a']:>10.1f} {r['old_b']:>8.4f} "
            f"{str(r['new_a']):>10} {str(r['new_b']):>8} "
            f"{r['n']:>4} {str(r.get('r2', '')):>6} "
            f"{str(r.get('delta_pct', '')):>8} {r['status']}"
        )
    print("=" * len(header))


def _print_paste_block(results: List[dict]) -> None:
    print("\n# ── Ready-to-paste CATEGORY_COEFFICIENTS block ──────────────────")
    print("CATEGORY_COEFFICIENTS: Dict[str, Dict] = {")
    for r in results:
        a = r["new_a"]
        b = r["new_b"]
        cal = r["calibrated"]
        n   = r["n"] if cal else 0
        print(
            f'    "{r["category"]}":'
            f'    {{"a": {a}, "b": {b}, "calibrated": {str(cal)}, "calibration_n": {n}}},'
        )
    print("}")
    print(
        "\n# Review the table above before committing. "
        "Do not commit calibrated=True for categories marked INSUFFICIENT DATA."
    )


async def _main(csv_path: str, enrich_bsr: bool) -> None:
    from backend.services.bsr_sales_model import CATEGORY_COEFFICIENTS, _predict as _bsr_predict  # noqa

    rows = _load_csv(csv_path)
    print(f"Loaded {len(rows)} observations from {csv_path}")

    if enrich_bsr:
        print("Enriching missing BSR values from Keepa (this uses quota)...")
        rows = await _enrich_missing_bsr(rows)

    # Group by category
    by_cat: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
    for row in rows:
        if row["bsr"] and row["bsr"] > 0:
            by_cat[row["category_key"]].append((row["bsr"], row["sales"]))

    results = []
    all_keys = set(CATEGORY_COEFFICIENTS.keys())

    for cat_key, points in sorted(by_cat.items()):
        old_coeff = CATEGORY_COEFFICIENTS.get(cat_key, CATEGORY_COEFFICIENTS["default"])
        old_a, old_b = old_coeff["a"], old_coeff["b"]
        old_pred = _predict(old_a, old_b, 10_000)

        if len(points) < MIN_POINTS_FOR_FIT:
            results.append({
                "category":  cat_key,
                "old_a":     old_a,
                "old_b":     old_b,
                "new_a":     old_a,
                "new_b":     old_b,
                "n":         len(points),
                "r2":        "—",
                "delta_pct": "—",
                "status":    f"INSUFFICIENT DATA ({len(points)}<{MIN_POINTS_FOR_FIT}) — rule-of-thumb kept",
                "calibrated": False,
            })
            continue

        try:
            new_a, new_b, r2 = _ols_fit(points)
        except ValueError as exc:
            results.append({
                "category":  cat_key,
                "old_a":     old_a,
                "old_b":     old_b,
                "new_a":     old_a,
                "new_b":     old_b,
                "n":         len(points),
                "r2":        "ERR",
                "delta_pct": "—",
                "status":    f"FIT ERROR: {exc}",
                "calibrated": False,
            })
            continue

        new_pred   = _predict(new_a, new_b, 10_000)
        delta_pct  = _pct_change(old_pred, new_pred)
        results.append({
            "category":  cat_key,
            "old_a":     old_a,
            "old_b":     old_b,
            "new_a":     new_a,
            "new_b":     new_b,
            "n":         len(points),
            "r2":        r2,
            "delta_pct": f"{delta_pct:+.1f}%",
            "status":    "CALIBRATED",
            "calibrated": True,
        })

    # Categories with NO observations in the CSV — keep current values
    seen_cats = {r["category"] for r in results}
    for cat_key in sorted(all_keys):
        if cat_key not in seen_cats:
            old_coeff = CATEGORY_COEFFICIENTS[cat_key]
            results.append({
                "category":  cat_key,
                "old_a":     old_coeff["a"],
                "old_b":     old_coeff["b"],
                "new_a":     old_coeff["a"],
                "new_b":     old_coeff["b"],
                "n":         0,
                "r2":        "—",
                "delta_pct": "—",
                "status":    "NO DATA — rule-of-thumb kept",
                "calibrated": False,
            })

    results.sort(key=lambda r: r["category"])
    _print_table(results)
    _print_paste_block(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate BSR→sales model coefficients")
    parser.add_argument("--csv",        required=True, help="Path to observations CSV")
    parser.add_argument("--enrich-bsr", action="store_true",
                        help="Fetch missing BSR from Keepa (uses quota)")
    args = parser.parse_args()
    asyncio.run(_main(args.csv, args.enrich_bsr))


if __name__ == "__main__":
    main()
