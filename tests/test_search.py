from typing import Any, cast

from redis.commands.search.hybrid_result import HybridResult
from redis.exceptions import ResponseError
from redisvl.index import SearchIndex

from app.catalog import Catalog, DataManifest
from app.models import CameraProduct, CompareRequest, Judgement, SearchMode
from app.search import Searcher
from app.settings import Settings


class Encoder:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        return [1.0] + [0.0] * 383


class Index:
    def __init__(self, fail_hybrid: bool = False, hybrid_warning: str | None = None) -> None:
        self.queries: list[Any] = []
        self.fail_hybrid = fail_hybrid
        self.hybrid_warning = hybrid_warning

    @property
    def client(self) -> "Index":
        return self

    def ft(self, index_name: str) -> "Index":
        return self

    def hybrid_search(self, query: Any, **kwargs: Any) -> HybridResult:
        if self.fail_hybrid:
            raise ResponseError("hybrid unavailable")
        rows = self.query(query)
        return HybridResult(
            total_results=len(rows),
            results=rows,
            warnings=[self.hybrid_warning] if self.hybrid_warning else [],
            execution_time=0,
        )

    def disconnect(self) -> None:
        pass

    def query(self, query: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        if self.fail_hybrid and type(query).__name__ == "HybridQuery":
            raise ResponseError("hybrid unavailable")
        return [
            {
                "product_id": pid,
                "passage_id": f"us:{pid}:{i}",
                "field": "product_title",
                "text": f"{pid} lens",
                "start": "0",
                "end": "6",
                "score": 2.0,
                "vector_distance": 0.1,
                "combined_score": 0.03,
                "search_text": f"{pid} lens. camera lens",
            }
            for i, pid in enumerate(["a", "a", "b"])
        ]


def service(index: Index | None = None) -> tuple[Searcher, Encoder, Index]:
    products = {
        pid: CameraProduct(product_id=pid, product_title=f"{pid} lens", product_brand="Canon")
        for pid in ["a", "b"]
    }
    catalog = Catalog(
        products,
        [
            Judgement(
                query="canon lens",
                query_id=1,
                product_id="a",
                product_locale="us",
                esci_label="E",
                split="train",
            )
        ],
        DataManifest(
            source="fixture",
            source_revision="test",
            product_count=2,
            query_count=1,
            judgement_count=1,
            checksums={},
        ),
        "fingerprint",
    )
    encoder = Encoder()
    backend = index or Index()
    return (
        Searcher(cast(SearchIndex, backend), encoder, catalog, Settings(_env_file=None)),
        encoder,
        backend,
    )


def test_comparison_embeds_once_and_returns_unique_products_with_source_labels() -> None:
    searcher, encoder, _ = service()
    result = searcher.compare(CompareRequest(query="canon lens"))
    assert encoder.calls == 1
    assert [r.mode for r in result.results] == list(SearchMode)
    for mode in result.results:
        assert [hit.product_id for hit in mode.hits] == ["a", "b"]
        assert mode.hits[0].source_label == "E"
        assert mode.hits[1].source_label is None


def test_source_judgements_are_not_attached_to_a_different_query() -> None:
    searcher, _, _ = service()
    result = searcher.compare(CompareRequest(query="a lens for my camera"))
    assert all(hit.source_label is None for mode in result.results for hit in mode.hits)


def test_brand_constraint_is_present_in_all_three_queries() -> None:
    searcher, _, index = service()
    result = searcher.compare(CompareRequest(query="canon lens", brands=["Canon"]))
    assert len(index.queries) == 3
    assert all("@brand:{Canon}" in mode.redis_query for mode in result.results)
    assert "FT.HYBRID" in result.results[2].redis_query


def test_a_failed_mode_is_reported_without_erasing_successful_results() -> None:
    searcher, _, _ = service(Index(fail_hybrid=True))
    result = searcher.compare(CompareRequest(query="canon lens"))
    assert result.results[0].hits
    assert result.results[1].hits
    assert result.results[2].error
    assert not result.results[2].hits


def test_passage_rank_precedes_product_deduplication_and_indexed_context_is_visible() -> None:
    searcher, _, _ = service()
    result = searcher.compare(CompareRequest(query="canon lens"))
    for mode in result.results:
        assert [hit.passage_rank for hit in mode.hits] == [1, 3]
        assert mode.hits[0].indexed_text == "a lens. camera lens"
    assert result.explanation_ms >= 0


def test_json_lexical_evidence_annotates_literal_overlap_without_unsupported_highlight() -> None:
    searcher, _, index = service()
    result = searcher.compare(CompareRequest(query="canon lens"))
    args = index.queries[0].get_args()
    assert "HIGHLIGHT" not in args
    assert "search_text" in args
    hit = result.results[0].hits[0]
    assert [hit.indexed_text[span.start : span.end] for span in hit.lexical_matches] == [
        "lens",
        "lens",
    ]


def test_incomplete_hybrid_response_is_reported_without_misleading_explanations() -> None:
    searcher, _, _ = service(Index(hybrid_warning="Timeout limit was reached"))
    result = searcher.compare(CompareRequest(query="canon lens"))
    assert result.results[0].hits
    assert result.results[1].hits
    assert "Timeout limit was reached" in (result.results[2].error or "")
    assert result.results[2].hits == []
