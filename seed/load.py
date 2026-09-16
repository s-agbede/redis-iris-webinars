"""Load the bundled camera source data using the pinned local model."""

import argparse
import json
import time
from typing import Any, cast

import yaml
from redis import Redis
from redis.exceptions import ResponseError
from redisvl.index import SearchIndex

from app.catalog import Catalog
from app.embeddings import build_vectorizer
from app.indexing import prepare_product_passages
from app.search import index_identity, serving_target
from app.settings import ROOT, Settings, get_settings


def current_manifest(client: Any, settings: Settings, catalog: Catalog) -> dict[str, Any] | None:
    """An interrupted, outdated or missing index must be rebuilt before serving."""
    with client.lock(f"{settings.namespace}:sync-lock", timeout=60, blocking_timeout=30):
        raw = client.get(settings.manifest_key)
        if not raw:
            return None
        manifest: dict[str, Any] = json.loads(raw)
        if any(manifest.get(k) != v for k, v in index_identity(settings, catalog).items()):
            return None
        target = serving_target(client, settings)
        try:
            raw_info = client.execute_command("FT.INFO", target["name"])
        except ResponseError as exc:
            if "unknown index" in str(exc).lower() or "no such index" in str(exc).lower():
                return None
            raise
        info = dict(zip(raw_info[::2], raw_info[1::2], strict=True))
        expected = client.get(target["count_key"])
        count = int(expected) if expected is not None else manifest.get("passage_count")
        if int(info[b"num_docs"]) != count or int(info[b"indexing"]):
            return None
        return manifest


def configure_schema(schema: dict[str, Any], settings: Settings) -> None:
    """Apply instance settings without depending on the order of YAML fields."""
    schema["index"].update(name=settings.products_index, prefix=settings.passage_prefix)
    for field in schema["fields"]:
        if field["name"] == "embedding" and field["type"] == "vector":
            field["attrs"]["algorithm"] = settings.index_algorithm.lower()
            return
    raise ValueError("Passage schema must define an embedding vector field.")


def load(settings: Settings, *, if_needed: bool = False) -> dict[str, Any]:
    catalog = Catalog.load(settings.data_dir)
    with Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=15) as client:
        if if_needed:
            existing = current_manifest(client, settings, catalog)
            if existing is not None:
                print("Reusing the current camera passage index.", flush=True)
                return existing
        if client.exists(f"{settings.namespace}:deploy", f"{settings.namespace}:changes"):
            raise RuntimeError(
                "Bootstrap will not overwrite an existing live catalogue. "
                "Use Manage shop > Safe deployment to rebuild its index, or set a fresh "
                "NAMESPACE to bootstrap a separate catalogue. If startup validation failed, "
                "restore the managed catalogue/index before starting the app."
            )
    encoder = build_vectorizer(settings)
    schema = yaml.safe_load((ROOT / "schemas/passages.yaml").read_text())
    configure_schema(schema, settings)
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=30)
    try:
        server_info = cast(dict[str, Any], client.info("server"))
        version = tuple(int(part) for part in server_info["redis_version"].split(".")[:2])
        if version < (8, 4):
            raise RuntimeError("Native hybrid search requires Redis 8.4 or newer.")
        index = SearchIndex.from_dict(schema, redis_client=client, validate_on_load=True)
        # Rebuild this namespace's passage index; other indexes are untouched.
        client.delete(settings.manifest_key)
        index.create(overwrite=True, drop=True)
        pipeline = client.pipeline(transaction=False)
        for product in catalog.products.values():
            pipeline.json().set(
                f"{settings.product_prefix}:us:{product.product_id}", "$", product.model_dump()
            )
        pipeline.execute()
        started = time.perf_counter()
        passage_count = 0
        for product in catalog.products.values():
            records = prepare_product_passages(product, encoder, settings)
            if records:
                index.load([record.model_dump() for record in records], id_field="passage_id")
            passage_count += len(records)
        print(f"Indexed {passage_count:,} passages", flush=True)
        deadline = time.monotonic() + 30
        while True:
            info = index.info()
            if int(info.get("num_docs", 0)) == passage_count and not int(info.get("indexing", 0)):
                break
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "Camera indexing did not finish; inspect FT.INFO and rerun make seed."
                )
            time.sleep(0.1)
        manifest = {
            **index_identity(settings, catalog),
            "product_count": len(catalog.products),
            "passage_count": passage_count,
            "seed_seconds": round(time.perf_counter() - started, 2),
        }
        with client.pipeline(transaction=True) as pipeline:
            pipeline.set(f"{settings.namespace}:expected-passages", passage_count)
            pipeline.set(settings.manifest_key, json.dumps(manifest))
            pipeline.execute()
        print(json.dumps(manifest, indent=2), flush=True)
        return manifest
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--if-needed", action="store_true", help="Reuse a matching complete index")
    load(get_settings(), if_needed=parser.parse_args().if_needed)
