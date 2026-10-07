"""Typed boundaries for the camera adviser and its teaching evidence."""

from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.models import ProductPhoto
from app.shop.memory import MemoryRecord, MemorySession

MemoryMode = Literal["none", "session", "both"]
ShopperID = Literal["alex", "jordan"]


class Onboarding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    camera: str = Field(default="", max_length=200)
    interests: str = Field(default="", max_length=300)
    preferences: str = Field(default="", max_length=300)


class ProductCard(BaseModel):
    product_id: str
    title: str
    brand: str | None = None
    description: str
    url: str
    photo: ProductPhoto | None = None


class Purchase(BaseModel):
    order_id: str
    shopper_id: ShopperID
    purchased_at: str
    fictional: bool = True
    product: ProductCard


class Guidance(BaseModel):
    source: Literal["built-in", "playbook"]
    title: str
    text: str
    entry_id: str | None = None
    version: int | None = None


class TurnContext(BaseModel):
    message: str
    mode: MemoryMode
    shopper_id: ShopperID | None = None
    session: MemorySession = Field(default_factory=MemorySession)
    memories: list[MemoryRecord] = Field(default_factory=list)
    previous_products: list[ProductCard] = Field(default_factory=list)
    products: list[ProductCard] = Field(default_factory=list)
    purchases: list[Purchase] = Field(default_factory=list)
    guidance: list[Guidance] = Field(default_factory=list)
    search_query: str | None = None


class ToolDefinition(BaseModel):
    """Provider function definition; MCP schemas are forwarded without rewriting."""

    type: Literal["function"] = "function"
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    description: str
    parameters: dict[str, JsonValue]
    strict: bool = False


class ShoppingTools(Protocol):
    def definitions(self) -> list[ToolDefinition]: ...
    def call(self, name: str, arguments: dict[str, JsonValue]) -> JsonValue: ...


class ToolExecution(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, JsonValue]
    output: JsonValue
    elapsed_ms: float


class AnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    product_ids: list[str]


class ModelRequest(BaseModel):
    """The credential-free JSON body sent to the answer provider."""

    # Preserve provider options exactly, including legacy captures without tools.
    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)

    model: str
    instructions: str
    input: str | list[dict[str, JsonValue]]
    store: bool
    reasoning: dict[str, str]
    max_output_tokens: int
    text: dict[str, JsonValue]


class ModelAnswer(AnswerDraft):
    request: ModelRequest | None = None
    tool_calls: list[ToolExecution] = Field(default_factory=list)


class CacheEntry(BaseModel):
    """Historical evidence, not a claim that RAM is a complete current profile."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    entry_id: str = Field(default_factory=lambda: uuid4().hex, pattern=r"^[a-f0-9]{32}$")
    scope: str = Field(min_length=1)
    mode: MemoryMode
    version: str
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1)
    products: list[ProductCard]
    context: TurnContext
    created_at: float
    expires_at: float


class CacheCandidate(BaseModel):
    entry: CacheEntry
    distance: float = Field(ge=0, le=2, allow_inf_nan=False)


class CacheTrace(BaseModel):
    status: Literal["disabled", "miss", "hit", "rejected", "bypass", "error"] = "disabled"
    reason: str = "Semantic caching is disabled."
    entry_id: str | None = None
    scope: str | None = None
    matched_question: str | None = None
    age_seconds: float | None = None
    distance: float | None = None
    similarity: float | None = None
    distance_threshold: float | None = None
    decision: str | None = None
    confidence: float | None = None
    confidence_threshold: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    lookup_ms: float = 0
    verifier_ms: float = 0
    verifier_model: str | None = None
    verifier_input_tokens: int | None = None
    verifier_cost_usd: float | None = None
    store_status: Literal["not_requested", "stored", "skipped", "error"] = "not_requested"
    store_reason: str | None = None
    stored_entry_id: str | None = None
    stored_scope: str | None = None
    original_context: TurnContext | None = None


class ReuseResult(BaseModel):
    """Lookup outcome, with product evidence returned explicitly on a hit."""

    answer: ModelAnswer | None = None
    products: list[ProductCard] = Field(default_factory=list)
    trace: CacheTrace = Field(default_factory=CacheTrace)


class TurnInspector(BaseModel):
    answer_request: ModelRequest | None = None
    tool_calls: list[ToolExecution] = Field(default_factory=list)
    context: TurnContext
    memory_ms: float
    search_ms: float
    model_ms: float
    total_ms: float
    event_ids: list[str]
    cache: CacheTrace = Field(default_factory=CacheTrace)
    note: str = (
        "Events saved. Automatic extraction is asynchronous; refresh memories to observe it."
    )


class ChatTurn(BaseModel):
    user: str
    assistant: str
    products: list[ProductCard]
    inspector: TurnInspector


class ShopSession(BaseModel):
    session_id: str
    shopper_id: ShopperID
    owner_id: str
    turns: list[ChatTurn] = Field(default_factory=list)
