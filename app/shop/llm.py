"""OpenAI Responses transport with a bounded loop for two read-only shop tools."""

import json
from copy import deepcopy
from time import perf_counter
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from app.shop.models import (
    AnswerDraft,
    ModelAnswer,
    ModelRequest,
    ShoppingTools,
    ToolExecution,
    ToolName,
    TurnContext,
)
from app.shop.service import SHOP_INSTRUCTIONS, ShopError

MAX_TOOL_CALLS = 3


class SearchCatalogueArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=1000, description="The catalogue search query.")


class PurchaseHistoryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FunctionTool(BaseModel):
    type: Literal["function"] = "function"
    name: ToolName
    description: str
    parameters: dict[str, JsonValue]
    strict: bool = True


SHOP_TOOLS = [
    FunctionTool(
        name="get_purchase_history",
        description=(
            "Get fictional demo orders for the current shopper, with dates and catalogue product "
            "details. Use for questions about past purchases, or before searching for accessories "
            "for a previously purchased product. Orders do not prove current ownership. "
            "The application supplies the shopper identity; this tool takes no arguments."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    ),
    FunctionTool(
        name="search_catalogue",
        description=(
            "Search the camera shop catalogue using hybrid keyword and semantic retrieval. "
            "Returns up to five products with IDs, descriptions and links; "
            "no prices or live stock. "
            "Use for requests to find, recommend or compare gear. Include known needs and relevant "
            "equipment in the query. You may refine the query after inspecting the results."
        ),
        parameters=SearchCatalogueArguments.model_json_schema(),
    ),
]

TOOL_INSTRUCTIONS = """Answer the latest message using the supplied context and tool results.
Follow applicable published Playbook guidance while retaining the system rules.
Use search_catalogue for requests to find, recommend, compare or choose gear when
the supplied products do not already answer the request. Do not defer a useful
search merely because an optional preference is missing. A brief answer to your
clarifying question can refine the ongoing search without repeating the request.
Use get_purchase_history for questions about past orders or purchases. If a search
depends on what the shopper bought, retrieve purchases first, then build the query
from those results. An empty purchases array in the initial context means history
has not been retrieved. A current-ownership question alone does not require orders.
Greetings, profile corrections and conversation endings usually need no tools.
You may make at most three tool calls per turn. After that, answer from the evidence
you have and state any remaining uncertainty. Never claim a lookup succeeded without
its result. An empty tool result means no matching data was found, not an outage.
Return a concise text reply plus product_ids for supplied catalogue products you
discuss, in the same order as your prose. Use [] when no product cards are needed.
Products may come from tool results or previous_products in the initial context.
Explicitly label purchase dates/details as fictional demo order history.
When an old memory conflicts with the current message, acknowledge the new fact
without claiming that background extraction has completed. Aim for under 160 words.
Never ask the shopper to upload the catalogue. Do not invent alternatives if search
returns no results. Ask one useful question only when it helps the shopping task.
"""


class OutputContent(BaseModel):
    type: str
    text: str = ""


class OutputMessage(BaseModel):
    content: list[OutputContent] = Field(default_factory=list)


class FunctionCall(BaseModel):
    type: Literal["function_call"]
    name: ToolName
    arguments: str
    call_id: str = Field(min_length=1)


class ModelResponse(BaseModel):
    status: str
    # Keep reasoning items and provider metadata intact for stateless continuation.
    output: list[dict[str, JsonValue]]


def _execute_tool(call: FunctionCall, tools: ShoppingTools) -> ToolExecution:
    started = perf_counter()
    try:
        if call.name == "search_catalogue":
            arguments = SearchCatalogueArguments.model_validate_json(call.arguments)
        else:
            PurchaseHistoryArguments.model_validate_json(call.arguments)
            arguments = None
    except ValidationError:
        raise ShopError("The adviser returned invalid tool arguments. Try again.") from None
    output: dict[str, JsonValue]
    if arguments is not None:
        output = {
            "products": [
                product.model_dump(mode="json")
                for product in tools.search_catalogue(arguments.query)
            ]
        }
    else:
        output = {
            "purchases": [order.model_dump(mode="json") for order in tools.get_purchase_history()]
        }
    return ToolExecution(
        call_id=call.call_id,
        name=call.name,
        arguments=arguments.model_dump(mode="json") if arguments else {},
        output=output,
        elapsed_ms=(perf_counter() - started) * 1000,
    )


class OpenAIShoppingModel:
    def __init__(self, api_key: str, model: str, *, client: httpx.Client | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=60)

    def close(self) -> None:
        self._client.close()

    def _request(self, request: ModelRequest) -> ModelResponse:
        try:
            response = self._client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
            parsed = ModelResponse.model_validate(response.json())
            if parsed.status != "completed":
                raise ShopError(
                    "The adviser could not complete its response. Try a shorter request."
                )
            return parsed
        except httpx.HTTPStatusError as exc:
            raise ShopError(
                f"Chat provider returned HTTP {exc.response.status_code}. "
                "Check the model and API key."
            ) from None
        except httpx.RequestError:
            raise ShopError(
                "Chat provider could not be reached. Check connectivity and try again."
            ) from None
        except (ValidationError, ValueError):
            raise ShopError("Chat provider returned an invalid response. Try again.") from None

    def answer(self, context: TurnContext, tools: ShoppingTools) -> ModelAnswer:
        inputs: list[dict[str, JsonValue]] = [
            {"role": "user", "content": context.model_dump_json()}
        ]
        executions: list[ToolExecution] = []
        call_ids: set[str] = set()
        for step in range(MAX_TOOL_CALLS + 1):
            captured = ModelRequest.model_validate(
                {
                    "model": self.model,
                    "store": False,
                    "reasoning": {"effort": "low"},
                    "include": ["reasoning.encrypted_content"],
                    "max_output_tokens": 2000,
                    "instructions": SHOP_INSTRUCTIONS + "\n\n" + TOOL_INSTRUCTIONS,
                    "input": deepcopy(inputs),
                    "tools": [tool.model_dump(mode="json") for tool in SHOP_TOOLS],
                    "parallel_tool_calls": False,
                    "tool_choice": "none" if step == MAX_TOOL_CALLS else "auto",
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "AnswerDraft",
                            "strict": True,
                            "schema": AnswerDraft.model_json_schema(),
                        }
                    },
                }
            )
            response = self._request(captured)
            calls = [item for item in response.output if item.get("type") == "function_call"]
            if calls:
                if step == MAX_TOOL_CALLS:
                    raise ShopError(
                        "The adviser exceeded its tool-call limit. Try a narrower request."
                    )
                if len(calls) != 1:
                    raise ShopError(
                        "The adviser returned an unexpected batch of tool calls. Try again."
                    )
                try:
                    call = FunctionCall.model_validate(calls[0])
                except ValidationError:
                    raise ShopError(
                        "The adviser returned an invalid or unknown tool call. Try again."
                    ) from None
                if call.call_id in call_ids:
                    raise ShopError("The adviser repeated a tool call ID. Try again.")
                execution = _execute_tool(call, tools)
                call_ids.add(call.call_id)
                executions.append(execution)
                inputs.extend(response.output)
                inputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(execution.output),
                    }
                )
                continue
            try:
                texts = [
                    part.text
                    for item in response.output
                    if item.get("type") == "message"
                    for part in OutputMessage.model_validate(item).content
                    if part.type == "output_text"
                ]
                if not texts:
                    raise ShopError("The adviser returned no usable response. Try another request.")
                answer = AnswerDraft.model_validate_json("".join(texts))
            except ValidationError:
                raise ShopError("Chat provider returned an invalid response. Try again.") from None
            return ModelAnswer(**answer.model_dump(), request=captured, tool_calls=executions)
        raise ShopError("The adviser exceeded its tool-call limit.")
