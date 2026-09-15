from typing import Any, cast

import pytest
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
        self.texts: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        self.texts.append(text)
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
    assert [r.mode for r in result.results] == [
        SearchMode.TEXT,
        SearchMode.VECTOR,
        SearchMode.HYBRID,
    ]
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


def test_result_highlights_use_offsets_in_each_displayed_field() -> None:
    searcher, _, _ = service()
    result = searcher.compare(CompareRequest(query="canon lens for"))
    text_hit = result.results[0].hits[0].model_dump()
    # The indexed text has two occurrences; each displayed field has only one.
    assert text_hit.get("title_matches") == [{"start": 2, "end": 6}]
    assert text_hit.get("passage_matches") == [{"start": 2, "end": 6}]
    for mode in result.results[1:]:
        for hit in mode.hits:
            assert hit.model_dump().get("title_matches") == []
            assert hit.model_dump().get("passage_matches") == []


def test_incomplete_hybrid_response_is_reported_without_misleading_explanations() -> None:
    searcher, _, _ = service(Index(hybrid_warning="Timeout limit was reached"))
    result = searcher.compare(CompareRequest(query="canon lens"))
    assert result.results[0].hits
    assert result.results[1].hits
    assert "Timeout limit was reached" in (result.results[2].error or "")
    assert result.results[2].hits == []


def test_basic_is_an_optional_literal_title_baseline_with_stable_order() -> None:
    searcher, _, _ = service()
    searcher.catalog.products["z"] = CameraProduct(
        product_id="z", product_title="A Lens adapter", product_brand="Sony"
    )
    result = searcher.compare(CompareRequest(query="LENS", include_basic=True))
    basic = next(item for item in result.results if item.mode.value == "basic")
    assert [hit.product_id for hit in basic.hits] == ["a", "z", "b"]
    assert basic.redis_query == ""
    assert basic.score_kind == "Literal title match (alphabetical)"
    assert basic.hits[0].passage.text == "a lens"
    assert basic.hits[0].fusion is None


def test_basic_respects_exact_brand_filter_and_does_not_tokenize_query() -> None:
    searcher, _, _ = service()
    result = searcher.compare(CompareRequest(query="lens", brands=["Sony"], include_basic=True))
    assert next(item for item in result.results if item.mode.value == "basic").hits == []
    result = searcher.compare(CompareRequest(query="lens a", include_basic=True))
    assert next(item for item in result.results if item.mode.value == "basic").hits == []


def test_basic_limit_and_source_evidence_match_the_returned_title() -> None:
    searcher, _, _ = service()
    result = searcher.compare(CompareRequest(query="lens", num_results=1, include_basic=True))
    basic = next(item for item in result.results if item.mode.value == "basic")
    assert len(basic.hits) == 1
    hit = basic.hits[0]
    assert hit.passage.field == "product_title"
    assert hit.passage.start == 0
    assert hit.passage.end == len(hit.title)


@pytest.mark.parametrize(
    ("query", "expression"),
    [
        ("Sony ZV-E10", "sony | zv | e10"),
        ('"Sony (ZV-E10)"', "sony | zv | e10"),
        ("Sony ZV/E10", "sony | zv | e10"),
        ("Sony ZV.E10", "sony | zv | e10"),
        ("Sony ZV_E10", "sony | zv_e10"),
        ("café 📷", "café | 📷"),
        ("lens|@brand:{Sony}*", "lens | brand | sony"),
    ],
)
def test_lexical_modes_treat_punctuation_as_separators(query: str, expression: str) -> None:
    searcher, encoder, _ = service()
    result = searcher.compare(CompareRequest(query=query, brands=["Canon"]))
    text, _, hybrid = result.results
    for mode in (text, hybrid):
        assert mode.error is None
        assert f"@search_text:({expression}) AND @brand:{{Canon}}" in mode.redis_query
    assert encoder.texts == [query]
    assert result.query == query
    assert all(hit.source_label is None for mode in result.results for hit in mode.hits)


def test_highlights_follow_normalized_terms_and_basic_keeps_the_literal_query() -> None:
    searcher, _, _ = service()
    result = searcher.compare(CompareRequest(query="a-lens", include_basic=True))
    basic, text, _, _ = result.results
    assert basic.hits == []
    hit = text.hits[0]
    for content, spans in (
        (hit.title, hit.title_matches),
        (hit.passage.text, hit.passage_matches),
        (hit.indexed_text, hit.lexical_matches),
    ):
        # "a" is a stopword; only the remaining search term should be highlighted.
        assert {content[span.start : span.end] for span in spans} == {"lens"}


@pytest.mark.parametrize("query", ["---", "(*)", "the-and"])
def test_no_searchable_terms_is_a_lexical_error_without_erasing_vector(query: str) -> None:
    searcher, _, index = service()
    result = searcher.compare(CompareRequest(query=query))
    text, vector, hybrid = result.results
    for mode in (text, hybrid):
        assert mode.error == "No searchable terms remain after removing punctuation and stopwords."
        assert mode.hits == []
    assert vector.hits and vector.error is None
    assert len(index.queries) == 1
