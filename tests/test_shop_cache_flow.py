from time import time
from typing import Literal

import pytest

from app.shop.cache import CacheError
from app.shop.jev import JevDecision, JevError, ReuseRequest
from app.shop.models import (
    CacheCandidate,
    CacheEntry,
    MemoryMode,
    ModelAnswer,
    ShoppingTools,
    TurnContext,
)
from app.shop.prompts import SHOP_INSTRUCTIONS
from app.shop.reuse import AnswerReuse
from tests.test_shop import Model, make_shop


class InMemoryCache:
    def __init__(self) -> None:
        self.entries: list[CacheEntry] = []
        self.lookups: list[tuple[str, str, MemoryMode, str]] = []
        self.fail = False

    def lookup(
        self, question: str, owner: str, mode: MemoryMode, version: str
    ) -> CacheCandidate | None:
        self.lookups.append((question, owner, mode, version))
        if self.fail:
            raise CacheError("Cache unavailable.")
        entries = [
            e
            for e in self.entries
            if e.version == version
            and (e.scope == "shared" or (e.scope == owner and e.mode == mode))
        ]
        return CacheCandidate(entry=entries[-1], distance=0.05) if entries else None

    def store(self, entry: CacheEntry) -> str:
        self.entries.append(entry)
        return entry.entry_id

    def remove(self, entry_id: str, owner: str) -> bool:
        found = any(e.entry_id == entry_id and e.scope == owner for e in self.entries)
        self.entries = [
            e for e in self.entries if not (e.entry_id == entry_id and e.scope == owner)
        ]
        return found

    def clear(self, owner: str) -> int:
        count = len(self.entries)
        self.entries = [e for e in self.entries if e.scope != owner]
        return count - len(self.entries)


class StubVerifier:
    def __init__(
        self, choice: Literal["accept", "reject", "uncertain"] = "accept", confidence: float = 0.9
    ) -> None:
        self.choice, self.confidence = choice, confidence
        self.calls: list[ReuseRequest] = []
        self.fail = False

    def verify(self, request: ReuseRequest) -> JevDecision:
        self.calls.append(request)
        if self.fail:
            raise JevError("Jev unavailable.")
        probabilities = {key: 0.025 for key in ("accept", "reject", "uncertain")}
        probabilities[self.choice] = 0.95
        return JevDecision(
            choice=self.choice, confidence=self.confidence, probabilities=probabilities
        )


class NominatingModel(Model):
    def __init__(
        self,
        scope: Literal["shopper", "shared"] = "shopper",
        invalid: bool = False,
        remote: bool = False,
    ) -> None:
        super().__init__()
        self.scope, self.invalid, self.remote = scope, invalid, remote
        self.calls = 0

    def answer(self, context: TurnContext, tools: ShoppingTools) -> ModelAnswer:
        self.calls += 1
        assert "store_in_cache" in [t.name for t in tools.definitions()]
        result = tools.call("store_in_cache", {"scope": self.scope})
        assert result["status"] == "nominated"
        if self.remote:
            tools.call("get_product_by_id", {"id": "fixture"})
        return ModelAnswer(
            text="Aperture controls the lens opening.",
            product_ids=["invented"] if self.invalid else [],
        )


def make_cached_shop(model=None, **verifier_options):
    model = model or NominatingModel()
    shop, memory, store, _ = make_shop(model)
    cache, verifier = InMemoryCache(), StubVerifier(**verifier_options)
    shop.reuse = AnswerReuse(cache, verifier, distance=0.2, confidence=0.5, ttl=600)
    return shop, memory, store, model, cache, verifier


def test_hit_skips_model_preserves_history_and_marks_original_evidence():
    shop, memory, store, model, cache, verifier = make_cached_shop()
    first = shop.new_session("alex")
    original = shop.turn("alex", first.session_id, "Explain aperture", "both")
    assert original.inspector.cache.store_status == "stored"
    second = shop.new_session("alex")
    hit = shop.turn("alex", second.session_id, "What does aperture mean?", "both")
    assert hit.assistant == original.assistant
    assert hit.inspector.cache.status == "hit"
    assert model.calls == 1
    assert hit.inspector.answer_request is None
    assert hit.inspector.tool_calls == []
    assert hit.inspector.model_ms == 0
    assert memory.events[second.session_id][-1].text == hit.assistant
    assert store.sessions[second.session_id].turns[-1].inspector.cache.status == "hit"
    assert verifier.calls[0].new_question == "What does aperture mean?"


@pytest.mark.parametrize(
    "choice,confidence", [("reject", 0.9), ("uncertain", 0.9), ("accept", 0.2)]
)
def test_rejected_or_low_confidence_candidate_generates(choice, confidence):
    shop, _, _, model, _, verifier = make_cached_shop()
    session = shop.new_session("alex")
    shop.turn("alex", session.session_id, "Explain aperture", "both")
    verifier.choice, verifier.confidence = choice, confidence
    turn = shop.turn("alex", session.session_id, "Explain aperture for video", "both")
    assert turn.inspector.cache.status == "rejected"
    assert model.calls == 2


@pytest.mark.parametrize("failing", ["cache", "verifier"])
def test_optional_cache_failures_fall_back_visibly(failing):
    shop, _, _, model, cache, verifier = make_cached_shop()
    session = shop.new_session("alex")
    shop.turn("alex", session.session_id, "Explain aperture", "both")
    (cache if failing == "cache" else verifier).fail = True
    turn = shop.turn("alex", session.session_id, "Explain aperture again", "both")
    assert turn.inspector.cache.status == "error"
    assert model.calls == 2


def test_jordan_and_different_memory_mode_do_not_find_alex_private_answer():
    shop, _, _, model, _, verifier = make_cached_shop()
    alex, jordan = shop.new_session("alex"), shop.new_session("jordan")
    shop.turn("alex", alex.session_id, "Explain aperture", "both")
    assert (
        shop.turn("jordan", jordan.session_id, "Explain aperture", "both").inspector.cache.status
        == "miss"
    )
    assert (
        shop.turn("alex", alex.session_id, "Explain aperture", "none").inspector.cache.status
        == "miss"
    )
    assert verifier.calls == []


def test_invalid_answer_is_never_stored():
    shop, _, _, _, cache, _ = make_cached_shop(NominatingModel(invalid=True))
    session = shop.new_session("alex")
    with pytest.raises(Exception, match="catalogue"):
        shop.turn("alex", session.session_id, "Explain aperture", "both")
    assert cache.entries == []


def test_remote_tool_turn_is_not_admitted():
    shop, _, _, _, cache, _ = make_cached_shop(NominatingModel(remote=True))
    session = shop.new_session("alex")
    result = shop.turn("alex", session.session_id, "Explain aperture", "both")
    assert result.inspector.cache.store_status == "skipped"
    assert cache.entries == []


def test_live_delivery_request_bypasses_lookup():
    shop, _, _, _, cache, _ = make_cached_shop()
    session = shop.new_session("alex")
    turn = shop.turn("alex", session.session_id, "Where is my delivery?", "both")
    assert turn.inspector.cache.status == "bypass"
    assert cache.lookups == []
    assert cache.entries == []


def test_explicit_bypass_neither_reads_nor_stores():
    shop, _, _, _, cache, _ = make_cached_shop()
    session = shop.new_session("alex")
    # Use ordinary model because cache tools are deliberately unavailable on bypass.
    shop.model = Model()
    turn = shop.turn("alex", session.session_id, "Hello", "both", use_cache=False)
    assert turn.inspector.cache.status == "bypass"
    assert cache.lookups == [] and cache.entries == []


def test_shared_nomination_with_memory_is_downgraded_to_private():
    from app.shop.models import Onboarding

    shop, _, _, _, cache, _ = make_cached_shop(NominatingModel(scope="shared"))
    shop.onboard("alex", Onboarding(preferences="compact"))
    session = shop.new_session("alex")
    shop.turn("alex", session.session_id, "Explain aperture", "both")
    assert cache.entries[0].scope == session.owner_id


def test_standalone_general_advice_can_be_shared_without_owner_context():
    shop, _, _, _, cache, _ = make_cached_shop(NominatingModel(scope="shared"))
    session = shop.new_session("alex")
    shop.turn("alex", session.session_id, "Explain aperture", "none")
    assert cache.entries[0].scope == "shared"
    assert cache.entries[0].context.shopper_id is None


def test_no_cache_write_after_session_save_failure():
    shop, _, store, _, cache, _ = make_cached_shop()
    session = shop.new_session("alex")

    def broken_save(session):
        raise RuntimeError("session failed")

    store.save = broken_save
    with pytest.raises(RuntimeError, match="session failed"):
        shop.turn("alex", session.session_id, "Explain aperture", "both")
    assert cache.entries == []


def test_changed_supporting_catalogue_record_rejects_reuse():
    from app.shop.models import TurnContext
    from app.shop.reuse import cache_version

    shop, _, _, model, cache, verifier = make_cached_shop()
    session = shop.new_session("alex")
    context = TurnContext(message="Compare two lenses", mode="both", shopper_id="alex")
    card = shop.card(shop.product("a"))
    context.products = [card.model_copy(update={"description": "Old listing"})]
    cache.entries.append(
        CacheEntry(
            scope=session.owner_id,
            mode="both",
            version=cache_version(shop.cache_configuration + SHOP_INSTRUCTIONS, context),
            question=context.message,
            answer="The first lens is better.",
            products=[],
            context=context,
            created_at=time(),
            expires_at=time() + 100,
        )
    )
    turn = shop.turn("alex", session.session_id, "Compare two lenses", "both")
    assert turn.inspector.cache.status == "rejected"
    assert "listing" in turn.inspector.cache.reason
    assert verifier.calls == []
    assert model.calls == 1


def test_answer_expiring_during_verification_is_not_served(monkeypatch):
    shop, _, _, model, _, verifier = make_cached_shop()
    session = shop.new_session("alex")
    shop.turn("alex", session.session_id, "Explain aperture", "both")
    clock = [time()]
    monkeypatch.setattr("app.shop.reuse.time", lambda: clock[0])
    original = verifier.verify

    def slow_verify(state):
        result = original(state)
        clock[0] += 601
        return result

    verifier.verify = slow_verify
    turn = shop.turn("alex", session.session_id, "Explain aperture again", "both")
    assert turn.inspector.cache.status == "rejected"
    assert "expired" in turn.inspector.cache.reason
    assert model.calls == 2


def test_cache_trace_save_failure_does_not_lose_already_saved_reply():
    from redis.exceptions import RedisError

    shop, memory, store, _, cache, _ = make_cached_shop()
    session = shop.new_session("alex")
    original = store.save
    calls = 0

    def save_once(session):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RedisError("optional trace persistence failed")
        original(session)

    store.save = save_once
    turn = shop.turn("alex", session.session_id, "Explain aperture", "both")
    assert store.sessions[session.session_id].turns[-1].assistant == turn.assistant
    assert memory.events[session.session_id][-1].text == turn.assistant
    assert cache.entries[0].answer == turn.assistant
    assert "evidence could not be saved" in turn.inspector.cache.store_reason
