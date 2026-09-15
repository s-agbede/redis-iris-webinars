from fastapi.testclient import TestClient

from app.main import create_app
from app.models import ProductPhoto
from tests.test_search import service


def test_api_validates_queries_and_returns_three_comparable_rankings() -> None:
    searcher, _, _ = service()
    with TestClient(create_app(lambda: searcher)) as client:
        assert client.post("/api/compare", json={"query": "   "}).status_code == 422
        assert (
            client.post("/api/compare", json={"query": "lens", "num_results": 200}).status_code
            == 422
        )
        response = client.post("/api/compare", json={"query": "canon lens"})
        assert response.status_code == 200
        assert len(response.json()["results"]) == 3
        assert response.json()["results"][0]["hits"][0]["source_label"] == "E"


def test_missing_index_returns_readiness_error_instead_of_fake_results() -> None:
    def unavailable() -> object:
        raise RuntimeError("Camera index is missing. Run make seed.")

    with TestClient(create_app(unavailable)) as client:  # type: ignore[arg-type]
        assert client.get("/api/health").status_code == 503
        response = client.post("/api/compare", json={"query": "lens"})
        assert response.status_code == 503
        assert "make seed" in response.json()["detail"]


def test_product_detail_keeps_original_source_fields_and_returns_404_for_missing() -> None:
    searcher, _, _ = service()
    with TestClient(create_app(lambda: searcher)) as client:
        assert client.get("/api/products/absent").status_code == 404
        response = client.get("/api/products/a")
        assert response.status_code == 200
        assert response.json()["product_title"] == "a lens"
        assert response.json()["product_description"] is None


def test_unmapped_products_have_no_photo_and_local_images_are_served() -> None:
    searcher, _, _ = service()
    with TestClient(create_app(lambda: searcher)) as client:
        detail = client.get("/api/products/a").json()
        assert "photo" in detail and detail["photo"] is None
        response = client.get("/photos/nikon-d610.jpg")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content.startswith(b"\xff\xd8\xff")
        assert client.get("/photos/does-not-exist.jpg").status_code == 404


def test_photo_mapping_is_identical_in_rankings_and_product_detail() -> None:
    searcher, _, _ = service()
    photo = ProductPhoto(
        url="/photos/nikon-d610.jpg",
        alt="Nikon D610 body",
        caption="Model reference; listing condition may differ.",
        source_url="https://commons.wikimedia.org/wiki/File:Nikon_D610_Body.jpg",
        author="Johntorcasio",
        license="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
    )
    searcher.photos = {"a": photo}
    with TestClient(create_app(lambda: searcher)) as client:
        detail = client.get("/api/products/a").json()
        assert detail["photo"] == photo.model_dump()
        result = client.post("/api/compare", json={"query": "canon lens"}).json()
        for mode in result["results"]:
            assert [hit["product_id"] for hit in mode["hits"]] == ["a", "b"]
            assert mode["hits"][0]["photo"] == detail["photo"]
            assert mode["hits"][1]["photo"] is None


def test_autocomplete_validates_input_and_returns_redis_suggestions() -> None:
    from tests.test_search import Index

    class SuggestionIndex(Index):
        def execute_command(self, *args: object) -> list[bytes]:
            assert args == ("FT.SUGGET", "camera:suggestions:v1:fingerprint", "so", "MAX", 6)
            return [b"Sony", b"Sony Alpha"]

    searcher, _, _ = service(SuggestionIndex())
    with TestClient(create_app(lambda: searcher)) as client:
        assert client.get("/api/suggestions", params={"prefix": " so "}).json() == [
            "Sony",
            "Sony Alpha",
        ]
        assert client.get("/api/suggestions", params={"prefix": "s"}).json() == []
        assert client.get("/api/suggestions", params={"prefix": "x" * 201}).status_code == 422


def test_autocomplete_reports_redis_failure() -> None:
    from redis.exceptions import ConnectionError

    from tests.test_search import Index

    class FailedIndex(Index):
        def execute_command(self, *args: object) -> list[bytes]:
            raise ConnectionError("offline")

    searcher, _, _ = service(FailedIndex())
    with TestClient(create_app(lambda: searcher)) as client:
        assert client.get("/api/suggestions", params={"prefix": "so"}).status_code == 503
