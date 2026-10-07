"""Tools available to one adviser turn: catalogue search, cache nomination and MCP reads."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from app.models import CameraProduct, CompareRequest, SearchMode
from app.shop.context_retriever import UNAVAILABLE, ContextRetrieverError
from app.shop.errors import ShopError
from app.shop.models import ProductCard, ShopperID, ToolDefinition, TurnContext

if TYPE_CHECKING:
    from app.shop.service import ShopService


class SearchCatalogueArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=1000, description="The catalogue search query.")


CATALOGUE_TOOL = ToolDefinition(
    name="search_catalogue",
    description=(
        "Search the full local camera catalogue using hybrid keyword and semantic retrieval. "
        "Returns up to five products with IDs, descriptions and links; no prices or live stock. "
        "Use for finding, recommending or comparing gear; include needs and relevant equipment."
    ),
    parameters=SearchCatalogueArguments.model_json_schema(),
    strict=True,
)


class CacheNomination(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scope: Literal["shopper", "shared"]


CACHE_TOOL = ToolDefinition(
    name="store_in_cache",
    description=(
        "Nominate the final reply for semantic caching when it is a complete reusable answer. "
        "Use shopper scope for recommendations, product answers or any personal context. "
        "Shared is only for standalone general camera education without personal information. "
        "Do not nominate greetings, questions seeking clarification, corrections, delivery, "
        "purchase-history or live price/stock answers. Call after required retrieval and before "
        "the final reply. This only nominates: the server stores the validated final answer later."
    ),
    parameters=CacheNomination.model_json_schema(),
    strict=True,
)


class ShopRetrieval:
    """Read tools bound to one shopper; accumulate evidence and a cache nomination.

    Tool results update this turn's context so final validation can check the
    answer's product IDs. Persistent conversation and cache writes happen later.
    """

    def __init__(
        self,
        shop: "ShopService",
        shopper_id: ShopperID,
        context: TurnContext,
        *,
        cache_enabled: bool = False,
    ) -> None:
        self.shop, self.shopper_id, self.context = shop, shopper_id, context
        self._generated: dict[str, ToolDefinition] | None = None
        self.cache_enabled = cache_enabled
        self.nomination: Literal["shopper", "shared"] | None = None
        self.remote_used = False

    def definitions(self) -> list[ToolDefinition]:
        if self._generated is None:
            generated = self.shop.context_retriever.list_tools(self.shopper_id)
            self._generated = {tool.name: tool for tool in generated}
            if any(name in self._generated for name in (CATALOGUE_TOOL.name, CACHE_TOOL.name)):
                raise ContextRetrieverError(
                    "Context Retriever tool conflicts with local catalogue search."
                )
        return [
            CATALOGUE_TOOL,
            *([CACHE_TOOL] if self.cache_enabled else []),
            *self._generated.values(),
        ]

    def call(self, name: str, arguments: dict[str, JsonValue]) -> JsonValue:
        if name == CACHE_TOOL.name and self.cache_enabled:
            try:
                self.nomination = CacheNomination.model_validate(arguments).scope
            except ValidationError:
                raise ShopError(
                    "The adviser returned invalid cache arguments. Try again."
                ) from None
            return {"status": "nominated", "note": "Final answer will be validated before storage."}
        if name == CATALOGUE_TOOL.name:
            try:
                parsed = SearchCatalogueArguments.model_validate(arguments)
            except ValidationError:
                raise ShopError("The adviser returned invalid tool arguments. Try again.") from None
            return {
                "products": [p.model_dump(mode="json") for p in self.search_catalogue(parsed.query)]
            }
        self.definitions()
        tool = (self._generated or {}).get(name)
        if tool is None:
            raise ShopError("The adviser returned an unknown tool call. Try again.")
        self.remote_used = True
        result = self.shop.context_retriever.call_tool(self.shopper_id, tool, arguments)
        self._collect_products(result)
        return result

    def _collect_products(self, result: JsonValue) -> None:
        # Product cards are derived only from records already returned by a tool.
        # This does not fetch linked entities or decide the agent's next tool call.
        if isinstance(result, dict):
            if "product_title" in result:
                # Explicit demo references identify orders but have no catalogue page.
                if result.get("product_locale") == "demo":
                    return
                try:
                    product = CameraProduct.model_validate(
                        {
                            key: value
                            for key, value in result.items()
                            if key in CameraProduct.model_fields
                        },
                        strict=True,
                    )
                except ValidationError:
                    raise ContextRetrieverError(UNAVAILABLE) from None
                if not product.product_id.strip() or not product.product_title.strip():
                    raise ContextRetrieverError(UNAVAILABLE)
                supplied = {p.product_id: p for p in self.context.products}
                supplied[product.product_id] = self.shop.card(product)
                self.context.products = list(supplied.values())
            for value in result.values():
                self._collect_products(value)
        elif isinstance(result, list):
            for item in result:
                self._collect_products(item)

    def search_catalogue(self, query: str) -> list[ProductCard]:
        self.context.search_query = query
        comparison = self.shop.searcher.compare(
            CompareRequest(query=query, num_results=5), modes=(SearchMode.HYBRID,)
        )
        result = comparison.results[0]
        if result.error:
            raise ShopError("Catalogue search is unavailable. Check the search lab readiness.")
        products = [
            self.shop.card(product)
            for hit in result.hits
            if (product := self.shop.product(hit.product_id)) is not None
        ]
        # Earlier search results remain valid evidence if the model refines its query.
        supplied = {product.product_id: product for product in self.context.products}
        supplied.update({product.product_id: product for product in products})
        self.context.products = list(supplied.values())
        return products
