from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_shop import make_shop


def test_shop_session_onboarding_and_chat_journey() -> None:
    shop, _, _, _ = make_shop()
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        session = client.post("/api/shop/sessions", json={"shopper_id": "alex"})
        assert session.status_code == 200
        session_id = session.json()["session_id"]
        response = client.post(
            "/api/shop/onboarding",
            json={"shopper_id": "alex", "camera": "Sony", "interests": "Travel", "preferences": ""},
        )
        assert response.status_code == 200
        assert len(response.json()["memories"]) == 2
        response = client.post(
            "/api/shop/chat",
            json={
                "shopper_id": "alex",
                "session_id": session_id,
                "message": "Hello",
                "mode": "both",
            },
        )
        assert response.status_code == 200
        assert response.json()["assistant"] == "What do you film?"
        loaded = client.get(f"/api/shop/sessions/{session_id}", params={"shopper_id": "alex"})
        assert len(loaded.json()["turns"]) == 1
        assert (
            client.get(
                f"/api/shop/sessions/{session_id}", params={"shopper_id": "jordan"}
            ).status_code
            == 400
        )


def test_shop_rejects_unknown_shoppers_and_excessively_long_messages() -> None:
    shop, _, _, _ = make_shop()
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        assert client.post("/api/shop/sessions", json={"shopper_id": "someone"}).status_code == 422
        assert (
            client.post(
                "/api/shop/chat",
                json={
                    "shopper_id": "alex",
                    "session_id": "absent",
                    "message": "x" * 4001,
                    "mode": "both",
                },
            ).status_code
            == 422
        )


def test_memory_inspection_uses_only_selected_demo_owner() -> None:
    shop, _, _, _ = make_shop()
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        client.post("/api/shop/onboarding", json={"shopper_id": "alex", "camera": "Sony"})
        assert (
            len(client.get("/api/shop/memories", params={"shopper_id": "alex"}).json()["memories"])
            == 1
        )
        assert (
            client.get("/api/shop/memories", params={"shopper_id": "jordan"}).json()["memories"]
            == []
        )
