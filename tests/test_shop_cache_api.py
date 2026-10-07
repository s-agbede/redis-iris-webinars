from fastapi.testclient import TestClient

from app.main import create_app
from app.shop.settings import ShopSettings
from tests.test_shop_cache_flow import make_cached_shop


def test_cache_configuration_does_not_make_ordinary_chat_require_jev():
    settings = ShopSettings(_env_file=None, shop_cache_enabled=True)
    assert settings.cache_missing() == ["OPENROUTER_API_KEY"]
    assert "OPENROUTER_API_KEY" not in settings.missing()


def test_cache_api_clear_and_remove_are_scoped_to_selected_demo_shopper():
    shop, _, _, _, cache, _ = make_cached_shop()
    alex, jordan = shop.new_session("alex"), shop.new_session("jordan")
    shop.turn("alex", alex.session_id, "Explain aperture", "both")
    shop.turn("jordan", jordan.session_id, "Explain aperture", "both")
    alex_id = cache.entries[0].entry_id
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        response = client.post(
            "/api/shop/cache/remove",
            json={
                "shopper_id": "jordan",
                "entry_id": alex_id,
            },
        )
        assert response.json() == {"deleted": False}
        assert client.post("/api/shop/cache/clear", json={"shopper_id": "alex"}).json() == {
            "deleted": 1
        }
        assert len(cache.entries) == 1 and cache.entries[0].scope == jordan.owner_id
        assert (
            client.post(
                "/api/shop/cache/remove",
                json={
                    "shopper_id": "alex",
                    "entry_id": "some:redis:key",
                },
            ).status_code
            == 422
        )


def test_cache_clear_cannot_race_a_chat_turn():
    shop, _, _, _, _, _ = make_cached_shop()
    app = create_app(lambda: shop.searcher, shop_builder=lambda _: shop)
    with TestClient(app) as client:
        app.state.shop_turn_lock.acquire()
        try:
            assert (
                client.post("/api/shop/cache/clear", json={"shopper_id": "alex"}).status_code == 409
            )
        finally:
            app.state.shop_turn_lock.release()


def test_http_chat_forwards_explicit_cache_bypass():
    from tests.test_shop import Model

    shop, _, _, _, cache, _ = make_cached_shop()
    shop.model = Model()
    session = shop.new_session("alex")
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        response = client.post(
            "/api/shop/chat",
            json={
                "shopper_id": "alex",
                "session_id": session.session_id,
                "message": "Hello",
                "mode": "both",
                "use_cache": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["inspector"]["cache"]["status"] == "bypass"
        assert cache.lookups == []
