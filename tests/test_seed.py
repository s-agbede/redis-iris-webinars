import json
from typing import Any

from app.catalog import Catalog
from app.search import index_identity
from app.settings import Settings
from seed.load import current_manifest


class RedisSnapshot:
    def __init__(self, manifest: dict[str, Any], count: int) -> None:
        self.manifest = manifest
        self.count = count

    def get(self, key: str) -> bytes:
        return json.dumps(self.manifest).encode()

    def execute_command(self, *args: str) -> list[object]:
        return [b"num_docs", self.count, b"indexing", 0]


def test_only_reuse_a_complete_index_of_the_same_data_and_model() -> None:
    settings = Settings(_env_file=None)
    catalog = Catalog.load(settings.data_dir)
    manifest = {**index_identity(settings, catalog), "passage_count": 123}
    assert current_manifest(RedisSnapshot(manifest, 123), settings, catalog) == manifest
    assert current_manifest(RedisSnapshot(manifest, 122), settings, catalog) is None
    assert (
        current_manifest(
            RedisSnapshot({**manifest, "embedding_revision": "old-model"}, 123), settings, catalog
        )
        is None
    )
