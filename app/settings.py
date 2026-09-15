"""Configuration for the local camera lab; serving never downloads model files."""

from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
MODEL: Final = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION: Final = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    redis_url: str = "redis://localhost:6379"
    namespace: str = "camera"
    data_dir: Path = ROOT / "seed/cameras"
    model_path: Path | None = None
    embedding_model: Literal["sentence-transformers/all-MiniLM-L6-v2"] = MODEL
    embedding_revision: Literal["c9745ed1d9f207416be6d2e6f8de32d1f16199bf"] = MODEL_REVISION
    embedding_dims: Literal[384] = 384
    index_algorithm: Literal["FLAT", "HNSW"] = "FLAT"
    passage_tokens: int = Field(default=240, ge=96, le=254)
    passage_overlap: int = Field(default=32, ge=0, le=64)
    candidate_limit: int = Field(default=100, ge=20, le=1000)

    @property
    def products_index(self) -> str:
        return f"{self.namespace}_passages"

    @property
    def passage_prefix(self) -> str:
        return f"{self.namespace}:passage"

    @property
    def product_prefix(self) -> str:
        return f"{self.namespace}:product"

    @property
    def manifest_key(self) -> str:
        return f"{self.namespace}:manifest"


@lru_cache
def get_settings() -> Settings:
    return Settings()
