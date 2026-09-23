"""HTTP and static frontend for the camera comparison lab."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from threading import Lock
from typing import Annotated, cast

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from redis.exceptions import RedisError
from redisvl.exceptions import RedisVLError

from app.deployment import DeploymentManager
from app.deployment import router as deployment_router
from app.freshness_routes import router as lab_router
from app.indexing import PassageEncoder
from app.models import (
    CatalogInfo,
    CompareRequest,
    Comparison,
    PassageEvidence,
    ProductDetail,
    SearchMode,
)
from app.search import Searcher, build_searcher
from app.settings import ROOT
from app.shop.memory import MemoryError
from app.shop.routes import build_shop, close_shop, shop_error_handler
from app.shop.routes import router as shop_router
from app.shop.service import ShopError, ShopService
from app.suggestions import get_suggestions, suggestion_key
from app.sync import SyncWorker
from app.traffic import router as traffic_router
from app.traffic import stop_traffic


def get_searcher(request: Request) -> Searcher:
    searcher: Searcher | None = request.app.state.searcher
    if searcher is None:
        raise HTTPException(status_code=503, detail=request.app.state.startup_error)
    return searcher


SearcherDep = Annotated[Searcher, Depends(get_searcher)]


def create_app(
    builder: Callable[[], Searcher] = build_searcher,
    *,
    shop_builder: Callable[[Searcher], ShopService] = build_shop,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.searcher = None
        application.state.shop = None
        application.state.shop_builder = shop_builder
        application.state.shop_init_lock = Lock()
        application.state.shop_turn_lock = Lock()
        application.state.sync_worker = None
        application.state.deployment = None
        application.state.startup_error = "Camera lab is starting."
        try:
            application.state.searcher = builder()
            searcher = application.state.searcher
            if searcher.store is not None:
                application.state.deployment = DeploymentManager(
                    searcher.store, cast(PassageEncoder, searcher.vectorizer), searcher.index
                )
                worker = SyncWorker(
                    searcher.store, cast(PassageEncoder, searcher.vectorizer), searcher.index
                )
                application.state.sync_worker = worker
                # Processing runs in app.worker; this instance serves Redis-backed controls.
        except (RedisError, RedisVLError, RuntimeError, ValueError, OSError) as exc:
            if application.state.searcher is not None:
                application.state.searcher.index.disconnect()
                application.state.searcher = None
            application.state.startup_error = (
                f"Camera lab is not ready: {exc} Restart the app after setup."
            )
        try:
            yield
        finally:
            close_shop(application.state.shop)
            stop_traffic()
            if application.state.deployment is not None:
                application.state.deployment.close()
            if application.state.sync_worker is not None:
                application.state.sync_worker.stop()
            if application.state.searcher is not None:
                application.state.searcher.index.disconnect()

    application = FastAPI(title="Camera Search Lab", version="0.2.0", lifespan=lifespan)

    application.include_router(lab_router)
    application.include_router(deployment_router)
    application.include_router(traffic_router)
    application.include_router(shop_router)
    application.add_exception_handler(ShopError, shop_error_handler)
    application.add_exception_handler(MemoryError, shop_error_handler)
    application.add_exception_handler(RedisError, shop_error_handler)

    @application.get("/api/health")
    def health(searcher: SearcherDep) -> dict[str, str | int]:
        try:
            searcher.index.client.ping()
        except RedisError as exc:
            raise HTTPException(status_code=503, detail="Redis is unavailable.") from exc
        return {
            "status": "ready",
            "products": len(searcher.store.all())
            if searcher.store
            else len(searcher.catalog.products),
            "passages": int(
                searcher.index.info(name=searcher.store.targets()[0]["name"])["num_docs"]
            )
            if searcher.store
            else searcher.passage_count,
        }

    @application.get("/api/catalog", response_model=CatalogInfo)
    def catalog(searcher: SearcherDep) -> CatalogInfo:
        return searcher.info()

    @application.get("/api/suggestions", response_model=list[str])
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

    @application.post("/api/compare", response_model=Comparison)
    def compare(body: CompareRequest, searcher: SearcherDep) -> Comparison:
        return searcher.compare(body)

    @application.post("/api/search", response_model=Comparison)
    def search(body: CompareRequest, searcher: SearcherDep) -> Comparison:
        result = searcher.compare(
            body.model_copy(update={"include_basic": False}), modes=(SearchMode.HYBRID,)
        )
        if result.results[0].error:
            raise HTTPException(503, detail=result.results[0].error)
        return result

    @application.get("/api/products/{product_id}", response_model=ProductDetail)
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
