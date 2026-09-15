"""Load the bundled camera source data using the pinned local model."""

import argparse
import json
import time
from typing import Any, cast

import yaml
from redis import Redis
from redis.exceptions import ResponseError
from redisvl.index import SearchIndex

from app.catalog import Catalog, make_passages
from app.embeddings import build_vectorizer
from app.search import index_identity
from app.settings import ROOT, Settings, get_settings


def current_manifest(client: Any, settings: Settings, catalog: Catalog) -> dict[str, Any] | None:
    """An interrupted, outdated or missing index must be rebuilt before serving."""
    raw = client.get(settings.manifest_key)
    if not raw:
        return None
    manifest: dict[str, Any] = json.loads(raw)
    if any(manifest.get(k) != v for k, v in index_identity(settings, catalog).items()):
        return None
    try:
        raw_info = client.execute_command("FT.INFO", settings.products_index)
    except ResponseError as exc:
        if "unknown index" in str(exc).lower() or "no such index" in str(exc).lower():
            return None
        raise
    info = dict(zip(raw_info[::2], raw_info[1::2], strict=True))
    if int(info[b"num_docs"]) != manifest.get("passage_count") or int(info[b"indexing"]):
        return None
    return manifest


def load(settings: Settings, *, if_needed: bool = False) -> dict[str, Any]:
    catalog = Catalog.load(settings.data_dir)
    if if_needed:
        with Redis.from_url(
            settings.redis_url, socket_connect_timeout=3, socket_timeout=15
        ) as client:
            existing = current_manifest(client, settings, catalog)
        if existing is not None:
            print(f"Reusing {existing['passage_count']:,} indexed camera passages.", flush=True)
            return existing
    encoder = build_vectorizer(settings)
    passages = [
        passage
        for product in catalog.products.values()
        for passage in make_passages(
            product, encoder.tokenizer, settings.passage_tokens, settings.passage_overlap
        )
    ]
    print(f"{len(catalog.products):,} products; {len(passages):,} source passages", flush=True)
    schema = yaml.safe_load((ROOT / "schemas/passages.yaml").read_text())
    schema["index"].update(name=settings.products_index, prefix=settings.passage_prefix)
    schema["fields"][-1]["attrs"]["algorithm"] = settings.index_algorithm.lower()
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=30)
    try:
        server_info = cast(dict[str, Any], client.info("server"))
        version = tuple(int(part) for part in server_info["redis_version"].split(".")[:2])
        if version < (8, 4):
            raise RuntimeError("Native hybrid search requires Redis 8.4 or newer.")
        index = SearchIndex.from_dict(schema, redis_client=client, validate_on_load=True)
        # Only camera passage keys are replaced. Source apparel indexes are separate.
        client.delete(settings.manifest_key)
        index.create(overwrite=True, drop=True)
        pipeline = client.pipeline(transaction=False)
        for product in catalog.products.values():
            pipeline.json().set(
                f"{settings.product_prefix}:us:{product.product_id}", "$", product.model_dump()
            )
        pipeline.execute()
        started = time.perf_counter()
        for offset in range(0, len(passages), 128):
            batch = passages[offset : offset + 128]
            vectors = encoder.embed_many([p.search_text for p in batch])
            index.load(
                [
                    {**p.model_dump(), "embedding": vector}
                    for p, vector in zip(batch, vectors, strict=True)
                ],
                id_field="passage_id",
            )
            print(
                f"Indexed {min(offset + 128, len(passages)):,}/{len(passages):,} passages",
                flush=True,
            )
        deadline = time.monotonic() + 30
        while True:
            info = index.info()
            if int(info.get("num_docs", 0)) == len(passages) and not int(info.get("indexing", 0)):
                break
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "Camera indexing did not finish; inspect FT.INFO and rerun make seed."
                )
            time.sleep(0.1)
        manifest = {
            **index_identity(settings, catalog),
            "product_count": len(catalog.products),
            "passage_count": len(passages),
            "seed_seconds": round(time.perf_counter() - started, 2),
        }
        client.set(settings.manifest_key, json.dumps(manifest))
        print(json.dumps(manifest, indent=2), flush=True)
        return manifest
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--if-needed", action="store_true", help="Reuse a matching complete index")
    load(get_settings(), if_needed=parser.parse_args().if_needed)
