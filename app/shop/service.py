"""Camera shopping flow: retrieve context, search, answer, and save events."""

import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Protocol
from urllib.parse import urlencode
from uuid import uuid4

from pydantic import JsonValue
from redis.exceptions import RedisError

from app.models import CameraProduct
from app.search import Searcher
from app.shop.errors import ShopError
from app.shop.memory import MemoryGateway, MemoryRecord, MemorySession
from app.shop.models import (
    CacheTrace,
    ChatTurn,
    Guidance,
    MemoryMode,
    ModelAnswer,
    Onboarding,
    ProductCard,
    ReuseResult,
    ShopperID,
    ShoppingTools,
    ShopSession,
    ToolDefinition,
    TurnContext,
    TurnInspector,
)
from app.shop.prompts import SHOP_INSTRUCTIONS
from app.shop.reuse import AnswerReuse, cache_version
from app.shop.tools import ShopRetrieval

logger = logging.getLogger(__name__)


@dataclass
class TurnTimings:
    """Observation only: timings never influence whether an answer is reused."""

    started: float = field(default_factory=perf_counter)
    memory_ms: float = 0
    search_ms: float = 0
    model_ms: float = 0

    def elapsed_ms(self) -> float:
        return round((perf_counter() - self.started) * 1000, 2)


class SessionStore(Protocol):
    def save(self, session: ShopSession) -> None: ...
    def load(self, session_id: str) -> ShopSession | None: ...


class ShoppingModel(Protocol):
    def answer(self, context: TurnContext, tools: ShoppingTools) -> ModelAnswer: ...


class GuidanceSource(Protocol):
    def discover(self, query: str) -> list[Guidance]: ...


class ContextRetriever(Protocol):
    def list_tools(self, shopper_id: ShopperID) -> list[ToolDefinition]: ...
    def call_tool(
        self, shopper_id: ShopperID, tool: ToolDefinition, arguments: dict[str, JsonValue]
    ) -> JsonValue: ...


class ShopService:
    def __init__(
        self,
        searcher: Searcher,
        memory: MemoryGateway,
        store: SessionStore,
        model: ShoppingModel,
        *,
        owner_prefix: str,
        context_retriever: ContextRetriever,
        guidance: GuidanceSource | None = None,
        reuse: AnswerReuse | None = None,
        cache_configuration: str = "camera-adviser-cache-v1",
    ) -> None:
        self.searcher, self.memory, self.store, self.model = searcher, memory, store, model
        self.owner_prefix, self.guidance = owner_prefix, guidance
        self.context_retriever = context_retriever
        self.reuse, self.cache_configuration = reuse, cache_configuration

    def turn(
        self,
        shopper_id: ShopperID,
        session_id: str,
        message: str,
        mode: MemoryMode,
        *,
        use_cache: bool = True,
    ) -> ChatTurn:
        """One turn: load context, try reuse, answer, save history, then consider caching."""
        timings = TurnTimings()
        if not message.strip() or len(message) > 4000:
            raise ShopError("Enter a message of 1–4,000 characters.")
        if mode not in ("none", "session", "both"):
            raise ShopError("Choose a valid memory mode.")
        session = self.session(shopper_id, session_id)
        context = self._load_context(session, message.strip(), mode, timings)
        version = cache_version(self.cache_configuration + SHOP_INSTRUCTIONS, context)

        reused = self._try_reuse(context, session.owner_id, version, use_cache=use_cache)
        answer = reused.answer
        tools = ShopRetrieval(
            self, shopper_id, context, cache_enabled=bool(self.reuse and use_cache)
        )
        if answer is None:
            model_started = perf_counter()
            answer = self.model.answer(context, tools)
            timings.search_ms = sum(call.elapsed_ms for call in answer.tool_calls)
            timings.model_ms = max(0, (perf_counter() - model_started) * 1000 - timings.search_ms)
        else:
            # A hit supplies cards checked against the current local catalogue.
            context.products = reused.products

        products = validated_answer_products(answer, context)
        turn = self._save_conversation(session, context, answer, products, reused.trace, timings)
        if self.reuse and tools.nomination is not None:
            # Nomination is not a write. Only an already-saved, validated reply is admitted.
            self.reuse.save(
                context=context,
                owner=session.owner_id,
                version=version,
                answer=answer,
                products=products,
                scope=tools.nomination,
                remote_used=tools.remote_used,
                trace=reused.trace,
            )
            turn.inspector.total_ms = timings.elapsed_ms()
            self._save_cache_evidence(session, reused.trace)
        return turn

    def _load_context(
        self, session: ShopSession, message: str, mode: MemoryMode, timings: TurnTimings
    ) -> TurnContext:
        context = TurnContext(message=message, mode=mode, shopper_id=session.shopper_id)
        started = perf_counter()
        if mode != "none":
            remembered = self.memory.session(session.session_id)
            # RAM is the source of history; the local session only supplies matching cards.
            context.session = MemorySession(
                events=remembered.events[-20:], summary=remembered.summary
            )
            context.previous_products = previous_product_cards(session, context.session)
        if mode == "both":
            context.memories = self.memory.search(session.owner_id, message)
        timings.memory_ms = (perf_counter() - started) * 1000
        context.guidance = self.guidance.discover(message) if self.guidance else []
        return context

    def _try_reuse(
        self, context: TurnContext, owner: str, version: str, *, use_cache: bool
    ) -> ReuseResult:
        if not use_cache:
            return ReuseResult(
                trace=CacheTrace(status="bypass", reason="Cache bypass selected for this request.")
            )
        if self.reuse is None:
            return ReuseResult()
        return self.reuse.find(context, owner, version, self.current_product_card)

    def current_product_card(self, product_id: str) -> ProductCard | None:
        product = self.product(product_id)
        return self.card(product) if product is not None else None

    def _save_conversation(
        self,
        session: ShopSession,
        context: TurnContext,
        answer: ModelAnswer,
        products: list[ProductCard],
        trace: CacheTrace,
        timings: TurnTimings,
    ) -> ChatTurn:
        # Hits and generated replies write the same events. RAM owns later extraction.
        event_ids = [
            self.memory.append_event(session.session_id, session.owner_id, "USER", context.message),
            self.memory.append_event(
                session.session_id, session.owner_id, "ASSISTANT", answer.text
            ),
        ]
        turn = ChatTurn(
            user=context.message,
            assistant=answer.text,
            products=products,
            inspector=TurnInspector(
                context=context,
                answer_request=answer.request,
                tool_calls=answer.tool_calls,
                memory_ms=round(timings.memory_ms, 2),
                search_ms=round(timings.search_ms, 2),
                model_ms=round(timings.model_ms, 2),
                total_ms=timings.elapsed_ms(),
                event_ids=event_ids,
                cache=trace,
            ),
        )
        session.turns.append(turn)
        self.store.save(session)
        return turn

    def _save_cache_evidence(self, session: ShopSession, trace: CacheTrace) -> None:
        try:
            self.store.save(session)
        except RedisError:
            # The reply is already saved. Failing this optional write must not invite
            # a retry that would append the same conversation events twice.
            trace.store_reason = (trace.store_reason or "") + (
                " Cache evidence could not be saved; the conversation was already saved."
            )
            logger.warning("Cache evidence persistence failed after a saved conversation.")

    def owner(self, shopper_id: ShopperID) -> str:
        if shopper_id not in ("alex", "jordan"):
            raise ShopError("Choose one of the two fictional demo shoppers.")
        return f"{self.owner_prefix}-{shopper_id}"

    def new_session(self, shopper_id: ShopperID) -> ShopSession:
        session = ShopSession(
            session_id=f"shop-{uuid4().hex}", shopper_id=shopper_id, owner_id=self.owner(shopper_id)
        )
        self.store.save(session)
        return session

    def session(self, shopper_id: ShopperID, session_id: str) -> ShopSession:
        session = self.store.load(session_id)
        if session is None:
            raise ShopError("Conversation not found. Start a new conversation.")
        if session.owner_id != self.owner(shopper_id):
            raise ShopError("This conversation does not belong to this shopper.")
        return session

    def memories(self, shopper_id: ShopperID) -> list[MemoryRecord]:
        return self.memory.inventory(self.owner(shopper_id))

    def onboard(self, shopper_id: ShopperID, profile: Onboarding) -> list[MemoryRecord]:
        facts = {
            key: text
            for key, text in {
                "camera": f"User currently owns a {profile.camera}." if profile.camera else "",
                "interests": f"User films {profile.interests}." if profile.interests else "",
                "preferences": f"User's gear preferences: {profile.preferences}."
                if profile.preferences
                else "",
            }.items()
            if text
        }
        if not facts:
            raise ShopError("Add at least one detail to remember.")
        return self.memory.create_facts(self.owner(shopper_id), facts)

    def card(self, product: CameraProduct) -> ProductCard:
        description = (
            product.product_description or product.product_bullet_point or product.product_title
        )
        return ProductCard(
            product_id=product.product_id,
            title=product.product_title,
            brand=product.product_brand,
            description=description[:2500],
            url="/?" + urlencode({"view": "product", "id": product.product_id}),
            photo=self.searcher.photos.get(product.product_id),
        )

    def product(self, product_id: str) -> CameraProduct | None:
        return (
            self.searcher.store.get(product_id)
            if self.searcher.store
            else self.searcher.catalog.products.get(product_id)
        )


def previous_product_cards(session: ShopSession, history: MemorySession) -> list[ProductCard]:
    """Retain the last recommendation only while its answer remains in RAM history."""
    retained_assistants = {event.event_id for event in history.events if event.role == "ASSISTANT"}
    for turn in reversed(session.turns):
        if (
            turn.products
            and turn.inspector.event_ids
            and turn.inspector.event_ids[-1] in retained_assistants
        ):
            return turn.products
    return []


def validated_answer_products(answer: ModelAnswer, context: TurnContext) -> list[ProductCard]:
    """Use only supplied products, in the order the answer discusses them."""
    available = {
        product.product_id: product
        for product in [
            *context.previous_products,
            *context.products,
            *(order.product for order in context.purchases),
        ]
    }
    if any(product_id not in available for product_id in answer.product_ids):
        raise ShopError(
            "The adviser returned a product outside the retrieved catalogue. Try again."
        )
    if not answer.text.strip():
        raise ShopError("The adviser returned an empty answer. Try again.")
    return [available[product_id] for product_id in dict.fromkeys(answer.product_ids)]
