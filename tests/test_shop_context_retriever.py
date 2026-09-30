"""Runtime Context Retriever configuration contracts."""

import pytest

from app.shop.settings import ShopSettings


def adapter_module():
    from app.shop import context_retriever

    return context_retriever


def test_shared_keys_are_rejected() -> None:
    with pytest.raises(adapter_module().ContextRetrieverError, match="distinct"):
        adapter_module().ContextRetrieverClient(
            "https://retriever.example.test/mcp", {"alex": "same", "jordan": "same"}
        )


@pytest.mark.parametrize(
    "endpoint",
    ["https://retriever.example.test:foo/mcp", "http://retriever.example.test/mcp", "https://"],
)
def test_invalid_endpoint_reports_a_safe_configuration_error(endpoint: str) -> None:
    with pytest.raises(adapter_module().ContextRetrieverError, match="HTTPS.*endpoint"):
        adapter_module().ContextRetrieverClient(
            endpoint, {"alex": "test-key-alex", "jordan": "test-key-jordan"}
        )


def test_shop_readiness_requires_only_runtime_retriever_credentials() -> None:
    settings = ShopSettings(
        _env_file=None,
        agent_memory_base_url="https://memory.example.test",
        agent_memory_store_id="store",
        agent_memory_api_key="memory-secret",
        openai_api_key="model-secret",
    )
    assert set(settings.missing()) == {"CTX_MCP_URL", "CTX_ALEX_AGENT_KEY", "CTX_JORDAN_AGENT_KEY"}
    configured = ShopSettings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "ctx_mcp_url": "https://retriever.example.test/mcp",
                "ctx_alex_agent_key": "test-key-alex",
                "ctx_jordan_agent_key": "test-key-jordan",
            }
        ),
    )
    assert configured.missing() == []
    assert "test-key-alex" not in repr(configured)
