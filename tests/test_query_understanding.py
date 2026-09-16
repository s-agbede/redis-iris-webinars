import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.query_understanding import infer_brand
from tests.test_search import service


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Sony 4k camera for youtube and filming myself. Beginner friendly", ["Sony"]),
        ("sony ZV-E10", ["Sony"]),
        ("Show me a Nikon camera", ["Nikon"]),
        ("Canon RF 85mm", ["Canon"]),
        ("microphone compatible with Sony", []),
        ("microphone for Sony", []),
        ("Sony-compatible microphone", []),
        ("Sony or Canon camera", []),
        ("Sony and Nikon cameras", []),
        ("Sony vs Nikon", []),
        ("not Sony cameras", []),
        ("Sony alternatives", []),
        ("Sonyish camera", []),
        ("beginner friendly camera", []),
    ],
)
def test_conservative_brand_rules(query, expected):
    assert infer_brand(query, ["Sony", "Nikon", "Canon"]) == expected


def test_comparison_can_enable_and_disable_inference_without_changing_query() -> None:
    searcher, _, _ = service()
    with TestClient(create_app(lambda: searcher)) as client:
        for enabled in (True, False, True):
            response = client.post(
                "/api/compare", json={"query": "Canon lens", "interpret_brand": enabled}
            )
            assert response.status_code == 200
            comparison = response.json()
            assert comparison["query"] == "Canon lens"
            assert comparison["inferred_brands"] == (["Canon"] if enabled else [])
            assert comparison["brands"] == (["Canon"] if enabled else [])
            for mode in comparison["results"]:
                assert mode["error"] is None
                assert ("@brand:{Canon}" in mode["redis_query"]) is enabled


@pytest.mark.parametrize("enabled", [False, True])
def test_manual_brand_filter_is_preserved_regardless_of_inference_setting(enabled: bool) -> None:
    searcher, _, _ = service()
    with TestClient(create_app(lambda: searcher)) as client:
        response = client.post(
            "/api/compare",
            json={"query": "Sony camera", "brands": ["Canon"], "interpret_brand": enabled},
        )
    assert response.status_code == 200
    comparison = response.json()
    assert comparison["brands"] == ["Canon"]
    assert comparison["inferred_brands"] == []
    assert all("@brand:{Canon}" in mode["redis_query"] for mode in comparison["results"])
