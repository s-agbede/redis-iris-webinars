"""The three retrieval strategies episode 1 walks through.

Same index, same data, same code path — one enum decides the query shape. The
progression is deliberate and each step fixes exactly one failure:

  VECTOR    similarity only. Finds plausible jackets at any price, in or out of
            stock, because constraints are not what an embedding encodes.
  FILTERED  adds numeric and tag filters. Constraints now respected, but rare
            exact tokens ("10,000mm", a brand name) still get blurred away.
  HYBRID    fuses BM25 full-text scoring with similarity, so exact terms and
            meaning both count.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from typing import Any

from redisvl.index import SearchIndex
from redisvl.query import HybridQuery, VectorQuery
from redisvl.query.filter import FilterExpression, Num, Tag
from redisvl.utils.vectorize import OpenAITextVectorizer

from app.models import SearchFilters, SearchHit, SearchMode, SearchResult, Timings
from app.settings import Settings

# HybridQuery is flagged experimental in redisvl 0.26; the warnings are noisy on
# a shared screen. Suppressed here rather than globally so it stays greppable.
warnings.filterwarnings("ignore", message=".*experimental.*")

RETURN_FIELDS = [
    "product_id",
    "name",
    "brand",
    "category",
    "price",
    "in_stock",
    "colours",
    "description",
]

TEXT_SCORE, VEC_SCORE, COMBINED_SCORE = "text_score", "vec_score", "combined_score"


def build_filter(filters: SearchFilters) -> FilterExpression | None:
    """Translate UI facets into RedisVL filter expressions.

    This function is the point of the episode: every control in the sidebar is
    one line here, and none of it goes anywhere near the embedding.
    """
    clauses: list[FilterExpression] = []

    if filters.min_price is not None:
        clauses.append(Num("price") >= filters.min_price)
    if filters.max_price is not None:
        clauses.append(Num("price") < filters.max_price)
    if filters.in_stock_only:
        clauses.append(Tag("in_stock") == "true")
    if filters.categories:
        clauses.append(Tag("category") == filters.categories)
    if filters.colours:
        clauses.append(Tag("colours") == filters.colours)
    if filters.sizes:
        clauses.append(Tag("sizes") == filters.sizes)

    if not clauses:
        return None

    combined = clauses[0]
    for clause in clauses[1:]:
        combined = combined & clause
    return combined


def _as_hit(raw: dict[str, Any], score: float) -> SearchHit:
    colours = raw.get("colours") or ""
    return SearchHit(
        product_id=raw["product_id"],
        name=raw["name"],
        brand=raw["brand"],
        category=raw.get("category", ""),
        price=float(raw["price"]),
        in_stock=raw.get("in_stock") == "true",
        colours=[c for c in colours.split(",") if c] if isinstance(colours, str) else colours,
        score=score,
    )


def _vector_score(raw: dict[str, Any]) -> float:
    """Cosine distance to similarity, so bigger is better in every mode."""
    return round(1.0 - float(raw.get("vector_distance", 1.0)), 4)


@dataclass(frozen=True, slots=True)
class Searcher:
    """Retrieval over the product index. Dependencies injected, no globals."""

    index: SearchIndex
    vectorizer: OpenAITextVectorizer
    settings: Settings

    def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.HYBRID,
        filters: SearchFilters | None = None,
        num_results: int = 12,
    ) -> SearchResult:
        filters = filters or SearchFilters()
        settings = self.settings
        timings = Timings()

        started = time.perf_counter()
        vector = self.vectorizer.embed(query)
        timings.embed_ms = round((time.perf_counter() - started) * 1000, 2)

        # VECTOR mode ignores the facets on purpose. That is not a bug — it is
        # the failure the next two modes exist to fix.
        expression = None if mode is SearchMode.VECTOR else build_filter(filters)

        redis_query: VectorQuery | HybridQuery
        if mode is SearchMode.HYBRID:
            redis_query = HybridQuery(
                text=query,
                text_field_name="search_text",
                vector=vector,
                vector_field_name="embedding",
                filter_expression=expression,
                yield_text_score_as=TEXT_SCORE,
                yield_vsim_score_as=VEC_SCORE,
                yield_combined_score_as=COMBINED_SCORE,
                # RRF, not LINEAR. BM25 scores are unbounded (0-12+ on this
                # corpus) while cosine similarity is capped at 1.0, so a linear
                # combination of raw scores lets text swamp the vector entirely
                # and returns confident nonsense. RRF fuses ranks, not scores,
                # so it is immune to the scale mismatch.
                combination_method=settings.fusion_method,
                linear_alpha=settings.linear_alpha,
                num_results=num_results,
                return_fields=RETURN_FIELDS,
            )
        else:
            redis_query = VectorQuery(
                vector=vector,
                vector_field_name="embedding",
                filter_expression=expression,
                num_results=num_results,
                return_fields=RETURN_FIELDS,
            )

        started = time.perf_counter()
        raw_results = self.index.query(redis_query)
        timings.redis_ms = round((time.perf_counter() - started) * 1000, 2)

        hits = [
            _as_hit(
                raw,
                float(raw[COMBINED_SCORE]) if COMBINED_SCORE in raw else _vector_score(raw),
            )
            for raw in raw_results
        ]

        return SearchResult(
            mode=mode,
            query=query,
            hits=hits,
            total=len(hits),
            timings=timings,
            redis_query=str(redis_query),
        )
