"""Local presenter API for the shopping assistant. Demo shoppers are not authentication."""

from collections.abc import Callable
from threading import Lock
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError

from app.search import Searcher
from app.shop.cache import CacheError, RedisAnswerCache
from app.shop.context_retriever import ContextRetrieverClient, ContextRetrieverError
from app.shop.errors import ShopError
from app.shop.jev import JevVerifier
from app.shop.llm import OpenAIShoppingModel
from app.shop.memory import MemoryError, MemoryRecord, RAMClient
from app.shop.models import ChatTurn, MemoryMode, Onboarding, ShopperID, ShopSession
from app.shop.prompts import TOOL_INSTRUCTIONS
from app.shop.reuse import AnswerReuse
from app.shop.service import ShopService
from app.shop.settings import ShopSettings

router = APIRouter(prefix="/api/shop", tags=["Sam's Camera Shop"])


class RedisSessionStore:
    def __init__(self, searcher: Searcher, prefix: str) -> None:
        self.client = searcher.index.client
        self.prefix = f"{searcher.settings.namespace}:shop:{prefix}:sessions:"

    def save(self, session: ShopSession) -> None:
        self.client.set(self.prefix + session.session_id, session.model_dump_json(), ex=604800)

    def load(self, session_id: str) -> ShopSession | None:
        raw = self.client.get(self.prefix + session_id)
        return ShopSession.model_validate_json(raw) if raw is not None else None


def build_shop(searcher: Searcher) -> ShopService:
    settings = ShopSettings()
    if missing := settings.missing():
        raise ShopError("Configure " + ", ".join(missing) + " in .env, then restart the app.")
    from app.shop.playbook import PlaybookGuidance

    playbook_fields = [
        settings.shop_playbook_url,
        settings.shop_playbook_id,
        settings.shop_playbook_api_key.get_secret_value(),
    ]
    if any(playbook_fields) and not all(playbook_fields):
        raise ShopError("Complete all three SHOP_PLAYBOOK settings, then restart the app.")
    context_retriever = ContextRetrieverClient(
        settings.ctx_mcp_url,
        {
            "alex": settings.ctx_alex_agent_key.get_secret_value(),
            "jordan": settings.ctx_jordan_agent_key.get_secret_value(),
        },
    )
    guidance = PlaybookGuidance(*playbook_fields) if all(playbook_fields) else None
    memory = RAMClient(
        settings.agent_memory_base_url,
        settings.agent_memory_store_id,
        settings.agent_memory_api_key.get_secret_value(),
        namespace_id=settings.agent_memory_namespace_id,
    )
    model = OpenAIShoppingModel(
        settings.openai_api_key.get_secret_value(), settings.shop_chat_model
    )
    reuse = None
    if settings.shop_cache_enabled and not settings.cache_missing():
        reuse = AnswerReuse(
            RedisAnswerCache(
                searcher.index.client,
                searcher.vectorizer,
                name=f"{searcher.settings.namespace}:shop:{settings.shop_owner_prefix}:answers-v1",
                distance=settings.shop_cache_distance,
            ),
            JevVerifier(
                settings.openrouter_api_key.get_secret_value(),
                settings.shop_jev_model,
                timeout_seconds=settings.shop_jev_timeout,
            ),
            distance=settings.shop_cache_distance,
            confidence=settings.shop_jev_confidence,
            ttl=settings.shop_cache_ttl,
        )
    return ShopService(
        searcher,
        memory,
        RedisSessionStore(searcher, settings.shop_owner_prefix),
        model,
        owner_prefix=settings.shop_owner_prefix,
        context_retriever=context_retriever,
        guidance=guidance,
        reuse=reuse,
        cache_configuration=(
            "answers-v1:"
            + settings.shop_chat_model
            + TOOL_INSTRUCTIONS
            + searcher.settings.embedding_model
            + searcher.settings.embedding_revision
        ),
    )


def service(request: Request) -> ShopService:
    if request.app.state.searcher is None:
        raise HTTPException(503, "The catalogue is unavailable. Check /api/health first.")
    with request.app.state.shop_init_lock:
        if request.app.state.shop is None:
            try:
                builder = cast(Callable[[Searcher], ShopService], request.app.state.shop_builder)
                request.app.state.shop = builder(request.app.state.searcher)
            except (ShopError, MemoryError, ContextRetrieverError) as exc:
                raise HTTPException(503, str(exc)) from None
    return cast(ShopService, request.app.state.shop)


ShopDep = Annotated[ShopService, Depends(service)]


class NewSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shopper_id: ShopperID


class ProfileRequest(Onboarding):
    shopper_id: ShopperID


class ChatRequest(NewSession):
    session_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    message: str = Field(min_length=1, max_length=4000)
    mode: MemoryMode = "both"
    use_cache: bool = True


class ClearCacheRequest(NewSession):
    include_shared: bool = False


class RemoveCacheRequest(NewSession):
    entry_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    shared: bool = False


class MemoryList(BaseModel):
    memories: list[MemoryRecord]
    complete: bool = True


@router.get("/status")
def status(request: Request) -> dict[str, object]:
    settings = ShopSettings()
    return {
        "configured": not settings.missing(),
        "missing": settings.missing(),
        "catalogue_ready": request.app.state.searcher is not None,
        "model": settings.shop_chat_model,
        "cache_enabled": settings.shop_cache_enabled,
        "cache_ready": settings.shop_cache_enabled and not settings.cache_missing(),
        "cache_missing": settings.cache_missing() if settings.shop_cache_enabled else [],
        "playbook_configured": bool(
            settings.shop_playbook_url
            and settings.shop_playbook_id
            and settings.shop_playbook_api_key.get_secret_value()
        ),
        "shoppers": [
            {"id": "alex", "name": "Alex", "description": "Travel filmmaker"},
            {"id": "jordan", "name": "Jordan", "description": "A separate demo shopper"},
        ],
    }


@router.post("/sessions", response_model=ShopSession)
def new_session(body: NewSession, shop: ShopDep) -> ShopSession:
    return shop.new_session(body.shopper_id)


@router.get("/sessions/{session_id}", response_model=ShopSession)
def session(session_id: str, shopper_id: ShopperID, shop: ShopDep) -> ShopSession:
    return shop.session(shopper_id, session_id)


@router.post("/onboarding", response_model=MemoryList)
def onboard(body: ProfileRequest, shop: ShopDep) -> MemoryList:
    return MemoryList(
        memories=shop.onboard(
            body.shopper_id,
            Onboarding(camera=body.camera, interests=body.interests, preferences=body.preferences),
        )
    )


@router.get("/memories", response_model=MemoryList)
def memories(shopper_id: ShopperID, shop: ShopDep) -> MemoryList:
    return MemoryList(memories=shop.memories(shopper_id))


@router.post("/chat", response_model=ChatTurn)
def chat(body: ChatRequest, shop: ShopDep, request: Request) -> ChatTurn:
    # One local presenter process: reject overlap instead of racing event order.
    lock: Lock = request.app.state.shop_turn_lock
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "The adviser is finishing another turn. Try again shortly.")
    try:
        return shop.turn(
            body.shopper_id, body.session_id, body.message, body.mode, use_cache=body.use_cache
        )
    finally:
        lock.release()


@router.post("/cache/clear")
def clear_cache(body: ClearCacheRequest, shop: ShopDep, request: Request) -> dict[str, int]:
    if shop.reuse is None:
        raise HTTPException(503, "Enable and configure semantic caching first.")
    lock: Lock = request.app.state.shop_turn_lock
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "The adviser is finishing another turn. Try again shortly.")
    try:
        deleted = shop.reuse.cache.clear(shop.owner(body.shopper_id))
        if body.include_shared:
            deleted += shop.reuse.cache.clear("shared")
        return {"deleted": deleted}
    except CacheError as exc:
        raise HTTPException(503, str(exc)) from None
    finally:
        lock.release()


@router.post("/cache/remove")
def remove_cache(body: RemoveCacheRequest, shop: ShopDep, request: Request) -> dict[str, bool]:
    if shop.reuse is None:
        raise HTTPException(503, "Enable and configure semantic caching first.")
    lock: Lock = request.app.state.shop_turn_lock
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "The adviser is finishing another turn. Try again shortly.")
    try:
        scope = "shared" if body.shared else shop.owner(body.shopper_id)
        return {"deleted": shop.reuse.cache.remove(body.entry_id, scope)}
    except CacheError as exc:
        raise HTTPException(503, str(exc)) from None
    finally:
        lock.release()


def close_shop(shop: ShopService | None) -> None:
    if shop is None:
        return
    for adapter in (shop.memory, shop.model, shop.guidance, shop.context_retriever):
        close = getattr(adapter, "close", None)
        if callable(close):
            close()
    if shop.reuse is not None:
        close = getattr(shop.reuse.verifier, "close", None)
        if callable(close):
            close()


async def shop_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, ContextRetrieverError):
        # Retrieval finishes before turn() starts writing session events.
        return JSONResponse(status_code=503, content={"detail": str(exc), "retry_safe": True})
    if isinstance(exc, RedisError):
        return JSONResponse(
            status_code=503, content={"detail": "Redis is unavailable. Check the local service."}
        )
    return JSONResponse(
        status_code=503 if isinstance(exc, (MemoryError, ContextRetrieverError)) else 400,
        content={"detail": str(exc)},
    )
