"""Build the Redis indexes from committed seed artifacts.

Nothing is generated here — descriptions and attributes already exist in
`products.enriched.jsonl` and `heroes.yaml`. This step assembles documents,
embeds them, and loads two indexes. Safe to re-run; it recreates both.

    uv run python -m seed.load
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import yaml
from redisvl.index import SearchIndex
from redisvl.schema import IndexSchema

from app.embeddings import build_vectorizer
from app.models import Product
from app.settings import get_settings

ENRICHED = Path("seed/products.enriched.jsonl")
HEROES = Path("seed/heroes.yaml")
POLICY_DIR = Path("seed/policies")
EMBED_BATCH = 100


def spec_terms(product: Product) -> str:
    """Search-friendly variants of a waterproof rating.

    Redis tokenises on punctuation, so the "10,000mm" in a description becomes
    "10" and "000mm" — which would make the exact-term query in episode 1 fail
    for the wrong reason. Emitting unpunctuated variants keeps the hybrid demo
    honest rather than dependent on how a copywriter wrote a number.
    """
    if product.waterproof_mm <= 0:
        return ""
    mm = product.waterproof_mm
    return f"waterproof {mm}mm {mm} mm hydrostatic head rated {mm} taped seams"


def build_search_text(product: Product) -> str:
    """The single field BM25 scores against."""
    parts = [
        product.name,
        product.brand,
        product.category,
        product.description,
        product.material,
        f"{product.fit} fit",
        " ".join(product.colours),
        spec_terms(product),
    ]
    return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()


def to_document(product: Product, embedding: list[float]) -> dict[str, Any]:
    """Redis JSON document. Booleans become tag strings, which is what tags are."""
    return {
        "product_id": product.product_id,
        "name": product.name,
        "brand": product.brand,
        "category": product.category,
        "department": product.department,
        "in_stock": "true" if product.in_stock else "false",
        "material": product.material,
        "fit": product.fit,
        "sizes": product.sizes,
        "colours": product.colours,
        "price": product.price,
        "waterproof_mm": product.waterproof_mm,
        "description": product.description,
        "search_text": product.search_text,
        "embedding": embedding,
        "is_hero": "true" if product.is_hero else "false",
    }


def read_products() -> list[Product]:
    products: list[Product] = []

    for line in ENRICHED.read_text().splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        products.append(
            Product(
                product_id=raw["product_id"],
                name=raw["name"],
                brand=raw["brand"],
                category=raw["category"],
                department=raw["department"],
                price=raw["price_eur"],
                cost=raw.get("cost_eur"),
                in_stock=raw["in_stock"],
                description=raw["description"],
                material=raw["material"],
                fit=raw["fit"],
                sizes=raw["sizes"],
                colours=raw["colours"],
                waterproof_mm=raw.get("waterproof_mm", 0),
            )
        )

    for entry in yaml.safe_load(HEROES.read_text()):
        if "product_id" not in entry:  # documentation-only entries
            continue
        products.append(
            Product(
                product_id=entry["product_id"],
                name=entry["name"],
                brand=entry["brand"],
                category=entry["category"],
                department="Women",
                price=entry["price_eur"],
                cost=entry.get("cost_eur"),
                in_stock=entry["in_stock"],
                is_hero=True,
                description=" ".join(entry["description"].split()),
                material=entry["material"],
                fit=entry["fit"],
                sizes=entry["sizes"],
                colours=entry["colours"],
                waterproof_mm=entry.get("waterproof_mm", 0),
            )
        )

    for product in products:
        product.search_text = build_search_text(product)
    return products


def read_policy_chunks() -> list[dict[str, Any]]:
    """Split each policy document on its `## ` section headings."""
    chunks: list[dict[str, Any]] = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        text = path.read_text()
        _, frontmatter, body = text.split("---", 2)
        meta = yaml.safe_load(frontmatter)
        sections = re.split(r"^## ", body, flags=re.M)[1:]
        for i, section in enumerate(sections):
            heading, _, content = section.partition("\n")
            chunks.append(
                {
                    "policy_id": meta["policy_id"],
                    "title": f"{meta['title']} — {heading.strip()}",
                    "topic": meta["topic"],
                    "chunk_index": i,
                    "body": " ".join(content.split()),
                }
            )
    return chunks


def main() -> None:
    settings = get_settings()
    vectorizer = build_vectorizer(settings)

    products = read_products()
    heroes = sum(1 for p in products if p.is_hero)
    print(f"products: {len(products)} ({heroes} hero, {len(products) - heroes} catalogue)")

    started = time.perf_counter()
    vectors = vectorizer.embed_many(
        [p.to_embedding_input() for p in products], batch_size=EMBED_BATCH
    )
    print(f"  embedded in {time.perf_counter() - started:.1f}s")

    index = SearchIndex(IndexSchema.from_yaml("schemas/products.yaml"), redis_url=settings.redis_url)
    index.create(overwrite=True, drop=True)
    index.load(
        [to_document(p, v) for p, v in zip(products, vectors, strict=True)],
        id_field="product_id",
    )
    print(f"  loaded into '{index.name}'")

    chunks = read_policy_chunks()
    print(f"\npolicy chunks: {len(chunks)} from {len(list(POLICY_DIR.glob('*.md')))} documents")

    started = time.perf_counter()
    chunk_vectors = vectorizer.embed_many(
        [f"{c['title']}. {c['body']}" for c in chunks], batch_size=EMBED_BATCH
    )
    print(f"  embedded in {time.perf_counter() - started:.1f}s")

    policy_index = SearchIndex(
        IndexSchema.from_yaml("schemas/policies.yaml"), redis_url=settings.redis_url
    )
    policy_index.create(overwrite=True, drop=True)
    policy_index.load(
        [
            {**chunk, "embedding": vector, "id": f"{chunk['policy_id']}-{chunk['chunk_index']}"}
            for chunk, vector in zip(chunks, chunk_vectors, strict=True)
        ],
        id_field="id",
    )
    print(f"  loaded into '{policy_index.name}'")
    print("\ndone")


if __name__ == "__main__":
    main()
