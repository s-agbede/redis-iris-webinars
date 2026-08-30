"""Normalise the denormalised The Look extract into per-entity JSONL spines.

The source CSV is a join of order_items x orders x products x users (women's
apparel, France, 2023-2024) taken from Google's public `thelook_ecommerce`
BigQuery dataset. Prices are USD in the source and converted here at a fixed
documented rate so the seed stays deterministic.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

SRC = Path("seed/thelook_raw.csv")
OUT = Path("seed")

USD_TO_EUR = 0.92  # fixed rate; recorded in README so the seed is reproducible
IN_STOCK_RATE = 0.78


def to_retail_eur(usd_prices: list[float]) -> float:
    """Highest observed sale price, converted and rounded to a .99 price point."""
    eur = max(usd_prices) * USD_TO_EUR
    return max(round(eur) - 0.01, 0.99)


def main() -> None:
    rows = list(csv.DictReader(SRC.open()))

    prices: dict[str, list[float]] = defaultdict(list)
    costs: dict[str, list[float]] = defaultdict(list)
    products: dict[str, dict[str, Any]] = {}

    for r in rows:
        pid = r["product_id"]
        prices[pid].append(float(r["sale_price"]))
        costs[pid].append(float(r["cost"]))
        products.setdefault(
            pid,
            {
                "product_id": f"P{int(pid):05d}",
                "source_id": int(pid),
                "name": r["product_name"].strip(),
                "brand": r["brand"].strip(),
                "category": r["category"].strip(),
                "department": r["department"].strip(),
            },
        )

    for pid, p in products.items():
        rng = random.Random(f"stock-{pid}")  # deterministic per product
        p["price_eur"] = to_retail_eur(prices[pid])
        p["cost_eur"] = round(statistics.mean(costs[pid]) * USD_TO_EUR, 2)
        p["in_stock"] = rng.random() < IN_STOCK_RATE
        p["is_hero"] = False

    users: dict[str, dict[str, Any]] = {}
    for r in rows:
        users.setdefault(
            r["user_id"],
            {
                "customer_id": f"C{int(r['user_id']):05d}",
                "source_id": int(r["user_id"]),
                "gender": r["gender"],
                "country": r["country"],
                "state": r["state"],
                "city": r["city"],
            },
        )

    orders: dict[str, dict[str, Any]] = {}
    for r in rows:
        oid = r["order_id"]
        o = orders.setdefault(
            oid,
            {
                "order_id": f"O{int(oid):06d}",
                "customer_id": f"C{int(r['user_id']):05d}",
                "status": r["order_status"],
                "created_at": r["order_created_at"] or None,
                "shipped_at": r["shipped_at"] or None,
                "delivered_at": r["delivered_at"] or None,
                "items": [],
            },
        )
        o["items"].append(
            {
                "order_item_id": f"OI{int(r['order_item_id']):06d}",
                "product_id": f"P{int(r['product_id']):05d}",
                "status": r["item_status"],
                "unit_price_eur": round(float(r["sale_price"]) * USD_TO_EUR, 2),
            }
        )

    for name, records in [
        ("products.raw.jsonl", products.values()),
        ("customers.raw.jsonl", users.values()),
        ("orders.raw.jsonl", orders.values()),
    ]:
        path = OUT / name
        with path.open("w") as fh:
            for rec in records:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
        print(f"{path}  {sum(1 for _ in records):>5} records")

    in_stock = sum(1 for p in products.values() if p["in_stock"])
    print(f"\nproducts   {len(products)}  ({in_stock} in stock)")
    print(f"customers  {len(users)}")
    print(f"orders     {len(orders)}  ({len(rows)} items)")
    print(f"brands     {len({p['brand'] for p in products.values()})}")
    print(f"categories {len({p['category'] for p in products.values()})}")
    lo = min(p["price_eur"] for p in products.values())
    hi = max(p["price_eur"] for p in products.values())
    med = statistics.median(p["price_eur"] for p in products.values())
    print(f"price EUR  {lo:.2f} – {hi:.2f}  (median {med:.2f})")


if __name__ == "__main__":
    main()
