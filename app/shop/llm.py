"""OpenAI Responses loop for generated MCP tools and local catalogue search."""

import json
from copy import deepcopy
from time import perf_counter
from typing import Literal

import httpx
from pydantic import BaseModel, Field, JsonValue, ValidationError

from app.shop.errors import ShopError
from app.shop.models import (
    AnswerDraft,
    ModelAnswer,
    ModelRequest,
    ShoppingTools,
    ToolDefinition,
    ToolExecution,
    TurnContext,
)
from app.shop.prompts import SHOP_INSTRUCTIONS, TOOL_INSTRUCTIONS

MAX_TOOL_CALLS = 6


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
