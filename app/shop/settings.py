"""Optional service credentials for the locally hosted teaching shop."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.settings import ROOT


class ShopSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    agent_memory_base_url: str = ""
    agent_memory_store_id: str = ""
    agent_memory_api_key: SecretStr = SecretStr("")
    agent_memory_namespace_id: str | None = None
    shop_owner_prefix: str = Field(default="sams-camera-shop-v1", pattern=r"^[a-zA-Z0-9-]{1,48}$")
    openai_api_key: SecretStr = SecretStr("")
    shop_chat_model: str = "gpt-5-mini"
    shop_playbook_url: str = ""
    shop_playbook_id: str = ""
    shop_playbook_api_key: SecretStr = SecretStr("")
    ctx_mcp_url: str = ""
    ctx_alex_agent_key: SecretStr = SecretStr("")
    ctx_jordan_agent_key: SecretStr = SecretStr("")
    shop_cache_enabled: bool = False
    shop_cache_distance: float = Field(default=0.2, ge=0, le=2, allow_inf_nan=False)
    shop_cache_ttl: int = Field(default=3600, ge=1, le=604800)
    openrouter_api_key: SecretStr = SecretStr("")
    shop_jev_model: str = "typesafe/jev-1.13"
    shop_jev_confidence: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    shop_jev_timeout: float = Field(default=5, gt=0, le=30, allow_inf_nan=False)

    def cache_missing(self) -> list[str]:
        return ["OPENROUTER_API_KEY"] if not self.openrouter_api_key.get_secret_value() else []

    def missing(self) -> list[str]:
        values = {
            "AGENT_MEMORY_BASE_URL": self.agent_memory_base_url,
            "AGENT_MEMORY_STORE_ID": self.agent_memory_store_id,
            "AGENT_MEMORY_API_KEY": self.agent_memory_api_key.get_secret_value(),
            "OPENAI_API_KEY": self.openai_api_key.get_secret_value(),
            "CTX_MCP_URL": self.ctx_mcp_url,
            "CTX_ALEX_AGENT_KEY": self.ctx_alex_agent_key.get_secret_value(),
            "CTX_JORDAN_AGENT_KEY": self.ctx_jordan_agent_key.get_secret_value(),
        }
        return [key for key, value in values.items() if not value]
