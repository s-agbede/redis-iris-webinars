"""HTTP contract fixtures follow OpenRouter's documented Decisions API.

Sources:
https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request
https://docs.typesafe.ai/primitives/choice
https://docs.typesafe.ai/confidence
"""

import json
from copy import deepcopy

import httpx
import pytest
from pydantic import JsonValue, ValidationError

from app.shop.jev import JevDecision, JevError, JevVerifier, ReuseRequest


@pytest.fixture
def state() -> ReuseRequest:
    return ReuseRequest(
        new_question="What is a prime lens?",
        current_context={"conversation": [], "memories": []},
        cached_question="Explain prime lenses.",
        cached_answer="A prime lens has a fixed focal length.",
        cached_context={"conversation": [], "memories": []},
    )


@pytest.fixture
def response_body() -> dict[str, JsonValue]:
    # The three-way Choice confidence is (top_probability - 1/3) / (2/3).
    return {
        "answers": {
            "cache_reuse": {
                "type": "choice",
                "choice": "accept",
                "confidence": 0.97,
                "probabilities": {"accept": 0.98, "reject": 0.01, "uncertain": 0.01},
            }
        },
        "model": "typesafe/jev-1.13-20260917",
        "usage": {"input_tokens": 476, "output_tokens": 70, "cost": 0.000019992},
        "id": "gen-dec-test",
        "provider": "TypeSafe",
    }


def test_verifier_sends_a_choice_question_with_complete_state_and_reads_typed_answer(
    state: ReuseRequest, response_body: dict[str, JsonValue]
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body)

    original = deepcopy(state)
    client = httpx.Client(transport=httpx.MockTransport(respond))
    verifier = JevVerifier("test-secret", timeout_seconds=2.5, client=client)
    decision = verifier.verify(state)
    request = requests[0]
    payload = json.loads(request.content)

    assert request.method == "POST"
    assert str(request.url) == "https://openrouter.ai/api/alpha/decisions"
    assert request.headers["authorization"] == "Bearer test-secret"
    assert request.headers["content-type"] == "application/json"
    assert request.extensions["timeout"]["read"] == 2.5
    assert payload["model"] == "typesafe/jev-1.13"
    assert payload["state"] == original.model_dump(mode="json")
    assert original == state
    assert "test-secret" not in request.content.decode()
    question = payload["questions"]["cache_reuse"]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"accept", "reject", "uncertain"}
    assert decision.choice == "accept"
    assert decision.confidence == 0.97
    assert decision.probabilities == {"accept": 0.98, "reject": 0.01, "uncertain": 0.01}
    assert decision.model == "typesafe/jev-1.13-20260917"
    assert decision.input_tokens == 476
    assert decision.cost_usd == 0.000019992


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_http_failures_raise_a_safe_error(state: ReuseRequest, status: int) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, json={"error": "private-response test-secret"})
        )
    )
    with pytest.raises(JevError, match=f"HTTP {status}") as error:
        JevVerifier("test-secret", client=client).verify(state)
    assert "private-response" not in str(error.value)
    assert "test-secret" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_network_failures_raise_a_safe_error(
    state: ReuseRequest, failure: type[httpx.RequestError]
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise failure("private-response test-secret", request=request)

    client = httpx.Client(transport=httpx.MockTransport(respond))
    with pytest.raises(JevError) as error:
        JevVerifier("test-secret", client=client).verify(state)
    assert "private-response" not in str(error.value)
    assert "test-secret" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize(
    "body",
    [
        b"private-response test-secret",
        b"null",
        b"[]",
        b'"private-response test-secret"',
        b'{"answers": {}}',
        b'{"error": "private-response test-secret"}',
    ],
)
def test_invalid_response_payloads_raise_a_safe_error(state: ReuseRequest, body: bytes) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    with pytest.raises(JevError, match="invalid response") as error:
        JevVerifier("test-secret", client=client).verify(state)
    assert "private-response" not in str(error.value)
    assert "test-secret" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"type": "noul", "noul": 0.99},
        {"type": "choice", "choice": "accept"},
        {
            "type": "choice",
            "choice": "private-response test-secret",
            "confidence": 1,
            "probabilities": {"accept": 1, "reject": 0, "uncertain": 0},
        },
        {
            "choice": "accept",
            "confidence": 1,
            "probabilities": {"accept": 1, "reject": 0, "uncertain": 0},
        },
    ],
)
def test_requires_the_expected_typed_choice_answer(
    state: ReuseRequest, answer: dict[str, JsonValue]
) -> None:
    body = {"answers": {"cache_reuse": answer}}
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))
    with pytest.raises(JevError, match="invalid response") as error:
        JevVerifier("test-secret", client=client).verify(state)
    assert "private-response" not in str(error.value)
    assert "test-secret" not in str(error.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("confidence", -0.1),
        ("confidence", 1.1),
        ("confidence", "0.99"),
        ("confidence", True),
        ("confidence", float("nan")),
        ("confidence", float("inf")),
        ("probabilities", {"accept": 1}),
        ("probabilities", {"accept": 1, "reject": 0, "uncertain": 0, "other": 0}),
        ("probabilities", {"accept": 0.5, "reject": 0, "uncertain": 0}),
        ("probabilities", {"accept": 0.8, "reject": 0.8, "uncertain": 0}),
        ("probabilities", {"accept": 0.1, "reject": 0.8, "uncertain": 0.1}),
        ("probabilities", {"accept": 1.1, "reject": -0.1, "uncertain": 0}),
        ("probabilities", {"accept": "0.98", "reject": 0.01, "uncertain": 0.01}),
        ("probabilities", {"accept": True, "reject": 0, "uncertain": 0}),
        ("probabilities", {"accept": float("nan"), "reject": 0, "uncertain": 0}),
        ("probabilities", {"accept": float("inf"), "reject": 0, "uncertain": 0}),
        ("input_tokens", -1),
        ("input_tokens", True),
        ("input_tokens", 1.5),
        ("input_tokens", "476"),
        ("cost_usd", -1.0),
        ("cost_usd", float("inf")),
        ("cost_usd", True),
        ("cost_usd", "0.01"),
    ],
)
def test_decision_rejects_invalid_numbers_and_inconsistent_distributions(
    field: str, value: JsonValue
) -> None:
    payload = {
        "choice": "accept",
        "confidence": 0.97,
        "probabilities": {"accept": 0.98, "reject": 0.01, "uncertain": 0.01},
        field: value,
    }
    with pytest.raises(ValidationError):
        JevDecision.model_validate(payload)


@pytest.mark.parametrize(
    "usage",
    [{"input_tokens": -1}, {"cost": -0.01}, {"cost": "private-response test-secret"}],
)
def test_invalid_usage_is_not_published_as_measurements(
    state: ReuseRequest, response_body: dict[str, JsonValue], usage: dict[str, JsonValue]
) -> None:
    response_body["usage"] = usage
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response_body))
    )
    with pytest.raises(JevError, match="invalid response") as error:
        JevVerifier("test-secret", client=client).verify(state)
    assert "private-response" not in str(error.value)
    assert "test-secret" not in str(error.value)


def test_missing_measurements_are_not_invented(
    state: ReuseRequest, response_body: dict[str, JsonValue]
) -> None:
    del response_body["usage"]
    del response_body["model"]
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response_body))
    )
    decision = JevVerifier("test-secret", client=client).verify(state)
    assert decision.input_tokens is None
    assert decision.cost_usd is None
    assert decision.model is None


@pytest.mark.parametrize("choice", ["accept", "reject", "uncertain"])
def test_adapter_preserves_valid_low_confidence_answers_for_application_policy(
    state: ReuseRequest, choice: str
) -> None:
    body = {
        "answers": {
            "cache_reuse": {
                "type": "choice",
                "choice": choice,
                "confidence": 0,
                "probabilities": {"accept": 0.333333, "reject": 0.333333, "uncertain": 0.333333},
            }
        }
    }
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))
    decision = JevVerifier("test-secret", client=client).verify(state)
    assert decision.choice == choice
    assert decision.confidence == 0


def test_close_releases_the_http_client() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    verifier = JevVerifier("test-secret", client=client)
    verifier.close()
    assert client.is_closed
