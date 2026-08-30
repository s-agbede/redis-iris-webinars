"""Application configuration, read once from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    The embedding model is a config value rather than a constant because
    RedisVL abstracts the vectorizer — but note that changing it changes the
    vector dimensions, so the index must be rebuilt (`make seed`).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = Field(..., description="Powers both the agent and embeddings")
    redis_url: str = "redis://localhost:6379"

    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 1536
    agent_model: str = "gpt-4.1-mini"

    # Caches query embeddings in Redis so a repeated search skips the API call.
    embedding_cache_enabled: bool = True

    products_index: str = "products"
    policies_index: str = "policies"

    default_num_results: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
