"""Generate product descriptions and attributes for the catalogue.

Run once; the output is committed, so nobody needs an API key to run the app.

Two deliberate constraints:

  * Attributes come back as structured fields, not prose. Those fields become
    the filterable facets in the UI — the prose is rendered from them. Getting
    JSON rather than paragraphs is what makes episode 1's filters possible.
  * `waterproof_mm` is NOT generated here. Every product in this file carries a
    real brand name, and we do not attach invented technical specifications to
    real brands. Specific numeric performance claims live only on the invented
    house-brand hero products in seed/heroes.jsonl.

Usage:
    uv run python -m scripts.generate_descriptions            # all pending
    uv run python -m scripts.generate_descriptions --limit 20 # sample first
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.settings import get_settings

SRC = Path("seed/products.raw.jsonl")
OUT = Path("seed/products.enriched.jsonl")

MODEL = "gpt-5.4-mini"
CONCURRENCY = 16
PROMPT_VERSION = 4

Fit = Literal["slim", "regular", "relaxed", "oversized", "true to size"]

# Category -> (group label, allowed size run). Groups exist because the
# attributes that matter differ: a bralette needs band/cup language, a jean
# needs rise and leg, and one shared schema for both is useless.
SIZE_APPAREL = ["XS", "S", "M", "L", "XL", "XXL"]
SIZE_SMALL = ["S", "M", "L"]
SIZE_ONE = ["one size"]

GROUPS: dict[str, tuple[str, list[str]]] = {
    "Outerwear & Coats": ("outerwear", SIZE_APPAREL),
    "Blazers & Jackets": ("outerwear", SIZE_APPAREL),
    "Tops & Tees": ("tops", SIZE_APPAREL),
    "Sweaters": ("tops", SIZE_APPAREL),
    "Fashion Hoodies & Sweatshirts": ("tops", SIZE_APPAREL),
    "Jeans": ("bottoms", SIZE_APPAREL),
    "Pants & Capris": ("bottoms", SIZE_APPAREL),
    "Shorts": ("bottoms", SIZE_APPAREL),
    "Skirts": ("bottoms", SIZE_APPAREL),
    "Leggings": ("bottoms", SIZE_APPAREL),
    "Dresses": ("dresses", SIZE_APPAREL),
    "Jumpsuits & Rompers": ("dresses", SIZE_APPAREL),
    "Suits": ("dresses", SIZE_APPAREL),
    "Clothing Sets": ("dresses", SIZE_APPAREL),
    "Maternity": ("dresses", SIZE_APPAREL),
    "Plus": ("tops", ["1X", "2X", "3X", "4X"]),
    "Intimates": ("intimates", SIZE_APPAREL),
    "Sleep & Lounge": ("intimates", SIZE_APPAREL),
    "Swim": ("intimates", SIZE_APPAREL),
    "Socks & Hosiery": ("intimates", SIZE_SMALL),
    "Active": ("active", SIZE_APPAREL),
    "Accessories": ("accessories", SIZE_ONE),
}

GROUP_GUIDANCE: dict[str, str] = {
    "outerwear": "Cover shell/lining, warmth, weather suitability in everyday terms, pockets and closures.",
    "tops": "Cover neckline, sleeve length, knit or weave, weight and layering.",
    "bottoms": "Cover rise, leg shape, stretch, waistband and length.",
    "dresses": "Cover silhouette, length, neckline, sleeves and lining.",
    "intimates": "Cover support, coverage, fabric feel and seam finish. Keep it factual and unsexualised.",
    "active": "Cover moisture handling, stretch, support and intended activity.",
    "accessories": "Cover materials, dimensions and how it is worn or carried.",
}


class Enrichment(BaseModel):
    """Structured attributes for one product."""

    description: str = Field(description="Two or three sentences of retail copy.")
    material: str = Field(description="Primary fabric, lowercase, e.g. 'organic cotton jersey'.")
    fit: Fit
    care: str = Field(description="Short care instruction, e.g. 'machine wash cold'.")
    colours: list[str] = Field(
        description=(
            "Two to four actual colours, single word, lowercase: black, navy, ecru, "
            "olive, rust. These become UI facets, so patterns and prints are never "
            "valid values - no striped, floral, print, multicolour or assorted."
        )
    )
    sizes: list[str] = Field(description="Available sizes, chosen from the allowed run.")


SYSTEM = """You write product copy for Northwind Outfitters, a women's apparel retailer.

Rules:
- Two or three sentences. Concrete and specific. No hype, no "elevate your wardrobe".
- Describe only what the product name, brand and category support.
- Never invent numeric performance claims (no waterproof ratings, no thread counts,
  no temperature ratings). These are real brands and we do not put figures in their mouths.
- Never mention price, discounts, stock or shipping.
- Vary sentence structure between products.
- Colours must be real colours, never patterns or prints."""


def user_prompt(product: dict[str, Any]) -> str:
    group, sizes = GROUPS.get(product["category"], ("tops", SIZE_APPAREL))
    return (
        f"Product name: {product['name']}\n"
        f"Brand: {product['brand']}\n"
        f"Category: {product['category']} (women's)\n"
        f"Price band: EUR {product['price_eur']:.2f}\n\n"
        f"Focus: {GROUP_GUIDANCE[group]}\n"
        f"Choose sizes only from: {', '.join(sizes)}\n"
        f"Keep the copy consistent with the price band."
    )


def load_pending(limit: int | None) -> list[dict[str, Any]]:
    products = [json.loads(line) for line in SRC.read_text().splitlines() if line.strip()]
    done: set[str] = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                if record.get("prompt_version") == PROMPT_VERSION:
                    done.add(record["product_id"])
    pending = [p for p in products if p["product_id"] not in done]
    print(f"{len(products)} products, {len(done)} already done, {len(pending)} pending")
    return pending[:limit] if limit else pending


async def enrich(
    client: AsyncOpenAI,
    product: dict[str, Any],
    sem: asyncio.Semaphore,
    usage: dict[str, int],
) -> dict[str, Any] | None:
    async with sem:
        try:
            completion = await client.chat.completions.parse(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user_prompt(product)},
                ],
                response_format=Enrichment,
            )
        except Exception as exc:  # surfaced, never silently dropped
            print(f"  !! {product['product_id']} {product['name'][:40]}: {exc}")
            return None

        if completion.usage:
            usage["in"] += completion.usage.prompt_tokens
            usage["out"] += completion.usage.completion_tokens

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            print(f"  !! {product['product_id']}: no parsed output")
            return None

        return {
            **product,
            **parsed.model_dump(),
            "waterproof_mm": 0,  # see module docstring
            "prompt_version": PROMPT_VERSION,
        }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    pending = load_pending(args.limit)
    if not pending:
        print("nothing to do")
        return

    client = AsyncOpenAI(api_key=get_settings().openai_api_key)
    sem = asyncio.Semaphore(CONCURRENCY)
    usage = {"in": 0, "out": 0}

    written = 0
    with OUT.open("a") as fh:
        tasks = [asyncio.create_task(enrich(client, p, sem, usage)) for p in pending]
        for coro in asyncio.as_completed(tasks):
            record = await coro
            if record is None:
                continue
            fh.write(json.dumps(record, sort_keys=True) + "\n")
            fh.flush()
            written += 1
            if written % 50 == 0:
                print(f"  {written}/{len(pending)}")

    print(f"\nwrote {written} records to {OUT}")
    print(f"tokens: {usage['in']:,} in / {usage['out']:,} out  (model {MODEL})")


if __name__ == "__main__":
    asyncio.run(main())
