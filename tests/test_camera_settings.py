from app.settings import Settings


def test_camera_search_does_not_require_a_hosted_api_key() -> None:
    settings = Settings(_env_file=None)
    assert settings.embedding_dims == 384
    assert settings.index_algorithm == "FLAT"
    assert settings.products_index.startswith("camera")
