"""HTTP and static frontend for the camera comparison lab."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from redis.exceptions import RedisError
from redisvl.exceptions import RedisVLError

from app.models import CatalogInfo, CompareRequest, Comparison, ProductDetail
from app.search import Searcher, build_searcher
from app.settings import ROOT
from app.suggestions import get_suggestions, suggestion_key


def get_searcher(request: Request) -> Searcher:
    searcher: Searcher | None = request.app.state.searcher
    if searcher is None:
        raise HTTPException(status_code=503, detail=request.app.state.startup_error)
    return searcher


SearcherDep = Annotated[Searcher, Depends(get_searcher)]


def create_app(builder: Callable[[], Searcher] = build_searcher) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.searcher = None
        application.state.startup_error = "Camera lab is starting."
        try:
            application.state.searcher = builder()
        except (RedisError, RedisVLError, RuntimeError, ValueError, OSError) as exc:
            application.state.startup_error = (
                f"Camera lab is not ready: {exc} Restart the app after setup."
            )
        try:
            yield
        finally:
            if application.state.searcher is not None:
                application.state.searcher.index.disconnect()

    application = FastAPI(title="Camera Search Lab", version="0.2.0", lifespan=lifespan)

    @application.get("/api/health")
    def health(searcher: SearcherDep) -> dict[str, str | int]:
        try:
            searcher.index.client.ping()
        except RedisError as exc:
            raise HTTPException(status_code=503, detail="Redis is unavailable.") from exc
        return {
            "status": "ready",
            "products": len(searcher.catalog.products),
            "passages": searcher.passage_count,
        }

    @application.get("/api/catalog", response_model=CatalogInfo)
    def catalog(searcher: SearcherDep) -> CatalogInfo:
        return searcher.info()

    @application.get("/api/suggestions", response_model=list[str])
    def suggestions(
        searcher: SearcherDep, prefix: Annotated[str, Query(max_length=200)] = ""
    ) -> list[str]:
        try:
            return get_suggestions(
                searcher.index.client,
                suggestion_key(searcher.settings, searcher.catalog),
                prefix,
            )
        except RedisError as exc:
            raise HTTPException(status_code=503, detail="Autocomplete is unavailable.") from exc

    @application.post("/api/compare", response_model=Comparison)
    def compare(body: CompareRequest, searcher: SearcherDep) -> Comparison:
        return searcher.compare(body)

    @application.get("/api/products/{product_id}", response_model=ProductDetail)
    def product(product_id: str, searcher: SearcherDep) -> ProductDetail:
        item = searcher.catalog.products.get(product_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Product not found in this catalogue.")
        return ProductDetail(
            **item.model_dump(),
            source_revision=searcher.catalog.manifest.source_revision,
            passages=searcher.passages.get(product_id, []),
            photo=searcher.photos.get(product_id),
        )

    application.mount("/photos", StaticFiles(directory=ROOT / "seed/photos/assets"), name="photos")
    web_dist = ROOT / "web/dist"
    if web_dist.is_dir():
        application.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    else:

        @application.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse("/docs")

    return application


app = create_app()
