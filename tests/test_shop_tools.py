import json
from collections.abc import Callable

import httpx
import pytest

from app.shop.llm import OpenAIShoppingModel
from app.shop.models import ProductCard, Purchase, TurnContext
from app.shop.service import ShopError


class Tools:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_purchase_history(self) -> list[Purchase]:
        self.calls.append("purchases")
        return [
            Purchase(
                order_id="demo-order",
                shopper_id="alex",
                purchased_at="2026-04-18",
                product=ProductCard(
                    product_id="camera", title="Sony ZV-E10", description="Camera", url="/camera"
                ),
            )
        ]

    def search_catalogue(self, query: str) -> list[ProductCard]:
        self.calls.append(query)
        return [ProductCard(product_id="mic", title="Microphone", description="Mic", url="/mic")]


def final_response(text: str = "Here is an option.") -> dict[str, object]:
    return {
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "output_text",
                "text": json.dumps({"text": text, "product_ids": []}),
            }
        ],
    }


def function_call(name: str, arguments: str = "{}", call_id: str = "call-1") -> dict[str, object]:
    return {
        "type": "function_call",
        "id": f"fc-{call_id}",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
        "status": "completed",
    }


def model_with(respond: Callable[[httpx.Request], httpx.Response]) -> OpenAIShoppingModel:
    return OpenAIShoppingModel(
        "private-key", "gpt-5-mini", client=httpx.Client(transport=httpx.MockTransport(respond))
    )


def test_native_tools_allow_a_direct_answer_without_a_planning_request() -> None:
    sent: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        definitions = {tool["name"]: tool for tool in body["tools"]}
        assert set(definitions) == {"get_purchase_history", "search_catalogue"}
        for tool in definitions.values():
            assert tool["type"] == "function" and tool["strict"] is True
            assert tool["parameters"]["additionalProperties"] is False
        assert definitions["get_purchase_history"]["parameters"]["properties"] == {}
        assert definitions["search_catalogue"]["parameters"]["required"] == ["query"]
        assert body["parallel_tool_calls"] is False
        assert body["store"] is False
        assert "previous_response_id" not in body
        return httpx.Response(200, json={"status": "completed", "output": [final_response()]})

    tools = Tools()
    answer = model_with(respond).answer(TurnContext(message="Hello", mode="none"), tools)

    assert len(sent) == 1 and tools.calls == []
    assert answer.request is not None
    assert answer.request.model_dump(mode="json") == sent[0]
    assert "private-key" not in answer.request.model_dump_json()
    assert answer.tool_calls == []


def test_purchase_result_can_inform_later_search_and_exact_request_is_preserved() -> None:
    sent: list[dict[str, object]] = []
    reasoning = {"type": "reasoning", "id": "rs-1", "summary": [], "encrypted_content": "opaque"}
    purchase_call = function_call("get_purchase_history")
    search_call = function_call("search_catalogue", '{"query":"microphone Sony ZV-E10"}', "call-2")

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        if len(sent) == 1:
            assert "reasoning.encrypted_content" in body["include"]
            output = [reasoning, purchase_call]
        elif len(sent) == 2:
            assert body["input"][1:3] == [reasoning, purchase_call]
            result = body["input"][3]
            assert result["type"] == "function_call_output" and result["call_id"] == "call-1"
            assert json.loads(result["output"])["purchases"][0]["product"]["title"] == "Sony ZV-E10"
            output = [search_call]
        else:
            result = body["input"][-1]
            assert result["call_id"] == "call-2"
            assert json.loads(result["output"])["products"][0]["product_id"] == "mic"
            output = [final_response()]
        return httpx.Response(200, json={"status": "completed", "output": output})

    tools = Tools()
    context = TurnContext(message="A microphone for the camera I bought here", mode="both")
    answer = model_with(respond).answer(context, tools)

    assert tools.calls == ["purchases", "microphone Sony ZV-E10"]
    assert len(sent) == 3
    assert [call.name for call in answer.tool_calls] == ["get_purchase_history", "search_catalogue"]
    assert answer.tool_calls[1].arguments == {"query": "microphone Sony ZV-E10"}
    assert all(call.elapsed_ms >= 0 for call in answer.tool_calls)
    assert answer.request is not None and answer.request.model_dump(mode="json") == sent[-1]
    captured = answer.request.model_dump_json()
    context.message = "Changed later"
    assert answer.request.model_dump_json() == captured


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("delete_memory", "{}"),
        ("get_purchase_history", '{"shopper_id":"jordan"}'),
        ("search_catalogue", '{"query":"camera","owner_id":"jordan"}'),
        ("search_catalogue", "not-json"),
        ("search_catalogue", "{}"),
        ("search_catalogue", '{"query":"   "}'),
        ("search_catalogue", '{"query":42}'),
        ("search_catalogue", json.dumps({"query": "x" * 1001})),
    ],
)
def test_invalid_tool_calls_are_rejected_before_execution(name: str, arguments: str) -> None:
    tools = Tools()
    model = model_with(
        lambda _: httpx.Response(
            200, json={"status": "completed", "output": [function_call(name, arguments)]}
        )
    )
    with pytest.raises(ShopError, match="tool"):
        model.answer(TurnContext(message="Find gear", mode="both"), tools)
    assert tools.calls == []


def test_tool_limit_prevents_unbounded_retrieval() -> None:
    requests = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        body = json.loads(request.content)
        if requests == 4:
            assert body["tool_choice"] == "none"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [function_call("get_purchase_history", call_id=f"call-{requests}")],
            },
        )

    tools = Tools()
    with pytest.raises(ShopError, match="limit"):
        model_with(respond).answer(TurnContext(message="Keep looking", mode="both"), tools)
    assert len(tools.calls) == 3 and requests == 4


def test_unexpected_parallel_calls_do_not_execute() -> None:
    tools = Tools()
    model = model_with(
        lambda _: httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    function_call("get_purchase_history", call_id=f"call-{i}") for i in range(2)
                ],
            },
        )
    )
    with pytest.raises(ShopError, match="tool"):
        model.answer(TurnContext(message="Find gear", mode="both"), tools)
    assert tools.calls == []


def test_reused_call_id_does_not_execute_twice() -> None:
    tools = Tools()
    model = model_with(
        lambda _: httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [function_call("get_purchase_history")],
            },
        )
    )
    with pytest.raises(ShopError, match="tool"):
        model.answer(TurnContext(message="Find gear", mode="both"), tools)
    assert tools.calls == ["purchases"]


def test_tool_failure_is_not_reported_to_the_model_as_an_empty_result() -> None:
    class UnavailableTools(Tools):
        def search_catalogue(self, query: str) -> list[ProductCard]:
            raise ShopError("Catalogue search is unavailable.")

    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [function_call("search_catalogue", '{"query":"camera"}')],
            },
        )

    with pytest.raises(ShopError, match="unavailable"):
        model_with(respond).answer(
            TurnContext(message="Find gear", mode="both"), UnavailableTools()
        )
    assert len(requests) == 1


def test_shop_http_turn_chains_purchases_into_search_and_records_only_the_exchange() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import CameraProduct
    from tests.test_shop import make_shop

    shop, memory, _, _ = make_shop()
    shop.searcher.catalog.products["B09BBKVMCD"] = CameraProduct(
        product_id="B09BBKVMCD", product_title="Sony ZV-E10"
    )
    bodies: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            output = function_call("get_purchase_history")
        elif len(bodies) == 2:
            orders = json.loads(body["input"][-1]["output"])["purchases"]
            assert len(orders) == 1 and orders[0]["shopper_id"] == "alex"
            assert orders[0]["fictional"] is True
            title = orders[0]["product"]["title"]
            output = function_call(
                "search_catalogue", json.dumps({"query": f"microphone {title}"}), "call-2"
            )
        else:
            products = json.loads(body["input"][-1]["output"])["products"]
            assert products
            output = {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "text": "An option for your fictional purchase.",
                                "product_ids": [products[0]["product_id"]],
                            }
                        ),
                    }
                ],
            }
        return httpx.Response(200, json={"status": "completed", "output": [output]})

    shop.model = model_with(respond)
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        session = client.post("/api/shop/sessions", json={"shopper_id": "alex"}).json()
        response = client.post(
            "/api/shop/chat",
            json={
                "shopper_id": "alex",
                "session_id": session["session_id"],
                "message": "A microphone for the camera I bought here",
                "mode": "both",
            },
        )
        assert response.status_code == 200, response.text
        turn = response.json()
        assert turn["inspector"]["context"]["search_query"] == "microphone Sony ZV-E10"
        assert [call["name"] for call in turn["inspector"]["tool_calls"]] == [
            "get_purchase_history",
            "search_catalogue",
        ]
        assert turn["inspector"]["answer_request"] == bodies[-1]
        assert turn["products"][0]["product_id"] in {"a", "b"}
        events = memory.events[session["session_id"]]
        assert [event.role for event in events] == ["USER", "ASSISTANT"]
        restored = client.get(
            f"/api/shop/sessions/{session['session_id']}", params={"shopper_id": "alex"}
        ).json()
        assert restored["turns"][0]["inspector"]["tool_calls"] == turn["inspector"]["tool_calls"]


def test_shop_tools_bind_purchase_history_to_the_selected_shopper() -> None:
    from app.models import CameraProduct
    from app.shop.service import ShopRetrieval
    from tests.test_shop import make_shop

    shop, _, _, _ = make_shop()
    shop.searcher.catalog.products["B09BBKVMCD"] = CameraProduct(
        product_id="B09BBKVMCD", product_title="Alex's camera"
    )
    shop.searcher.catalog.products["B06XG9T25F"] = CameraProduct(
        product_id="B06XG9T25F", product_title="Jordan's camera"
    )
    tools = ShopRetrieval(shop, "jordan", TurnContext(message="My orders", mode="both"))
    orders = tools.get_purchase_history()
    assert len(orders) == 1 and orders[0].shopper_id == "jordan"
    assert orders[0].product.title == "Jordan's camera"


def test_refined_search_retains_products_supplied_by_earlier_searches() -> None:
    from app.shop.service import ShopRetrieval
    from tests.test_shop import make_shop

    shop, _, _, _ = make_shop()
    context = TurnContext(message="Find gear", mode="both")
    tools = ShopRetrieval(shop, "alex", context)
    assert "a" in {product.product_id for product in tools.search_catalogue("camera")}
    del shop.searcher.catalog.products["a"]
    assert "a" not in {product.product_id for product in tools.search_catalogue("refined camera")}
    assert "a" in {product.product_id for product in context.products}
    assert context.search_query == "refined camera"
