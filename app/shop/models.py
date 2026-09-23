"""Typed boundaries for the camera adviser and its teaching evidence."""

from typing import Literal, Protocol

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
    session: MemorySession = Field(default_factory=MemorySession)
    memories: list[MemoryRecord] = Field(default_factory=list)
    previous_products: list[ProductCard] = Field(default_factory=list)
    products: list[ProductCard] = Field(default_factory=list)
    purchases: list[Purchase] = Field(default_factory=list)
    guidance: list[Guidance] = Field(default_factory=list)
    search_query: str | None = None


class ShoppingTools(Protocol):
    def search_catalogue(self, query: str) -> list[ProductCard]: ...
    def get_purchase_history(self) -> list[Purchase]: ...


ToolName = Literal["search_catalogue", "get_purchase_history"]


class ToolExecution(BaseModel):
    call_id: str
    name: ToolName
    arguments: dict[str, JsonValue]
    output: dict[str, JsonValue]
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


class TurnInspector(BaseModel):
    answer_request: ModelRequest | None = None
    tool_calls: list[ToolExecution] = Field(default_factory=list)
    context: TurnContext
    memory_ms: float
    search_ms: float
    model_ms: float
    total_ms: float
    event_ids: list[str]
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
