"""Local presenter API for the shopping assistant. Demo shoppers are not authentication."""

from collections.abc import Callable
from threading import Lock
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError

from app.search import Searcher
from app.shop.llm import OpenAIShoppingModel
from app.shop.memory import MemoryError, MemoryRecord, RAMClient
from app.shop.models import ChatTurn, MemoryMode, Onboarding, ShopperID, ShopSession
from app.shop.service import ShopError, ShopService
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
    return ShopService(
        searcher,
        memory,
        RedisSessionStore(searcher, settings.shop_owner_prefix),
        model,
        owner_prefix=settings.shop_owner_prefix,
        guidance=guidance,
    )


def service(request: Request) -> ShopService:
    if request.app.state.searcher is None:
        raise HTTPException(503, "The catalogue is unavailable. Check /api/health first.")
    with request.app.state.shop_init_lock:
        if request.app.state.shop is None:
            try:
                builder = cast(Callable[[Searcher], ShopService], request.app.state.shop_builder)
                request.app.state.shop = builder(request.app.state.searcher)
            except (ShopError, MemoryError) as exc:
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
        return shop.turn(body.shopper_id, body.session_id, body.message, body.mode)
    finally:
        lock.release()


def close_shop(shop: ShopService | None) -> None:
    if shop is None:
        return
    for adapter in (shop.memory, shop.model, shop.guidance):
        close = getattr(adapter, "close", None)
        if callable(close):
            close()


async def shop_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, RedisError):
        return JSONResponse(
            status_code=503, content={"detail": "Redis is unavailable. Check the local service."}
        )
    return JSONResponse(
        status_code=503 if isinstance(exc, MemoryError) else 400, content={"detail": str(exc)}
    )
