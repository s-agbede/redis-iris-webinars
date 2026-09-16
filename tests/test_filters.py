"""Metadata constraints are independent of search wording and ranking method."""

import pytest
import yaml
from fastapi.testclient import TestClient

from app.catalog import make_passages
from app.main import create_app
from app.models import CameraProduct, CompareRequest, SearchMode
from app.search import index_identity
from app.settings import ROOT
from tests.test_catalog import product, tokenizer
from tests.test_search import Index, service


def test_color_filter_is_validated_and_normalized_at_the_api_boundary() -> None:
    searcher, _, _ = service()
    with TestClient(create_app(lambda: searcher)) as client:
        response = client.post(
            "/api/compare", json={"query": "lens", "colors": [" WHITE ", "white", "Ice  Blue"]}
        )
        assert response.status_code == 200
        assert response.json()["colors"] == ["white", "ice blue"]
        for colors in ([" "], ["x" * 301], ["white"] * 21):
            assert (
                client.post("/api/compare", json={"query": "lens", "colors": colors}).status_code
                == 422
            )


@pytest.mark.parametrize("brands", [[], ["Sony", "Canon"]])
def test_color_constraints_reach_all_redis_modes_and_both_hybrid_branches(
    brands: list[str],
) -> None:
    searcher, _, _ = service()
    comparison = searcher.compare(CompareRequest(query="lens", brands=brands, colors=["White"]))
    for mode in comparison.results:
        assert mode.error is None
        assert "@color:{white}" in mode.redis_query
        if brands:
            assert "@brand:{Sony|Canon}" in mode.redis_query
    hybrid = comparison.results[-1].redis_query
    lexical, vector = hybrid.split(" VSIM ", 1)
    assert "@color:{white}" in lexical
    assert "@color:{white}" in vector.split(" COMBINE ", 1)[0]


def test_basic_combines_brand_and_color_before_limiting_and_excludes_missing_color() -> None:
    searcher, _, _ = service()
    searcher.catalog.products = {
        pid: CameraProduct(
            product_id=pid, product_title=f"{pid} camera", product_brand=brand, product_color=color
        )
        for pid, brand, color in [
            ("a", "Sony", "Black"),
            ("b", "Canon", "White"),
            ("c", "Sony", None),
            ("d", "Sony", " WHITE "),
            ("e", "Sony", "Ice  Blue"),
        ]
    }
    comparison = searcher.compare(
        CompareRequest(
            query="camera",
            brands=["Sony"],
            colors=["white", "ice blue"],
            include_basic=True,
            num_results=1,
        )
    )
    basic = comparison.results[0]
    assert basic.mode is SearchMode.BASIC
    assert [hit.product_id for hit in basic.hits] == ["d"]
    assert basic.hits[0].color == " WHITE "
    unfiltered = searcher.compare(CompareRequest(query="camera", include_basic=True))
    assert len(unfiltered.results[0].hits) == 5


def test_color_facets_count_products_and_merge_only_case_and_spacing_variants() -> None:
    searcher, _, _ = service()
    searcher.catalog.products = {
        pid: product(product_id=pid, product_color=color)
        for pid, color in [("a", "White"), ("b", " WHITE "), ("c", None), ("d", "Off White")]
    }
    with TestClient(create_app(lambda: searcher)) as client:
        response = client.get("/api/catalog")
    assert response.status_code == 200
    assert response.json()["colors"] == [
        {"value": "off white", "count": 1},
        {"value": "white", "count": 2},
    ]


def test_every_passage_carries_the_normalized_color_without_changing_the_source() -> None:
    item = product(product_color=" WHITE ", product_description="A compact camera.")
    passages = make_passages(item, tokenizer())
    assert len(passages) == 2
    assert all(passage.color == "white" for passage in passages)
    assert item.product_color == " WHITE "
    searcher, _, _ = service()
    assert index_identity(searcher.settings, searcher.catalog)["pipeline"] != "camera-passages-v1"
    schema = yaml.safe_load((ROOT / "schemas/passages.yaml").read_text())
    color = next(field for field in schema["fields"] if field["name"] == "color")
    assert color["type"] == "tag"
    assert color["attrs"] == {"case_sensitive": True, "separator": "\u001f"}


@pytest.mark.parametrize(
    ("brand", "color"), [("Nikon", "White"), ("Canon", "Black"), ("Canon", None)]
)
def test_live_hydration_rechecks_filters_before_limiting_but_indexed_view_keeps_snapshot(
    brand: str, color: str | None
) -> None:
    class IndexedWhiteCanon(Index):
        def query(self, query):
            return [
                {**row, "title": "Canon white lens", "brand": "Canon", "color": "white"}
                for row in super().query(query)
            ]

    searcher, _, _ = service(IndexedWhiteCanon())

    class LiveProducts:
        def targets(self):
            return [{"name": "fixture"}]

        def get_many(self, ids):
            return {
                "a": product(product_id="a", product_brand=brand, product_color=color),
                "b": product(product_id="b", product_color=" WHITE "),
            }

    searcher.store = LiveProducts()
    request = CompareRequest(
        query="Canon lens", interpret_brand=True, colors=["white"], num_results=1
    )
    live = searcher.compare(request)
    assert live.inferred_brands == ["Canon"]
    for result in live.results:
        assert result.error is None
        assert [hit.product_id for hit in result.hits] == ["b"]
    indexed = searcher.compare(request.model_copy(update={"indexed_view": True}))
    for result in indexed.results:
        assert result.error is None
        assert [hit.product_id for hit in result.hits] == ["a"]
        assert result.hits[0].brand == "Canon"
        assert result.hits[0].color == "white"
