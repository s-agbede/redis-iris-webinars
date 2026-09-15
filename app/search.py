"""Three RedisVL retrieval methods over the same source passages and filters."""

import json
import string
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from redis import Redis
from redis.commands.search.hybrid_result import HybridResult
from redis.exceptions import RedisError
from redisvl.exceptions import RedisSearchError
from redisvl.index import SearchIndex
from redisvl.query import HybridQuery, TextQuery, VectorQuery
from redisvl.query.filter import Tag
from redisvl.redis.utils import convert_bytes

from app.catalog import Catalog, make_passages
from app.embeddings import build_vectorizer
from app.evidence import explain_fusion, literal_query_matches
from app.models import (
    CatalogInfo,
    CompareRequest,
    Comparison,
    ExampleQuery,
    FacetValue,
    FusionEvidence,
    Label,
    ModeResult,
    PassageEvidence,
    ProductPhoto,
    RedisPassage,
    SearchHit,
    SearchMode,
)
from app.photos import load_photos
from app.queries import (
    NO_LEXICAL_TERMS,
    build_hybrid_query,
    build_text_query,
    build_vector_query,
)
from app.settings import ROOT, Settings, get_settings
from app.suggestions import prepare_suggestions

SCORE_KINDS = {
    SearchMode.TEXT: "BM25",
    SearchMode.VECTOR: "Cosine similarity",
    SearchMode.HYBRID: "RRF",
}
TEXT_SEPARATORS = str.maketrans({char: " " for char in string.punctuation if char != "_"})


def normalize_lexical_query(text: str) -> str:
    """Split ASCII punctuation before RedisVL escapes the plain-language query.

    Redis indexes unescaped ZV-E10 as two TEXT tokens. Passing it directly to
    RedisVL would instead escape the hyphen and search for one literal token.
    Keep underscores and non-ASCII characters intact; this is not a query parser.
    """
    return " ".join(text.translate(TEXT_SEPARATORS).split())


def describe_query(query: TextQuery | VectorQuery | HybridQuery, index_name: str) -> str:
    if isinstance(query, HybridQuery):
        args = query.query.get_args()
        if query.combination_method:
            args += query.combination_method.get_args()
        args += query.postprocessing_config.build_args()
        return (
            f"FT.HYBRID {index_name} "
            + " ".join(map(str, args))
            + " PARAMS 2 vector <384 float32 values>"
        )
    suffix = " PARAMS 2 vector <384 float32 values>" if isinstance(query, VectorQuery) else ""
    return f"FT.SEARCH {index_name} {query}{suffix}"


class Encoder(Protocol):
    def embed(self, text: str) -> list[float]: ...


def index_identity(settings: Settings, catalog: Catalog) -> dict[str, str | int]:
    return {
        "pipeline": "camera-passages-v1",
        "data_fingerprint": catalog.fingerprint,
        "source_revision": catalog.manifest.source_revision,
        "embedding_model": settings.embedding_model,
        "embedding_revision": settings.embedding_revision,
        "dims": settings.embedding_dims,
        "algorithm": settings.index_algorithm,
        "passage_tokens": settings.passage_tokens,
        "passage_overlap": settings.passage_overlap,
    }


@dataclass
class Searcher:
    index: SearchIndex
    vectorizer: Encoder
    catalog: Catalog
    settings: Settings
    passage_count: int = 0
    passages: dict[str, list[PassageEvidence]] = field(default_factory=dict)
    photos: dict[str, ProductPhoto] = field(default_factory=dict)

    def _hits(
        self,
        rows: list[RedisPassage],
        mode: SearchMode,
        labels: dict[str, Label],
        limit: int,
        fusion: dict[str, FusionEvidence],
        query_text: str,
        stopwords: set[str],
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for passage_rank, row in enumerate(rows, start=1):
            pid = row.product_id
            if pid in seen:
                continue
            product = self.catalog.products[pid]
            score = row.relevance_score(mode)
            indexed_text = row.search_text
            matches = (
                literal_query_matches(indexed_text, query_text, stopwords)
                if mode is SearchMode.TEXT
                else []
            )
            hits.append(
                SearchHit(
                    product_id=pid,
                    title=product.product_title,
                    brand=product.product_brand,
                    color=product.product_color,
                    score=score,
                    source_label=labels.get(pid),
                    photo=self.photos.get(pid),
                    indexed_text=indexed_text,
                    lexical_matches=matches,
                    title_matches=(
                        literal_query_matches(product.product_title, query_text, stopwords)
                        if mode is SearchMode.TEXT
                        else []
                    ),
                    passage_matches=(
                        literal_query_matches(row.text, query_text, stopwords)
                        if mode is SearchMode.TEXT
                        else []
                    ),
                    passage_rank=passage_rank,
                    fusion=fusion.get(row.passage_id),
                    passage=row.passage(),
                )
            )
            seen.add(pid)
            if len(hits) == limit:
                break
        return hits

    def _hybrid_rows(self, query: HybridQuery) -> list[dict[str, Any]]:
        """Keep native completeness metadata that RedisVL's query() discards."""
        client = self.index.client
        if client is None:
            raise ValueError("Redis client is unavailable.")
        response = cast(
            HybridResult,
            client.ft(self.settings.products_index).hybrid_search(
                query=query.query,
                combine_method=query.combination_method,
                post_processing=query.postprocessing_config,
                params_substitution=query.params,
            ),
        )
        if response.warnings:
            warnings = "; ".join(str(convert_bytes(warning)) for warning in response.warnings)
            raise ValueError(f"Redis returned an incomplete hybrid result: {warnings}")
        rows = cast(list[dict[str, Any]], convert_bytes(response.results))
        if response.total_results != len(rows) or any(not row for row in rows):
            raise ValueError("Redis did not return the complete hybrid candidate union.")
        return rows

    def _basic_result(self, request: CompareRequest) -> ModeResult:
        """Literal title baseline, sorted alphabetically rather than by relevance."""
        started = time.perf_counter()
        needle = request.query.casefold()
        products = sorted(
            (
                product
                for product in self.catalog.products.values()
                if needle in product.product_title.casefold()
                and (not request.brands or product.product_brand in request.brands)
            ),
            key=lambda product: (product.product_title.casefold(), product.product_id),
        )[: request.num_results]
        labels = self.catalog.labels(request.query)
        hits = [
            SearchHit(
                product_id=product.product_id,
                title=product.product_title,
                brand=product.product_brand,
                color=product.product_color,
                score=1.0,
                source_label=labels.get(product.product_id),
                photo=self.photos.get(product.product_id),
                indexed_text=product.product_title,
                passage=PassageEvidence(
                    passage_id=f"{product.product_id}:basic-title",
                    field="product_title",
                    text=product.product_title,
                    start=0,
                    end=len(product.product_title),
                ),
            )
            for product in products
        ]
        return ModeResult(
            mode=SearchMode.BASIC,
            query_ms=round((time.perf_counter() - started) * 1000, 2),
            score_kind="Literal title match (alphabetical)",
            redis_query="",
            hits=hits,
        )

    def compare(self, request: CompareRequest) -> Comparison:
        started = time.perf_counter()
        labels = self.catalog.labels(request.query)
        expression = Tag("brand") == request.brands if request.brands else None
        lexical_text = normalize_lexical_query(request.query)
        vector: list[float] | None = None
        embedding_error: str | None = None
        embed_started = time.perf_counter()
        try:
            vector = self.vectorizer.embed(request.query)
        except (ValueError, RuntimeError) as exc:
            embedding_error = str(exc)
        embedding_ms = (time.perf_counter() - embed_started) * 1000
        explanation_ms = 0.0
        results: list[ModeResult] = []
        lexical: TextQuery | None = None
        for mode in (SearchMode.TEXT, SearchMode.VECTOR, SearchMode.HYBRID):
            result = ModeResult(mode=mode, query_ms=0, score_kind=SCORE_KINDS[mode], redis_query="")
            if mode is not SearchMode.TEXT and vector is None:
                result.error = embedding_error or "Local embedding failed."
                results.append(result)
                continue
            try:
                query: TextQuery | VectorQuery | HybridQuery
                if mode is SearchMode.TEXT:
                    lexical = build_text_query(
                        lexical_text,
                        filters=expression,
                        candidate_limit=self.settings.candidate_limit,
                    )
                    query = lexical
                elif mode is SearchMode.VECTOR:
                    assert vector is not None
                    query = build_vector_query(
                        vector, filters=expression, candidate_limit=self.settings.candidate_limit
                    )
                else:
                    assert vector is not None
                    if lexical is None:
                        raise ValueError(NO_LEXICAL_TERMS)
                    query = build_hybrid_query(
                        lexical_text,
                        vector,
                        lexical=lexical,
                        filters=expression,
                        candidate_limit=self.settings.candidate_limit,
                    )
                result.redis_query = describe_query(query, self.settings.products_index)
                query_started = time.perf_counter()
                try:
                    rows = (
                        self._hybrid_rows(query)
                        if isinstance(query, HybridQuery)
                        else self.index.query(query)
                    )
                finally:
                    result.query_ms = round((time.perf_counter() - query_started) * 1000, 2)
                explanation_started = time.perf_counter()
                try:
                    fusion = (
                        explain_fusion(rows, self.settings.candidate_limit)
                        if mode is SearchMode.HYBRID
                        else {}
                    )
                    passages = [RedisPassage.model_validate(row) for row in rows]
                    result.hits = self._hits(
                        passages,
                        mode,
                        labels,
                        request.num_results,
                        fusion,
                        lexical_text,
                        lexical.stopwords if lexical else set(),
                    )
                finally:
                    explanation_ms += (time.perf_counter() - explanation_started) * 1000
            except (RedisError, RedisSearchError, ValueError) as exc:
                result.error = str(exc)
            results.append(result)
        if request.include_basic:
            results.insert(0, self._basic_result(request))
        return Comparison(
            query=request.query,
            brands=request.brands,
            embedding_ms=round(embedding_ms, 2),
            explanation_ms=round(explanation_ms, 2),
            total_ms=round((time.perf_counter() - started) * 1000, 2),
            embedding_model=self.settings.embedding_model,
            source_revision=self.catalog.manifest.source_revision,
            candidate_limit=self.settings.candidate_limit,
            results=results,
        )

    def info(self) -> CatalogInfo:
        brands = Counter(p.product_brand for p in self.catalog.products.values() if p.product_brand)
        examples = [
            ExampleQuery.model_validate(value)
            for value in json.loads((self.settings.data_dir / "examples.json").read_text())
        ]
        return CatalogInfo(
            product_count=len(self.catalog.products),
            passage_count=self.passage_count,
            source_revision=self.catalog.manifest.source_revision,
            embedding_model=self.settings.embedding_model,
            embedding_revision=self.settings.embedding_revision,
            vector_dimensions=self.settings.embedding_dims,
            index_algorithm=self.settings.index_algorithm,
            brands=[
                FacetValue(value=brand, count=count) for brand, count in sorted(brands.items())
            ],
            examples=examples,
        )


def build_searcher(settings: Settings | None = None) -> Searcher:
    """Verify the seeded index, load local evidence, and prepare Redis autocomplete."""
    settings = settings or get_settings()
    catalog = Catalog.load(settings.data_dir)
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=15)
    try:
        raw = cast(bytes | None, client.get(settings.manifest_key))
        if not raw:
            raise RuntimeError("Camera index is missing. Start Redis and run make seed.")
        manifest = json.loads(raw)
        expected = index_identity(settings, catalog)
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise RuntimeError(
                "Camera index does not match this data/model configuration. Run make seed."
            )
        index = SearchIndex.from_existing(settings.products_index, redis_client=client)
        count = int(index.info().get("num_docs", 0))
        if count != manifest["passage_count"]:
            raise RuntimeError("Camera index is incomplete. Run make seed.")
        encoder = build_vectorizer(settings)
        passages = {
            pid: [
                PassageEvidence.model_validate(p.model_dump())
                for p in make_passages(
                    product, encoder.tokenizer, settings.passage_tokens, settings.passage_overlap
                )
            ]
            for pid, product in catalog.products.items()
        }
        photos = load_photos(ROOT / "seed/photos", set(catalog.products))
        prepare_suggestions(client, settings, catalog)
        return Searcher(index, encoder, catalog, settings, count, passages, photos)
    except Exception:
        client.close()
        raise
