"""HTTP surface for the shopping agent.

Episode 1 needs two things from this file: a search endpoint the UI calls, and
enough read access to the catalogue to inspect *why* a search ranked the way it
did. The second part is not decoration — the single most useful field when
debugging a ranking is `search_text`, because that is what BM25 actually sees,
and it is invisible from the product card.

Interactive docs at /docs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from redisvl.query import FilterQuery

from app.models import SearchFilters, SearchMode, SearchResult
from app.search import RETURN_FIELDS, Searcher, build_filter, build_searcher
from app.settings import Settings, get_settings

HEROES = Path("seed/heroes.yaml")
WEB_DIST = Path("web/dist")

BROWSE_FIELDS = [*RETURN_FIELDS, "is_hero", "sizes", "material", "fit", "waterproof_mm"]
DETAIL_FIELDS = [*BROWSE_FIELDS, "search_text", "department"]


class SearchRequest(BaseModel):
    """A search as the UI issues it. Mode and filters are independent axes."""

    query: str = Field(min_length=1)
    mode: SearchMode = SearchMode.HYBRID
    filters: SearchFilters = Field(default_factory=SearchFilters)
    num_results: int = Field(12, ge=1, le=100)


class ProductSummary(BaseModel):
    """A catalogue row, as returned when browsing rather than searching."""

    product_id: str
    name: str
    brand: str
    category: str
    price: float
    in_stock: bool
    is_hero: bool
    colours: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)


class ProductDetail(ProductSummary):
    """One product, including the fields the search actually scores against."""

    description: str = ""
    material: str = ""
    fit: str = ""
    waterproof_mm: int = 0
    search_text: str = Field(
        "",
        description=(
            "The single field BM25 scores against. Read this when a ranking "
            "surprises you — it is assembled in seed/load.py and it is the only "
            "text full-text search can see."
        ),
    )


class HeroProduct(BaseModel):
    """A hand-written demo product, with the note explaining why it exists.

    `demo_role` lives only in seed/heroes.yaml — it is stripped before loading,
    so this endpoint reads the file rather than the index.
    """

    product_id: str
    name: str
    brand: str
    category: str
    price_eur: float
    in_stock: bool
    waterproof_mm: int = 0
    demo_role: str = ""


class FacetValue(BaseModel):
    value: str
    count: int


class Facets(BaseModel):
    """Every value the sidebar could offer, straight from the live index."""

    categories: list[FacetValue]
    colours: list[FacetValue]
    sizes: list[FacetValue]
    price_min: float
    price_max: float


class Health(BaseModel):
    status: str
    products_index: str
    products: int
    heroes: int


def _as_list(value: Any) -> list[str]:
    """Redis returns multi-value tags as either a list or a comma string."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [part for part in value.split(",") if part]
    return []


def _summary_fields(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": raw["product_id"],
        "name": raw["name"],
        "brand": raw["brand"],
        "category": raw.get("category", ""),
        "price": float(raw["price"]),
        "in_stock": raw.get("in_stock") == "true",
        "is_hero": raw.get("is_hero") == "true",
        "colours": _as_list(raw.get("colours")),
        "sizes": _as_list(raw.get("sizes")),
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the searcher once. A per-request index connection would show up as
    latency in the receipt and misattribute it to Redis."""
    app.state.searcher = build_searcher()
    yield


app = FastAPI(
    title="Northwind Outfitters",
    description=__doc__,
    version="0.1.0",
    lifespan=lifespan,
)


def get_searcher(request: Request) -> Searcher:
    searcher: Searcher = request.app.state.searcher
    return searcher


SearcherDep = Annotated[Searcher, Depends(get_searcher)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _aggregate_tag(searcher: Searcher, field: str) -> list[FacetValue]:
    """Distinct values for a tag field, with counts, via FT.AGGREGATE.

    Read from the index rather than from the seed files so the sidebar can never
    offer a facet the index cannot satisfy.
    """
    raw = searcher.index.client.execute_command(
        "FT.AGGREGATE",
        searcher.index.name,
        "*",
        "GROUPBY",
        "1",
        f"@{field}",
        "REDUCE",
        "COUNT",
        "0",
        "AS",
        "n",
        "SORTBY",
        "2",
        "@n",
        "DESC",
        "LIMIT",
        "0",
        "1000",
    )
    values: list[FacetValue] = []
    for row in raw[1:]:
        pairs = {
            row[i].decode() if isinstance(row[i], bytes) else row[i]: (
                row[i + 1].decode() if isinstance(row[i + 1], bytes) else row[i + 1]
            )
            for i in range(0, len(row), 2)
        }
        value = pairs.get(field, "")
        if value:
            values.append(FacetValue(value=value, count=int(pairs.get("n", 0))))
    return values


@lru_cache
def _heroes() -> list[HeroProduct]:
    entries = yaml.safe_load(HEROES.read_text())
    return [
        HeroProduct.model_validate(entry)
        for entry in entries
        if isinstance(entry, dict) and "product_id" in entry
    ]


@app.get("/api/health", response_model=Health)
def health(searcher: SearcherDep, settings: SettingsDep) -> Health:
    info = searcher.index.info()
    return Health(
        status="ok",
        products_index=settings.products_index,
        products=int(info.get("num_docs", 0)),
        heroes=len(_heroes()),
    )


@app.post("/api/search", response_model=SearchResult)
def search(request: SearchRequest, searcher: SearcherDep) -> SearchResult:
    """Run one search.

    `mode` and `filters` are orthogonal: any mode honours any filters. Compare
    the same query and filters across all three modes to see what each signal
    contributes.
    """
    return searcher.search(
        query=request.query,
        mode=request.mode,
        filters=request.filters,
        num_results=request.num_results,
    )


@app.get("/api/products", response_model=list[ProductSummary])
def browse_products(
    searcher: SearcherDep,
    hero: Annotated[
        bool | None, Query(description="True for the 12 hand-written demo products")
    ] = None,
    category: Annotated[list[str] | None, Query()] = None,
    colour: Annotated[list[str] | None, Query()] = None,
    size: Annotated[list[str] | None, Query()] = None,
    in_stock: Annotated[bool | None, Query()] = None,
    min_price: Annotated[float | None, Query(ge=0)] = None,
    max_price: Annotated[float | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProductSummary]:
    """Browse the catalogue with no query at all — filters only.

    Useful when drafting eval cases: find the product you want to make the
    answer, and the near-misses that should lose to it.
    """
    expression = build_filter(
        SearchFilters(
            min_price=min_price,
            max_price=max_price,
            categories=category or [],
            colours=colour or [],
            sizes=size or [],
            in_stock_only=bool(in_stock),
        )
    )
    if hero is not None:
        from redisvl.query.filter import Tag

        hero_clause = Tag("is_hero") == ("true" if hero else "false")
        expression = hero_clause if expression is None else expression & hero_clause

    query = FilterQuery(
        filter_expression=expression,
        return_fields=BROWSE_FIELDS,
        num_results=limit,
    )
    query.paging(offset, limit)
    return [ProductSummary(**_summary_fields(raw)) for raw in searcher.index.query(query)]


@app.get("/api/products/{product_id}", response_model=ProductDetail)
def product_detail(product_id: str, searcher: SearcherDep) -> ProductDetail:
    """One product, including `search_text` — what BM25 sees."""
    raw = searcher.index.fetch(product_id)
    if not raw:
        raise HTTPException(status_code=404, detail=f"no product {product_id!r}")
    return ProductDetail(
        **_summary_fields(raw),
        description=raw.get("description", ""),
        material=raw.get("material", ""),
        fit=raw.get("fit", ""),
        waterproof_mm=int(raw.get("waterproof_mm", 0) or 0),
        search_text=raw.get("search_text", ""),
    )


@app.get("/api/heroes", response_model=list[HeroProduct])
def heroes() -> list[HeroProduct]:
    """The 12 hand-written demo products, each with the note saying why it exists.

    Start here when drafting eval cases: `demo_role` records the specific way
    each product is meant to succeed or fail, which is the label you are trying
    to encode.
    """
    return _heroes()


@app.get("/api/facets", response_model=Facets)
def facets(searcher: SearcherDep) -> Facets:
    """Every facet value the index can actually satisfy."""
    prices = [
        float(raw["price"])
        for raw in searcher.index.query(FilterQuery(return_fields=["price"], num_results=10_000))
    ]
    return Facets(
        categories=_aggregate_tag(searcher, "category"),
        colours=_aggregate_tag(searcher, "colours"),
        sizes=_aggregate_tag(searcher, "sizes"),
        price_min=min(prices, default=0.0),
        price_max=max(prices, default=0.0),
    )


if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
else:

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """No frontend built yet — send people somewhere useful instead."""
        return RedirectResponse("/docs")
