"""Search lab HTTP endpoints; ranking and evidence live in app.search."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.exceptions import RedisError

from app.models import (
    CatalogInfo,
    CompareRequest,
    Comparison,
    PassageEvidence,
    ProductDetail,
    SearchMode,
)
from app.search import Searcher
from app.suggestions import get_suggestions, suggestion_key

router = APIRouter()


def get_searcher(request: Request) -> Searcher:
    searcher: Searcher | None = request.app.state.searcher
    if searcher is None:
        raise HTTPException(status_code=503, detail=request.app.state.startup_error)
    return searcher


SearcherDep = Annotated[Searcher, Depends(get_searcher)]


@router.get("/api/health")
def health(searcher: SearcherDep) -> dict[str, str | int]:
    try:
        searcher.index.client.ping()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Redis is unavailable.") from exc
    return {
        "status": "ready",
        "products": len(searcher.store.all()) if searcher.store else len(searcher.catalog.products),
        "passages": int(searcher.index.info(name=searcher.store.targets()[0]["name"])["num_docs"])
        if searcher.store
        else searcher.passage_count,
    }


@router.get("/api/catalog", response_model=CatalogInfo)
def catalog(searcher: SearcherDep) -> CatalogInfo:
    return searcher.info()


@router.get("/api/suggestions", response_model=list[str])
def suggestions(
    searcher: SearcherDep, prefix: Annotated[str, Query(max_length=200)] = ""
) -> list[str]:
    try:
        original = get_suggestions(
            searcher.index.client,
            suggestion_key(searcher.settings, searcher.catalog),
            prefix,
        )
        if searcher.store:
            demo = searcher.store.get_many(searcher.store.demo_ids())
            matches = (
                [
                    p.product_title
                    for p in demo.values()
                    if p.product_title.casefold().startswith(prefix.strip().casefold())
                    # A saved catalogue record is not searchable until sync publishes passages.
                    and searcher.store.passage_count(p.product_id) > 0
                ]
                if len(prefix.strip()) >= 2
                else []
            )
            return list(dict.fromkeys(matches + original))[:6]
        return original
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Autocomplete is unavailable.") from exc


@router.post("/api/compare", response_model=Comparison)
def compare(body: CompareRequest, searcher: SearcherDep) -> Comparison:
    return searcher.compare(body)


@router.post("/api/search", response_model=Comparison)
def search(body: CompareRequest, searcher: SearcherDep) -> Comparison:
    result = searcher.compare(
        body.model_copy(update={"include_basic": False}), modes=(SearchMode.HYBRID,)
    )
    if result.results[0].error:
        raise HTTPException(503, detail=result.results[0].error)
    return result


@router.get("/api/products/{product_id}", response_model=ProductDetail)
def product(product_id: str, searcher: SearcherDep) -> ProductDetail:
    item = (
        searcher.store.get(product_id)
        if searcher.store
        else searcher.catalog.products.get(product_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found in this catalogue.")
    is_demo = item.product_id.startswith("demo-")
    return ProductDetail(
        **item.model_dump(),
        source_origin="demo" if is_demo else "esci",
        source_revision=None if is_demo else searcher.catalog.manifest.source_revision,
        passages=[
            PassageEvidence.model_validate(raw)
            for raw in (
                searcher.store.client.json().get(key)
                for key in searcher.store.passage_keys(product_id)
            )
            if raw is not None
        ]
        if searcher.store
        else searcher.passages.get(product_id, []),
        photo=searcher.photos.get(product_id),
    )
