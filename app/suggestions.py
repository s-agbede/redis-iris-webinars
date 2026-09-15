"""Redis autocomplete is a separate prefix dictionary, not passage retrieval."""

from collections import Counter
from collections.abc import Iterable
from typing import Any

from app.catalog import Catalog
from app.models import CameraProduct
from app.settings import Settings


def suggestion_entries(products: Iterable[CameraProduct]) -> dict[str, int]:
    """Weight each title/brand by distinct product coverage, not passage count."""
    entries: Counter[str] = Counter()
    for product in products:
        values = {
            " ".join(value.split())
            for value in (product.product_title, product.product_brand or "")
        }
        entries.update(value for value in values if 2 <= len(value) <= 200)
    return dict(entries)


def suggestion_key(settings: Settings, catalog: Catalog) -> str:
    return f"{settings.namespace}:suggestions:v1:{catalog.fingerprint}"


def prepare_suggestions(client: Any, settings: Settings, catalog: Catalog) -> None:
    """Populate a source-versioned dictionary atomically; never change search data."""
    key = suggestion_key(settings, catalog)
    if client.exists(key):
        return
    with client.pipeline(transaction=True) as pipeline:
        for text, count in suggestion_entries(catalog.products.values()).items():
            pipeline.execute_command("FT.SUGADD", key, text, count)
        pipeline.execute()


def get_suggestions(client: Any, key: str, prefix: str) -> list[str]:
    prefix = prefix.strip()
    if len(prefix) < 2:
        return []
    rows = client.execute_command("FT.SUGGET", key, prefix, "MAX", 6) or []
    return [row.decode("utf-8") if isinstance(row, bytes) else str(row) for row in rows]
