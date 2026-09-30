"""Discovery and tool failures never become a fabricated or saved chat reply."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.shop.service import ShopService
from tests.test_search import service
from tests.test_shop import Memory, Store
from tests.test_shop_mcp import MCPBackend, client_for
from tests.test_shop_tools import final_response, function_call, model_with


def chat_shop(backend):
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        output = (
            function_call("filter_purchase")
            if len(requests) == 1
            else final_response("No matching orders.")
        )
        return httpx.Response(200, json={"status": "completed", "output": [output]})

    searcher, _, _ = service()
    retriever = client_for(backend)
    return (
        ShopService(
            searcher,
            Memory(),
            Store(),
            model_with(respond),
            owner_prefix="retrieval-chat-test",
            context_retriever=retriever,
        ),
        requests,
        retriever._client,
    )


def test_empty_history_reaches_model_without_demo_fallback():
    shop, requests, _ = chat_shop(MCPBackend("empty"))
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        session = client.post("/api/shop/sessions", json={"shopper_id": "alex"}).json()
        response = client.post(
            "/api/shop/chat",
            json={
                "shopper_id": "alex",
                "session_id": session["session_id"],
                "message": "Past orders?",
            },
        )
        assert response.status_code == 200
        assert response.json()["products"] == []
        assert json.loads(requests[-1]["input"][-1]["output"]) == {"results": [], "has_more": False}


@pytest.mark.parametrize(
    "fault,model_calls", [("timeout", 0), ("expired", 0), ("foreign", 1), ("tool-error", 1)]
)
def test_failed_retrieval_returns_503_without_continuation_or_saved_reply(fault, model_calls):
    shop, requests, pool = chat_shop(MCPBackend(fault))
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        session = client.post("/api/shop/sessions", json={"shopper_id": "alex"}).json()
        response = client.post(
            "/api/shop/chat",
            json={
                "shopper_id": "alex",
                "session_id": session["session_id"],
                "message": "Past orders?",
            },
        )
        assert response.status_code == 503
        assert response.json() == {
            "detail": "Context Retriever is unavailable. Please try again shortly.",
            "retry_safe": True,
        }
        assert len(requests) == model_calls
        assert shop.memory.session(session["session_id"]).events == []
        assert shop.session("alex", session["session_id"]).turns == []
    assert pool.is_closed


def test_foreign_session_is_rejected_before_discovery_or_model_access():
    backend = MCPBackend()
    shop, requests, _ = chat_shop(backend)
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        session = client.post("/api/shop/sessions", json={"shopper_id": "alex"}).json()
        response = client.post(
            "/api/shop/chat",
            json={
                "shopper_id": "jordan",
                "session_id": session["session_id"],
                "message": "Past orders?",
            },
        )
        assert response.status_code == 400
        assert requests == [] and backend.requests == []
