"""The three RedisVL query builders used by the live comparison.

Read these alongside schemas/passages.yaml. Every method searches the same
passages and applies the same filter. Embedding and execution live in search.py.
"""

from redisvl.query import HybridQuery, TextQuery, VectorQuery
from redisvl.query.filter import FilterExpression
from redisvl.query.hybrid import build_base_query

from app.constants import RRF_CONSTANT

PASSAGE_FIELDS = ["passage_id", "field", "text", "start", "end"]
RETURN_FIELDS = ["title", "brand", "color", "product_id", *PASSAGE_FIELDS, "search_text"]
NO_LEXICAL_TERMS = "No searchable terms remain after removing punctuation and stopwords."


def build_text_query(
    text: str, *, filters: FilterExpression | None, candidate_limit: int
) -> TextQuery:
    """Rank normalized query words against passage text using BM25."""
    query = TextQuery(
        text=text,
        text_field_name="search_text",
        text_scorer="BM25STD",
        filter_expression=filters,
        num_results=candidate_limit,
        return_fields=RETURN_FIELDS,
    )
    if not set(text.lower().split()) - query.stopwords:
        raise ValueError(NO_LEXICAL_TERMS)
    return query


def build_vector_query(
    vector: list[float], *, filters: FilterExpression | None, candidate_limit: int
) -> VectorQuery:
    """Find nearest passage embeddings; cosine distance is defined in the schema."""
    return VectorQuery(
        vector=vector,
        vector_field_name="embedding",
        filter_expression=filters,
        num_results=candidate_limit,
        return_fields=RETURN_FIELDS,
    )


def build_hybrid_query(
    text: str,
    vector: list[float],
    *,
    lexical: TextQuery,
    filters: FilterExpression | None,
    candidate_limit: int,
) -> HybridQuery:
    """Fuse lexical and vector passage ranks with native reciprocal rank fusion."""
    query = HybridQuery(
        text=text,
        text_field_name="search_text",
        vector=vector,
        vector_field_name="embedding",
        text_scorer="BM25STD",
        filter_expression=filters,
        combination_method="RRF",
        vector_search_method="KNN",
        knn_ef_runtime=0,
        rrf_window=candidate_limit,
        rrf_constant=RRF_CONSTANT,
        yield_combined_score_as="combined_score",
        num_results=candidate_limit,
        return_fields=RETURN_FIELDS,
    )
    align_hybrid_lexical_branch(query, lexical, filters=filters, candidate_limit=candidate_limit)
    # Fetch the full union for evidence without widening either branch's RRF window.
    query.postprocessing_config.limit(0, 2 * candidate_limit)
    return query


def align_hybrid_lexical_branch(
    query: HybridQuery,
    lexical: TextQuery,
    *,
    filters: FilterExpression | None,
    candidate_limit: int,
) -> None:
    """Keep hybrid's lexical matching identical to the standalone full-text query.

    RedisVL 0.26 makes hybrid text optional (~). Reuse the mandatory expression
    so passages with no lexical match cannot receive a lexical RRF contribution.
    Score aliases support the evidence inspector; Redis still computes the ranks.
    """
    query.query = build_base_query(
        text_query=lexical.query_string(),
        vector_param_name="vector",
        vector_field_name="embedding",
        text_scorer="BM25STD",
        vector_search_method="KNN",
        num_results=candidate_limit,
        knn_ef_runtime=0,
        filter_expression=filters,
        yield_text_score_as="text_score",
        yield_vsim_score_as="vsim_score",
    )
