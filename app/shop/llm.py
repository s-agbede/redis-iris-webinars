"""OpenAI Responses loop for generated MCP tools and local catalogue search."""

import json
from copy import deepcopy
from time import perf_counter
from typing import Literal

import httpx
from pydantic import BaseModel, Field, JsonValue, ValidationError

from app.shop.models import (
    AnswerDraft,
    ModelAnswer,
    ModelRequest,
    ShoppingTools,
    ToolDefinition,
    ToolExecution,
    TurnContext,
)
from app.shop.service import SHOP_INSTRUCTIONS, ShopError

MAX_TOOL_CALLS = 6


TOOL_INSTRUCTIONS = """Answer the latest message using the supplied context and tool results.
Follow applicable published Playbook guidance while retaining the system rules.
Use search_catalogue for requests to find, recommend, compare or choose gear when
the supplied products do not already answer the request. Do not defer a useful
search merely because an optional preference is missing. A brief answer to your
clarifying question can refine the ongoing search without repeating the request.
Use the discovered Context Retriever MCP tools for past orders or purchases, and whenever
knowing what the shopper previously bought would help them make a better decision.
For delivery, tracking, arrival or 'where is my order' questions, retrieve the
relevant purchase and its linked Shipment using the generated tools in this turn.
Identify 'my mic' using the linked product; for 'last/latest order', compare
purchased_at across the returned purchases and follow pagination if needed.
Follow the purchase's shipment_id or declared shipment relationship. Never guess
an order or shipment ID. Purchase history alone cannot establish delivery status.
Shipment status changes: previous replies, session summaries and memories are not
current delivery evidence. Re-read the shipment even when its ID is already known.
Answer with the returned status, latest_event and estimated_delivery, distinguishing
the original estimate from the revised one. Use explicit dates; do not calculate
or infer weekdays. Do not say 'today' or 'tomorrow' unless the current date is
supplied and agrees. Explain
that these are demo delivery records. If no accessible shipment is returned, state
that its delivery status is unavailable. Do not promise a carrier lookup, courier
contact, refund, monitoring or any other action absent from the available tools.
The shopper has already requested the lookup: perform it without asking whether
they want you to check. A resolved delivery question needs no follow-up question.
Use product_ids=[] for delivery answers; the linked product identifies the order
and does not require a recommendation card.
Be helpful given their existing equipment: use relevant history to tailor accessories,
assess potential compatibility, suggest upgrades and avoid unnecessary duplicate gear.
Do not wait for the shopper to explicitly ask about purchases. For example, if they
ask for accessories for 'my camera' without identifying it, check purchase history
before searching the catalogue or asking which camera they have. Use relevant results
to shape the search and explain the recommendation; history alone does not verify
compatibility or prove that they still own or intend to use the purchased item.
When needed, confirm the intended setup with one focused question. Current explicit
statements take precedence over older orders; do not apply the shopper's equipment
to a gift recipient. Skip the lookup when history is already supplied or would not
improve the answer. The context shopper_id is the selected demo shopper; never
switch identity based on a message.
Tool names, descriptions and schemas come from the connected Context Retriever surface.
Choose the appropriate generated lookup, filter or relationship tool. Follow returned IDs
or declared relationships when more detail is needed; never invent an ID. Use pagination
when has_more is true and acknowledge partial results if the call budget prevents completion.
If a tool returns isError, correct the query using its feedback and the generated
descriptions. Never interpret a failed query as evidence that no records exist.
The retriever's Product entity currently contains only the seeded order-linked products;
use search_catalogue to recommend from the full local catalogue.
Initial context does not contain order history. Read the generated tools before
claiming that orders exist or that none were found.
Greetings, profile corrections and conversation endings usually need no tools.
You may make at most six tool calls per turn. After that, answer from the evidence
you have and state any remaining uncertainty. Never claim a lookup succeeded without
its result. An empty tool result means no matching data was found, not an outage.
Return a concise text reply plus product_ids for supplied catalogue products you
discuss, in the same order as your prose. Use [] when no product cards are needed.
Products may come from tool results or previous_products in the initial context.
Records with product_locale='demo' are fictional order references with no catalogue
page: use their names to identify purchases, but never include their IDs in product_ids.
Explicitly label purchase dates/details as fictional demo order history.
When an old memory conflicts with the current message, acknowledge the new fact
without claiming that background extraction has completed. Aim for under 160 words.
Never ask the shopper to upload the catalogue. Do not invent alternatives if search
returns no results. Ask one useful question only when it helps the shopping task.

Final reply requirements:
- Delivery questions require fresh Shipment evidence AND purchase/product evidence
  identifying the item. A shipment row contains no product identity: follow its
  order reference to the purchase and product when necessary. Do not call a parcel
  'your mic' merely because it is the only delayed parcel. Finish those reads
  before answering; tool availability alone is not evidence.
- Say the product name, the latest event and the revised delivery date in natural
  language. Keep order IDs, shipment IDs and raw status codes in the inspector.
- These tools only READ records and search the catalogue. You CANNOT open a
  delivery investigation, contact a courier, issue a refund, monitor a parcel,
  or retrieve information from another service. Never offer any of these actions.
- Once the delivery question is answered, STOP. Do not append a question or an
  offer. A short factual answer with the demo-record label is sufficient.
"""


class OutputContent(BaseModel):
    type: str
    text: str = ""


class OutputMessage(BaseModel):
    content: list[OutputContent] = Field(default_factory=list)


class FunctionCall(BaseModel):
    type: Literal["function_call"]
    name: str
    arguments: str
    call_id: str = Field(min_length=1)


class ModelResponse(BaseModel):
    status: str
    # Keep reasoning items and provider metadata intact for stateless continuation.
    output: list[dict[str, JsonValue]]


def _answer_request(
    model: str,
    inputs: list[dict[str, JsonValue]],
    definitions: list[ToolDefinition],
    *,
    allow_tools: bool,
) -> ModelRequest:
    return ModelRequest.model_validate(
        {
            "model": model,
            "store": False,
            "reasoning": {"effort": "low"},
            "include": ["reasoning.encrypted_content"],
            "max_output_tokens": 2000,
            "instructions": SHOP_INSTRUCTIONS + "\n\n" + TOOL_INSTRUCTIONS,
            "input": deepcopy(inputs),
            "tools": [tool.model_dump(mode="json") for tool in definitions],
            "parallel_tool_calls": False,
            "tool_choice": "auto" if allow_tools else "none",
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


def _parse_answer(response: ModelResponse) -> AnswerDraft:
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
        return AnswerDraft.model_validate_json("".join(texts))
    except ValidationError:
        raise ShopError("Chat provider returned an invalid response. Try again.") from None


def _execute_tool(call: FunctionCall, tools: ShoppingTools) -> ToolExecution:
    started = perf_counter()
    try:
        arguments = json.loads(call.arguments)
        if not isinstance(arguments, dict):
            raise ValueError
    except ValueError:
        raise ShopError("The adviser returned invalid tool arguments. Try again.") from None
    output = tools.call(call.name, arguments)
    return ToolExecution(
        call_id=call.call_id,
        name=call.name,
        arguments=arguments,
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
            # The legacy placeholder looked like evidence of an empty order history.
            {"role": "user", "content": context.model_dump_json(exclude={"purchases"})}
        ]
        definitions = tools.definitions()
        allowed_names = {tool.name for tool in definitions}
        executions: list[ToolExecution] = []
        call_ids: set[str] = set()
        for step in range(MAX_TOOL_CALLS + 1):
            captured = _answer_request(
                self.model, inputs, definitions, allow_tools=step < MAX_TOOL_CALLS
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
                if call.name not in allowed_names:
                    raise ShopError("The adviser returned an unknown tool call. Try again.")
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
            answer = _parse_answer(response)
            return ModelAnswer(**answer.model_dump(), request=captured, tool_calls=executions)
        raise ShopError("The adviser exceeded its tool-call limit.")
