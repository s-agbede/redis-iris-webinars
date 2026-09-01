"""The three retrieval signals episode 1 walks through.

Same index, same data, same code path — one enum decides the query shape:

  TEXT    BM25 over `search_text`. Where most search already is, and it works
          right up until the shopper does not know the catalogue's vocabulary.
          Ask for "something to keep me dry walking the dog" and lexical
          matching has nothing to hold on to.
  VECTOR  Cosine similarity over embeddings. Intent survives paraphrase, so the
          shopper's own words are enough. Rare exact tokens ("10,000mm", a brand
          name) get blurred away instead.
  HYBRID  Both, fused by rank. Exact terms and meaning both count — which is
          what production systems actually do, and the first example of a
          pattern that continues into ranking and re-ranking.

FILTERS ARE NOT A MODE. They are a separate axis that applies to whichever
signal is selected: the same price and stock facets fix the same class of
mistake on top of TEXT as on top of VECTOR. Modelling them as a stage between
the two would teach the opposite of that.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from typing import Any

from redisvl.index import SearchIndex
from redisvl.query import HybridQuery, TextQuery, VectorQuery
from redisvl.query.filter import FilterExpression, Num, Tag
from redisvl.utils.vectorize import OpenAITextVectorizer

from app.embeddings import build_vectorizer
from app.models import SearchFilters, SearchHit, SearchMode, SearchResult, Timings
from app.settings import Settings, get_settings

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

TEXT_FIELD = "search_text"
TEXT_SCORE, VEC_SCORE, COMBINED_SCORE = "text_score", "vec_score", "combined_score"

# What TextQuery calls its BM25 column. Unlike the other two this is unbounded —
# see `_score`.
BM25_SCORE = "score"


def build_filter(filters: SearchFilters) -> FilterExpression | None:
    """Translate UI facets into RedisVL filter expressions.

    Every control in the sidebar is one line here, and none of it goes anywhere
    near the embedding or the BM25 scorer. That independence is the reason
    filters are an axis rather than a mode.
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


def _score(mode: SearchMode, raw: dict[str, Any]) -> float:
    """The mode's own score, normalised only so that bigger is always better.

    These are NOT comparable across modes and the UI should not imply they are:
    BM25 is unbounded (past 12 on this corpus), cosine similarity is capped at
    1.0, and RRF returns small reciprocal-rank sums near 0.03. Comparing them
    numerically is the exact mistake that made LINEAR fusion return nonsense.
    """
    if mode is SearchMode.TEXT:
        return round(float(raw.get(BM25_SCORE, 0.0)), 4)
    if mode is SearchMode.HYBRID:
        return round(float(raw[COMBINED_SCORE]), 4)
    # Cosine distance to similarity.
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

        # TEXT needs no embedding at all, so it skips the network hop entirely
        # and `embed_ms` stays zero. Worth pointing at on the call: the cheapest
        # mode is also the fastest, and that is a real part of the tradeoff.
        vector: list[float] | None = None
        if mode is not SearchMode.TEXT:
            started = time.perf_counter()
            vector = self.vectorizer.embed(query)
            timings.embed_ms = round((time.perf_counter() - started) * 1000, 2)

        # Applied in every mode. No special cases.
        expression = build_filter(filters)

        redis_query: TextQuery | VectorQuery | HybridQuery
        if mode is SearchMode.TEXT:
            redis_query = TextQuery(
                text=query,
                text_field_name=TEXT_FIELD,
                text_scorer=settings.text_scorer,
                filter_expression=expression,
                num_results=num_results,
                return_fields=RETURN_FIELDS,
            )
        elif mode is SearchMode.VECTOR:
            assert vector is not None  # guaranteed above; keeps mypy honest
            redis_query = VectorQuery(
                vector=vector,
                vector_field_name="embedding",
                filter_expression=expression,
                num_results=num_results,
                return_fields=RETURN_FIELDS,
            )
        else:
            assert vector is not None
            redis_query = HybridQuery(
                text=query,
                text_field_name=TEXT_FIELD,
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

        started = time.perf_counter()
        raw_results = self.index.query(redis_query)
        timings.redis_ms = round((time.perf_counter() - started) * 1000, 2)

        hits = [_as_hit(raw, _score(mode, raw)) for raw in raw_results]

        return SearchResult(
            mode=mode,
            query=query,
            hits=hits,
            total=len(hits),
            timings=timings,
            redis_query=str(redis_query),
        )


def build_searcher(settings: Settings | None = None) -> Searcher:
    """Assemble a Searcher against the live products index.

    Shared by the API and the eval on purpose: an eval that wires up retrieval
    its own way measures something the application does not actually do.

    The schema is read from the running index rather than from
    `schemas/products.yaml`, so a stale index cannot silently disagree with the
    file. If the index is missing this raises, which is the right outcome — the
    fix is `make seed`, not a fallback.
    """
    settings = settings or get_settings()
    return Searcher(
        index=SearchIndex.from_existing(settings.products_index, redis_url=settings.redis_url),
        vectorizer=build_vectorizer(settings),
        settings=settings,
    )
