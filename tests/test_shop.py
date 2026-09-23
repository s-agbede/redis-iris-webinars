from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from app.models import CameraProduct
from app.shop.memory import MemoryEvent, MemoryRecord, MemorySession
from app.shop.models import (
    AnswerDraft,
    ModelAnswer,
    Onboarding,
    ShoppingTools,
    ShopSession,
    TurnContext,
)
from app.shop.service import SHOP_INSTRUCTIONS, ShopError, ShopService


class Store:
    def __init__(self) -> None:
        self.sessions: dict[str, ShopSession] = {}

    def save(self, session: ShopSession) -> None:
        self.sessions[session.session_id] = session.model_copy(deep=True)

    def load(self, session_id: str) -> ShopSession | None:
        return self.sessions.get(session_id)


class Memory:
    def __init__(self) -> None:
        self.events: dict[str, list[MemoryEvent]] = {}
        self.records: dict[str, list[MemoryRecord]] = {}
        self.searched: list[str] = []

    def close(self) -> None:
        pass

    def append_event(self, session_id: str, owner_id: str, role: str, text: str) -> str:
        events = self.events.setdefault(session_id, [])
        event_id = str(len(events))
        events.append(MemoryEvent(event_id=event_id, role=role, text=text))
        return event_id

    def session(self, session_id: str) -> MemorySession:
        return MemorySession(events=list(self.events.get(session_id, [])))

    def search(self, owner_id: str, query: str, limit: int = 8) -> list[MemoryRecord]:
        self.searched.append(owner_id)
        return self.inventory(owner_id)[:limit]

    def inventory(self, owner_id: str) -> list[MemoryRecord]:
        return list(self.records.get(owner_id, []))

    def create_facts(self, owner_id: str, facts: dict[str, str]) -> list[MemoryRecord]:
        result = [
            MemoryRecord(id=key, text=text, memory_type="semantic", owner_id=owner_id)
            for key, text in facts.items()
        ]
        self.records[owner_id] = result
        return result


@dataclass
class SearchPlan:
    """Scripted retrieval for service tests; the production model uses native tools."""

    query: str | None
    purchases: bool


class Model:
    def __init__(
        self, plans: list[SearchPlan] | None = None, answers: list[AnswerDraft] | None = None
    ) -> None:
        self.plans: Iterator[SearchPlan] = iter(plans or [SearchPlan(query=None, purchases=False)])
        self.answers: Iterator[AnswerDraft] = iter(
            answers or [AnswerDraft(text="What do you film?", product_ids=[])]
        )
        self.contexts: list[TurnContext] = []

    def answer(self, context: TurnContext, tools: ShoppingTools) -> ModelAnswer:
        self.contexts.append(context.model_copy(deep=True))
        retrieval = next(self.plans)
        if retrieval.query:
            tools.search_catalogue(retrieval.query)
        if retrieval.purchases:
            tools.get_purchase_history()
        self.contexts.append(context.model_copy(deep=True))
        return ModelAnswer(**next(self.answers).model_dump())


def make_shop(model: Model | None = None) -> tuple[ShopService, Memory, Store, Model]:
    from tests.test_search import service

    searcher, _, _ = service()
    memory, store = Memory(), Store()
    model = model or Model()
    return (
        ShopService(searcher, memory, store, model, owner_prefix="shop-test"),
        memory,
        store,
        model,
    )


def test_new_session_is_empty_and_does_not_copy_previous_conversation() -> None:
    shop, memory, _, _ = make_shop()
    first = shop.new_session("alex")
    memory.append_event(first.session_id, first.owner_id, "USER", "Sony camera")
    second = shop.new_session("alex")
    assert second.session_id != first.session_id
    assert second.owner_id == first.owner_id
    assert second.turns == []
    assert memory.session(second.session_id).events == []


def test_wrong_shopper_cannot_access_another_session() -> None:
    shop, memory, _, _ = make_shop()
    session = shop.new_session("alex")
    with pytest.raises(ShopError, match="belong"):
        shop.turn("jordan", session.session_id, "What did I buy?", "both")
    assert memory.searched == []


def test_onboarding_writes_separate_facts_directly_without_fabricating_events() -> None:
    shop, memory, _, _ = make_shop()
    profile = Onboarding(camera="Sony ZV-E10", interests="Walking tours", preferences="Lightweight")
    records = shop.onboard("alex", profile)
    assert len(records) == 3
    assert "Sony ZV-E10" in records[0].text
    assert len({r.id for r in records}) == 3
    assert memory.events == {}
    assert shop.memories("jordan") == []


@pytest.mark.parametrize(
    "mode,session_count,memory_count", [("none", 0, 0), ("session", 1, 0), ("both", 1, 1)]
)
def test_memory_modes_control_actual_model_context(
    mode: str, session_count: int, memory_count: int
) -> None:
    shop, memory, _, model = make_shop()
    session = shop.new_session("alex")
    memory.append_event(session.session_id, session.owner_id, "USER", "Earlier turn")
    memory.records[session.owner_id] = [
        MemoryRecord(id="kit", text="Sony", memory_type="semantic", owner_id=session.owner_id)
    ]
    result = shop.turn("alex", session.session_id, "Hello", mode)  # type: ignore[arg-type]
    context = model.contexts[0]
    assert len(context.session.events) == session_count
    assert len(context.memories) == memory_count
    assert result.inspector.context.mode == mode
    assert memory.events[session.session_id][-2].text == "Hello"
    assert memory.events[session.session_id][-1].role == "ASSISTANT"


def test_cards_only_come_from_real_catalogue_results_in_model_order() -> None:
    model = Model(
        [SearchPlan(query="canon lens", purchases=False)],
        [AnswerDraft(text="These two options.", product_ids=["b", "a"])],
    )
    shop, _, _, _ = make_shop(model)
    session = shop.new_session("alex")
    result = shop.turn("alex", session.session_id, "Find a lens", "both")
    assert [p.product_id for p in result.products] == ["b", "a"]
    assert result.products[0].title == "b lens"
    assert result.products[0].url == "/?view=product&id=b"
    assert result.inspector.context.search_query == "canon lens"


def test_invented_product_id_fails_instead_of_producing_a_fake_link() -> None:
    model = Model(answers=[AnswerDraft(text="Try this", product_ids=["made-up"])])
    shop, memory, _, _ = make_shop(model)
    session = shop.new_session("alex")
    with pytest.raises(ShopError, match="catalogue"):
        shop.turn("alex", session.session_id, "Hello", "both")
    assert all(event.role != "ASSISTANT" for event in memory.events.get(session.session_id, []))


def test_previous_cards_are_available_for_followups_only_with_session_context() -> None:
    model = Model(
        [SearchPlan(query="canon lens", purchases=False), SearchPlan(query=None, purchases=False)],
        [
            AnswerDraft(text="Options", product_ids=["a", "b"]),
            AnswerDraft(text="Second option", product_ids=["b"]),
        ],
    )
    shop, _, _, _ = make_shop(model)
    session = shop.new_session("alex")
    shop.turn("alex", session.session_id, "Find lenses", "both")
    result = shop.turn("alex", session.session_id, "The second one?", "session")
    assert result.products[0].product_id == "b"
    assert model.contexts[2].previous_products[1].product_id == "b"


def test_previous_cards_survive_a_reply_without_cards() -> None:
    model = Model(
        [
            SearchPlan(query="canon lens", purchases=False),
            SearchPlan(query=None, purchases=False),
            SearchPlan(query=None, purchases=False),
        ],
        [
            AnswerDraft(text="Two options", product_ids=["a", "b"]),
            AnswerDraft(text="You are welcome.", product_ids=[]),
            AnswerDraft(text="The second option", product_ids=["b"]),
        ],
    )
    shop, _, _, _ = make_shop(model)
    session = shop.new_session("alex")
    shop.turn("alex", session.session_id, "Find lenses", "session")
    shop.turn("alex", session.session_id, "Thanks", "session")

    result = shop.turn("alex", session.session_id, "Tell me about the second one", "session")

    assert [product.product_id for product in model.contexts[4].previous_products] == ["a", "b"]
    assert result.products[0].product_id == "b"


@pytest.mark.parametrize("retained_later_events", [0, 20])
def test_previous_cards_require_their_assistant_event_in_retained_context(
    retained_later_events: int,
) -> None:
    model = Model(
        [SearchPlan(query="canon lens", purchases=False), SearchPlan(query=None, purchases=False)],
        [
            AnswerDraft(text="Two options", product_ids=["a", "b"]),
            AnswerDraft(text="Which options do you mean?", product_ids=[]),
        ],
    )
    shop, memory, _, _ = make_shop(model)
    session = shop.new_session("alex")
    shop.turn("alex", session.session_id, "Find lenses", "session")
    if retained_later_events:
        for _ in range(retained_later_events):
            memory.append_event(session.session_id, session.owner_id, "USER", "Later discussion")
    else:
        memory.events.pop(session.session_id)

    shop.turn("alex", session.session_id, "The second one?", "session")

    assert model.contexts[2].previous_products == []


def test_purchase_evidence_is_shopper_scoped_and_historical() -> None:
    model = Model([SearchPlan(query=None, purchases=True)])
    shop, _, _, _ = make_shop(model)
    shop.searcher.catalog.products["B09BBKVMCD"] = CameraProduct(
        product_id="B09BBKVMCD", product_title="Sony ZV-E10"
    )
    session = shop.new_session("alex")
    result = shop.turn("alex", session.session_id, "What did I buy?", "both")
    assert result.inspector.context.purchases
    assert all(p.shopper_id == "alex" and p.fictional for p in result.inspector.context.purchases)
    assert result.inspector.context.purchases[0].product.product_id == "B09BBKVMCD"


def test_blank_onboarding_and_empty_messages_are_rejected() -> None:
    shop, _, _, _ = make_shop()
    session = shop.new_session("alex")
    with pytest.raises(ShopError, match="message"):
        shop.turn("alex", session.session_id, "   ", "both")
    with pytest.raises(ShopError, match="one"):
        shop.onboard("alex", Onboarding(camera="", interests="", preferences=""))


def test_each_saved_turn_keeps_its_own_exact_answer_request() -> None:
    import json

    import httpx

    from app.shop.llm import OpenAIShoppingModel

    bodies: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        output = '{"text":"Here is my answer.","product_ids":[]}'
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": output}],
                    }
                ],
            },
        )

    shop, memory, store, _ = make_shop()
    shop.model = OpenAIShoppingModel(
        "secret", "gpt-5-mini", client=httpx.Client(transport=httpx.MockTransport(respond))
    )
    session = shop.new_session("alex")
    shop.onboard("alex", Onboarding(camera="Sony ZV-E10"))
    first = shop.turn("alex", session.session_id, "What camera do I own?", "none")
    second = shop.turn("alex", session.session_id, "What camera do I own?", "both")
    assert first.inspector.answer_request is not None
    assert second.inspector.answer_request is not None
    assert first.inspector.answer_request.model_dump(mode="json") == bodies[0]
    assert second.inspector.answer_request.model_dump(mode="json") == bodies[1]
    old = json.loads(bodies[0]["input"][0]["content"])  # type: ignore[index]
    current = json.loads(bodies[1]["input"][0]["content"])  # type: ignore[index]
    for body in bodies:
        assert str(body["instructions"]).count(SHOP_INSTRUCTIONS) == 1
    assert old["guidance"] == [] and current["guidance"] == []
    assert old["session"]["events"] == [] and old["memories"] == []
    assert len(current["session"]["events"]) == 2 and len(current["memories"]) == 1
    memory.records.clear()
    saved = store.load(session.session_id)
    assert saved is not None
    restored = ShopSession.model_validate_json(saved.model_dump_json())
    assert restored.turns[0].inspector.answer_request == first.inspector.answer_request
