"""Answer-cache admission and applicability checks for the teaching adviser."""

import hashlib
import json
import re
from collections.abc import Callable
from time import perf_counter, time
from typing import Literal, Protocol

from app.shop.cache import AnswerCache, CacheError
from app.shop.jev import JevDecision, JevError, ReuseRequest
from app.shop.models import (
    CacheCandidate,
    CacheEntry,
    CacheTrace,
    ModelAnswer,
    ProductCard,
    ReuseResult,
    TurnContext,
)

LIVE_REQUEST = re.compile(
    r"\b(deliver\w*|shipment\w*|tracking|arriv\w*|parcel\w*|order\w*|purchase\w*|"
    r"bought|stock|price\w*|refund\w*)\b",
    re.I,
)
PUBLIC_QUESTION = re.compile(
    r"(?:explain|what is|what does) (?:aperture|shutter speed|iso|depth of field|"
    r"focal length|white balance)(?: mean| do)?[?.!]*",
    re.I,
)


class Verifier(Protocol):
    def verify(self, request: ReuseRequest) -> JevDecision: ...


def cache_version(instructions: str, context: TurnContext) -> str:
    """Only application rules/guidance, never a whole-user memory fingerprint."""
    value = json.dumps(
        {
            "rules": instructions,
            "guidance": [item.model_dump(mode="json") for item in context.guidance],
        },
        sort_keys=True,
    )
    return hashlib.sha256(value.encode()).hexdigest()[:24]


class AnswerReuse:
    def __init__(
        self,
        cache: AnswerCache,
        verifier: Verifier,
        *,
        distance: float,
        confidence: float,
        ttl: int,
    ) -> None:
        self.cache, self.verifier = cache, verifier
        self.distance, self.confidence, self.ttl = distance, confidence, ttl

    def find(
        self,
        context: TurnContext,
        owner: str,
        version: str,
        product: Callable[[str], ProductCard | None],
    ) -> ReuseResult:
        """A candidate must pass scope, evidence and applicability checks, in that order."""
        trace = CacheTrace(
            status="miss",
            reason="No candidate within the allowed scope.",
            distance_threshold=self.distance,
            confidence_threshold=self.confidence,
        )
        if LIVE_REQUEST.search(context.message):
            trace.status, trace.reason = (
                "bypass",
                "Live order, delivery or commercial data needs retrieval.",
            )
            return ReuseResult(trace=trace)
        candidate = self._lookup_candidate(context, owner, version, trace)
        if candidate is None:
            return ReuseResult(trace=trace)
        entry = candidate.entry
        if (
            entry.scope not in (owner, "shared")
            or entry.version != version
            or (entry.scope != "shared" and entry.mode != context.mode)
        ):
            trace.status, trace.reason = "error", "Cache scope validation failed."
            return ReuseResult(trace=trace)
        record_candidate(trace, candidate)
        trace.status = "rejected"
        if reason := stale_evidence_reason(entry, product):
            trace.reason = reason
            return ReuseResult(trace=trace)

        decision = self._verify_candidate(context, entry, trace)
        if decision is None:
            return ReuseResult(trace=trace)
        if decision.choice != "accept" or decision.confidence < self.confidence:
            trace.reason = "Jev did not approve unchanged reuse at the configured confidence."
            return ReuseResult(trace=trace)
        if entry.expires_at <= time():
            trace.reason = "The cached answer expired during verification."
            return ReuseResult(trace=trace)
        trace.status, trace.reason = (
            "hit",
            "Jev approved answer applicability; freshness is bounded by the demo policy.",
        )
        trace.original_context = entry.context
        return ReuseResult(
            answer=ModelAnswer(
                text=entry.answer, product_ids=[p.product_id for p in entry.products]
            ),
            products=entry.products,
            trace=trace,
        )

    def save(
        self,
        context: TurnContext,
        owner: str,
        version: str,
        answer: ModelAnswer,
        products: list[ProductCard],
        scope: Literal["shopper", "shared"],
        remote_used: bool,
        trace: CacheTrace,
    ) -> None:
        if remote_used or trace.status == "bypass" or LIVE_REQUEST.search(context.message):
            trace.store_status, trace.store_reason = (
                "skipped",
                "Live or remote record answers are not cached.",
            )
            return
        public = scope == "shared" and can_share_answer(context)
        original = context.model_copy(deep=True)
        if public:
            original.shopper_id = None
        now = time()
        entry = CacheEntry(
            scope="shared" if public else owner,
            version=version,
            mode=context.mode,
            question=context.message,
            answer=answer.text,
            products=products,
            context=original,
            created_at=now,
            expires_at=now + self.ttl,
        )
        try:
            trace.stored_entry_id = self.cache.store(entry)
            trace.stored_scope = entry.scope
            trace.store_status = "stored"
            trace.store_reason = f"Final answer stored in {entry.scope} scope."
        except CacheError as exc:
            trace.store_status, trace.store_reason = "error", str(exc)

    def _lookup_candidate(
        self, context: TurnContext, owner: str, version: str, trace: CacheTrace
    ) -> CacheCandidate | None:
        started = perf_counter()
        try:
            return self.cache.lookup(context.message, owner, context.mode, version)
        except CacheError as exc:
            trace.status, trace.reason = "error", str(exc)
            return None
        finally:
            trace.lookup_ms = round((perf_counter() - started) * 1000, 2)

    def _verify_candidate(
        self, context: TurnContext, entry: CacheEntry, trace: CacheTrace
    ) -> JevDecision | None:
        request = ReuseRequest(
            new_question=context.message,
            current_context=context.model_dump(mode="json"),
            cached_question=entry.question,
            cached_answer=entry.answer,
            cached_context=entry.context.model_dump(mode="json"),
        )
        started = perf_counter()
        try:
            decision = self.verifier.verify(request)
        except JevError as exc:
            trace.status, trace.reason = "error", str(exc)
            return None
        finally:
            trace.verifier_ms = round((perf_counter() - started) * 1000, 2)
        trace.decision, trace.confidence = decision.choice, decision.confidence
        trace.probabilities = decision.probabilities
        trace.verifier_model = decision.model
        trace.verifier_input_tokens = decision.input_tokens
        trace.verifier_cost_usd = decision.cost_usd
        return decision


def stale_evidence_reason(
    entry: CacheEntry, current_product: Callable[[str], ProductCard | None]
) -> str | None:
    """Check all supplied product evidence, including products omitted from the cards."""
    if entry.expires_at <= time():
        return "The cached answer has expired."
    evidence = [*entry.products, *entry.context.products, *entry.context.previous_products]
    if any(current_product(saved.product_id) != saved for saved in evidence):
        return "A saved product is missing or its listing has changed."
    return None


def can_share_answer(context: TurnContext) -> bool:
    """Shared scope needs standalone education with no supplied personal context.

    This deliberate allowlist is a demo admission rule, not a general classifier.
    A model's nomination alone cannot make a personalised answer public.
    """
    return (
        PUBLIC_QUESTION.fullmatch(context.message.strip()) is not None
        and not context.session.events
        and not context.session.summary
        and not context.memories
        and not context.previous_products
        and not context.products
        and not context.purchases
        and not context.guidance
    )


def record_candidate(trace: CacheTrace, candidate: CacheCandidate) -> None:
    """Capture what was matched after its scope has been checked."""
    entry = candidate.entry
    trace.entry_id = entry.entry_id
    trace.scope = entry.scope
    trace.matched_question = entry.question
    trace.age_seconds = round(max(0, time() - entry.created_at), 2)
    trace.distance = candidate.distance
    trace.similarity = 1 - candidate.distance
