"""Assemble the camera shop, its search labs, and their shared resources."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from threading import Lock
from typing import cast

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from redis.exceptions import RedisError
from redisvl.exceptions import RedisVLError

from app.deployment import DeploymentManager
from app.deployment import router as deployment_router
from app.freshness_routes import router as lab_router
from app.indexing import PassageEncoder
from app.search import Searcher, build_searcher
from app.search_routes import router as search_router
from app.settings import ROOT
from app.shop.context_retriever import ContextRetrieverError
from app.shop.errors import ShopError
from app.shop.memory import MemoryError
from app.shop.routes import build_shop, close_shop, shop_error_handler
from app.shop.routes import router as shop_router
from app.shop.service import ShopService
from app.sync import SyncWorker
from app.traffic import router as traffic_router
from app.traffic import stop_traffic


def create_app(
    builder: Callable[[], Searcher] = build_searcher,
    *,
    shop_builder: Callable[[Searcher], ShopService] = build_shop,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        start_services(application, builder, shop_builder)
        try:
            yield
        finally:
            close_services(application)

    application = FastAPI(title="Camera Search Lab", version="0.2.0", lifespan=lifespan)
    application.include_router(lab_router)
    application.include_router(deployment_router)
    application.include_router(traffic_router)
    application.include_router(shop_router)
    application.include_router(search_router)
    for error in (ShopError, MemoryError, ContextRetrieverError, RedisError):
        application.add_exception_handler(error, shop_error_handler)
    mount_frontend(application)
    return application


def start_services(
    application: FastAPI,
    builder: Callable[[], Searcher],
    shop_builder: Callable[[Searcher], ShopService],
) -> None:
    """Start local search now; the adviser initializes lazily on its first request."""
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


def close_services(application: FastAPI) -> None:
    close_shop(application.state.shop)
    stop_traffic()
    if application.state.deployment is not None:
        application.state.deployment.close()
    if application.state.sync_worker is not None:
        application.state.sync_worker.stop()
    if application.state.searcher is not None:
        application.state.searcher.index.disconnect()


def mount_frontend(application: FastAPI) -> None:
    application.mount("/photos", StaticFiles(directory=ROOT / "seed/photos/assets"), name="photos")
    web_dist = ROOT / "web/dist"
    if web_dist.is_dir():
        application.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    else:

        @application.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse("/docs")


app = create_app()
