"""Opt-in checks against the seeded local Redis and the real local model."""

import math
import os

import pytest
from fastapi.testclient import TestClient

from app.catalog import clean_text
from app.main import create_app
from app.search import build_searcher
from app.settings import Settings

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_REDIS_URL"), reason="Set TEST_REDIS_URL after make seed"
)


def test_live_comparison_filters_and_source_evidence() -> None:
    settings = Settings(_env_file=None, redis_url=os.environ["TEST_REDIS_URL"])
    with TestClient(create_app(lambda: build_searcher(settings))) as client:
        assert client.get("/api/health").status_code == 200
        info = client.get("/api/catalog").json()
        assert info["product_count"] == 2317
        assert info["vector_dimensions"] == 384
        response = client.post(
            "/api/compare", json={"query": "canon rf lenses", "brands": ["Canon"]}
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert [r["mode"] for r in results] == ["text", "vector", "hybrid"]
        for result in results:
            assert result["error"] is None, result["error"]
            assert len(result["hits"]) == 5
            assert len({hit["product_id"] for hit in result["hits"]}) == 5
            for hit in result["hits"]:
                assert hit["brand"] == "Canon"
                detail = client.get(f"/api/products/{hit['product_id']}").json()
                passage = hit["passage"]
                text = clean_text(detail[passage["field"]])
                assert text[passage["start"] : passage["end"]] == passage["text"]
                assert "price" not in detail
                assert hit["passage_rank"] >= 1
                assert passage["text"] in hit["indexed_text"]
                if result["mode"] == "text":
                    assert hit["lexical_matches"]
                    assert all(
                        0 <= span["start"] < span["end"] <= len(hit["indexed_text"])
                        for span in hit["lexical_matches"]
                    )
                elif result["mode"] == "hybrid":
                    fusion = hit["fusion"]
                    assert fusion["status"] == "verified"
                    assert math.isclose(
                        fusion["text_contribution"] + fusion["vector_contribution"],
                        hit["score"],
                        rel_tol=0,
                        abs_tol=1e-12,
                    )
        empty = client.post(
            "/api/compare", json={"query": "lens", "brands": ["brand-that-does-not-exist"]}
        ).json()
        assert all(not r["hits"] and not r["error"] for r in empty["results"])
        absent = client.post("/api/compare", json={"query": "zzqxabsenttoken931"}).json()
        text, vector, hybrid = absent["results"]
        assert all(not result["error"] for result in absent["results"])
        assert text["hits"] == []
        # No lexical matches means no lexical rank contribution to hybrid.
        assert [h["product_id"] for h in hybrid["hits"]] == [
            h["product_id"] for h in vector["hits"]
        ]
        assert all(
            hit["fusion"]["status"] == "verified"
            and hit["fusion"]["text_rank"] is None
            and hit["fusion"]["text_contribution"] == 0
            for hit in hybrid["hits"]
        )


def test_live_model_number_punctuation_and_highlights() -> None:
    settings = Settings(_env_file=None, redis_url=os.environ["TEST_REDIS_URL"])
    with TestClient(create_app(lambda: build_searcher(settings))) as client:
        for query in ("Sony ZV-E10", "sony zv e10"):
            response = client.post("/api/compare", json={"query": query})
            assert response.status_code == 200
            comparison = response.json()
            assert comparison["query"] == query
            text, vector, hybrid = comparison["results"]
            assert all(mode["error"] is None for mode in (text, vector, hybrid))
            for mode in (text, hybrid):
                assert [hit["product_id"] for hit in mode["hits"][:2]] == [
                    "B09BBKVMCD",  # Sony Alpha ZV-E10 body
                    "B09BBMQKSR",  # Sony Alpha ZV-E10 lens kit
                ]
                assert "@search_text:(sony | zv | e10)" in mode["redis_query"]
            hit = text["hits"][0]
            assert {
                hit["title"][span["start"] : span["end"]].casefold()
                for span in hit["title_matches"]
            } == {"sony", "zv", "e10"}
