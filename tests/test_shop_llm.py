import json

import httpx
import pytest

from app.shop.llm import OpenAIShoppingModel
from app.shop.models import TurnContext
from app.shop.service import ShopError
from tests.test_shop_tools import Tools


def test_answer_sends_only_explicit_context_without_provider_history() -> None:
    seen: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"text":"What will you film?","product_ids":[]}',
                            }
                        ],
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    model = OpenAIShoppingModel("secret", "gpt-5-mini", client=client)
    result = model.answer(TurnContext(message="Find a camera", mode="none"), Tools())
    assert result.text == "What will you film?"
    assert seen[0]["store"] is False
    assert "previous_response_id" not in seen[0]
    assert seen[0]["model"] == "gpt-5-mini"
    assert "Find a camera" in str(seen[0]["input"])


@pytest.mark.parametrize(
    "status,body",
    [
        (401, {"error": "secret"}),
        (200, {"status": "incomplete", "output": []}),
        (
            200,
            {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}],
            },
        ),
    ],
)
def test_model_failures_are_explicit_and_do_not_expose_upstream_bodies(
    status: int, body: dict[str, object]
) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    )
    model = OpenAIShoppingModel("secret", "gpt-5-mini", client=client)
    with pytest.raises(ShopError) as error:
        model.answer(TurnContext(message="Hi", mode="both"), Tools())
    assert "secret" not in str(error.value)


def test_answer_captures_exact_sent_body_without_credentials_and_survives_later_calls() -> None:
    from app.shop.models import TurnInspector

    sent: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"text":"What camera do you own?","product_ids":[]}',
                            }
                        ],
                    }
                ],
            },
        )

    model = OpenAIShoppingModel(
        "private-api-key", "gpt-5-mini", client=httpx.Client(transport=httpx.MockTransport(respond))
    )
    context = TurnContext(message="What camera do I own?", mode="none")
    first = model.answer(context, Tools())
    context.message = "Different question"
    model.answer(context, Tools())
    assert first.request is not None
    assert first.request.model_dump(mode="json") == sent[0]
    assert "private-api-key" not in first.request.model_dump_json()
    assert isinstance(first.request.input, list)
    assert json.loads(str(first.request.input[0]["content"]))["message"] == "What camera do I own?"
    inspector = TurnInspector(
        context=context,
        answer_request=first.request,
        memory_ms=0,
        search_ms=0,
        model_ms=0,
        total_ms=0,
        event_ids=[],
    )
    restored = TurnInspector.model_validate_json(inspector.model_dump_json())
    assert restored.answer_request == first.request


def test_older_turns_do_not_fabricate_a_captured_request() -> None:
    from app.shop.models import TurnInspector

    inspector = TurnInspector(
        context=TurnContext(message="Hi", mode="none"),
        memory_ms=0,
        search_ms=0,
        model_ms=0,
        total_ms=0,
        event_ids=[],
    )
    assert inspector.answer_request is None
