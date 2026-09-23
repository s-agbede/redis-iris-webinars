"""Typed Redis Agent Memory boundary; extraction and reconciliation belong to Redis."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import TracebackType
from typing import Literal, Protocol, Self
from uuid import NAMESPACE_URL, uuid5

import httpx
from pydantic import BaseModel, Field, ValidationError
from redis_agent_memory import AgentMemory, errors, models


class MemoryRecord(BaseModel):
    id: str
    text: str
    memory_type: str
    owner_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MemoryEvent(BaseModel):
    event_id: str
    role: str
    text: str
    created_at: str | None = None


class MemorySession(BaseModel):
    events: list[MemoryEvent] = Field(default_factory=list)
    summary: str | None = None


class MemoryError(RuntimeError):
    """A safe error suitable for displaying without exposing service responses."""


class MemoryGateway(Protocol):
    def append_event(
        self, session_id: str, owner_id: str, role: Literal["USER", "ASSISTANT"], text: str
    ) -> str: ...

    def session(self, session_id: str) -> MemorySession: ...

    def search(self, owner_id: str, query: str, limit: int = 8) -> list[MemoryRecord]: ...

    def inventory(self, owner_id: str) -> list[MemoryRecord]: ...

    def create_facts(self, owner_id: str, facts: dict[str, str]) -> list[MemoryRecord]: ...

    def close(self) -> None: ...


@contextmanager
def _service_errors(operation: str) -> Iterator[None]:
    try:
        yield
    except errors.AgentMemoryError as exc:
        if isinstance(exc, errors.ResponseValidationError):
            detail = "returned an invalid response"
        elif exc.status_code in (401, 403):
            detail = "rejected access; check the configured store and API key"
        else:
            detail = f"request failed (HTTP {exc.status_code})"
        raise MemoryError(f"Redis Agent Memory {operation}: {detail}.") from None
    except (httpx.HTTPError, errors.NoResponseError):
        raise MemoryError(
            f"Redis Agent Memory {operation}: the service could not be reached."
        ) from None
    except ValidationError:
        raise MemoryError(f"Redis Agent Memory {operation}: invalid memory data.") from None


def _record(memory: models.MemoryRecord | models.GetLongTermMemoryResponseContent) -> MemoryRecord:
    return MemoryRecord(
        id=memory.id,
        text=memory.text,
        memory_type=memory.memory_type or "unknown",
        owner_id=memory.owner_id,
        created_at=memory.created_at.isoformat(),
        updated_at=memory.updated_at.isoformat(),
    )


class RAMClient:
    """Synchronous SDK adapter for FastAPI's threadpool-backed application service.

    Callers must use owner-specific session identifiers: the session API accepts only
    an ID, whereas long-term recall is always filtered by owner and namespace.
    """

    def __init__(
        self, endpoint: str, store_id: str, api_key: str, namespace_id: str | None = None
    ) -> None:
        self._store_id = store_id
        self._namespace_id = namespace_id
        self._namespace_ref = (
            models.NamespaceRefInput(namespace_id=namespace_id) if namespace_id else None
        )
        # Session appends lack client-supplied event IDs, so automatic retries could
        # duplicate a turn after a lost response. Retrying onboarding is safe by ID.
        self._sdk = AgentMemory(
            endpoint, store_id=store_id, api_key=api_key, retry_config=None, timeout_ms=30_000
        )
        self._closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            # The official SDK exposes cleanup through its untyped context manager.
            self._sdk.__exit__(None, None, None)  # type: ignore[no-untyped-call]
            self._closed = True

    def append_event(
        self, session_id: str, owner_id: str, role: Literal["USER", "ASSISTANT"], text: str
    ) -> str:
        with _service_errors("append event"):
            response = self._sdk.add_session_event(
                session_id=session_id,
                actor_id=owner_id if role == "USER" else "camera-shop-assistant",
                role=models.MessageRole(role),
                content=[models.Text(text=text)],
                created_at=datetime.now(UTC),
                namespace_ref=self._namespace_ref,
            )
        return response.event.event_id

    def session(self, session_id: str) -> MemorySession:
        with _service_errors("read session"):
            try:
                response = self._sdk.get_session_memory(session_id=session_id)
            except errors.AgentMemoryError as exc:
                if exc.status_code == 404:
                    return MemorySession()
                raise
        self._check_namespace(
            response.namespace_ref, legacy=bool(response.model_dump().get("namespace"))
        )
        return MemorySession(
            events=[
                MemoryEvent(
                    event_id=event.event_id,
                    role=event.role.value,
                    text="\n".join(part.text for part in event.content),
                    created_at=event.created_at.isoformat(),
                )
                for event in response.events
            ],
            summary=response.summary.text if response.summary else None,
        )

    def search(self, owner_id: str, query: str, limit: int = 8) -> list[MemoryRecord]:
        if not 1 <= limit <= 100:
            raise MemoryError("Memory search limit must be between 1 and 100.")
        response = self._search(owner_id, text=query, limit=limit)
        return self._records(owner_id, response.items)

    def inventory(self, owner_id: str) -> list[MemoryRecord]:
        """Read all filter-only pages; fail instead of claiming a partial inventory."""
        records: dict[str, MemoryRecord] = {}
        seen_tokens: set[str] = set()
        token: str | None = None
        while True:
            page = self._search(owner_id, limit=100, page_token=token)
            for record in self._records(owner_id, page.items):
                records[record.id] = record
            token = page.next_page_token
            if not token:
                return list(records.values())
            if token in seen_tokens:
                raise MemoryError("Redis Agent Memory could not provide a complete inventory.")
            seen_tokens.add(token)

    def create_facts(self, owner_id: str, facts: dict[str, str]) -> list[MemoryRecord]:
        """Create onboarding facts once; subsequent changes must be conversational.

        The bulk endpoint can report per-record failures. Read back each requested
        ID to distinguish an identical concurrent creation from a failed write.
        Existing records are not resubmitted and no service error body reaches the caller.
        """
        if not facts.keys() <= {"camera", "interests", "preferences"}:
            raise MemoryError("Onboarding supports only camera, interests, preferences.")
        if any(not text.strip() or len(text) > 50_000 for text in facts.values()):
            raise MemoryError("Onboarding facts must contain between 1 and 50000 characters.")
        planned = [
            models.CreateMemoryRecord(
                id=self._fact_id(owner_id, key),
                text=text.strip(),
                owner_id=owner_id,
                memory_type="semantic",
                namespace_ref=self._namespace_ref,
                topics=["camera-shop", "onboarding", key],
            )
            for key, text in facts.items()
        ]
        existing: dict[str, MemoryRecord] = {}
        pending: list[models.CreateMemoryRecord] = []
        for memory in planned:
            found = self._get_fact(memory.id, owner_id)
            if found is None:
                pending.append(memory)
            else:
                self._check_same_fact(found, memory.text)
                existing[memory.id] = found
        if pending:
            with _service_errors("create onboarding facts"):
                response = self._sdk.bulk_create_long_term_memories(memories=pending)
            # Inspect the entire per-record result; even a returned error may mean
            # an identical request won the race. Verification never rewrites it.
            reported = set(response.created) | {error.id for error in response.errors or []}
            if not reported <= {memory.id for memory in pending}:
                raise MemoryError("Redis Agent Memory returned an invalid onboarding result.")
            for memory in pending:
                found = self._get_fact(memory.id, owner_id)
                if found is not None:
                    self._check_same_fact(found, memory.text)
                    existing[memory.id] = found
            if len(existing) != len(planned):
                raise MemoryError(
                    f"Saved {len(existing)} of {len(planned)} onboarding facts. "
                    "Retry the same facts to finish safely."
                )
        return [existing[memory.id] for memory in planned]

    def _fact_id(self, owner_id: str, key: str) -> str:
        identity = json.dumps(["camera-shop", self._store_id, self._namespace_id, owner_id, key])
        return f"camera-shop-{uuid5(NAMESPACE_URL, identity)}"

    def _get_fact(self, memory_id: str, owner_id: str) -> MemoryRecord | None:
        with _service_errors("read onboarding fact"):
            try:
                memory = self._sdk.get_long_term_memory(memory_id=memory_id)
            except errors.AgentMemoryError as exc:
                if exc.status_code == 404:
                    return None
                raise
        self._check_scope(owner_id, memory)
        return _record(memory)

    @staticmethod
    def _check_same_fact(record: MemoryRecord, text: str) -> None:
        if record.text != text:
            raise MemoryError(
                "This onboarding fact already exists. Tell the assistant about changes in chat "
                "so Redis can reconcile the memory automatically."
            )

    def _search(
        self, owner_id: str, *, limit: int, text: str | None = None, page_token: str | None = None
    ) -> models.SearchLongTermMemoryResponseContent:
        filters = models.LongTermMemoryFilter(
            owner_id=models.OwnerIDFilter(eq=owner_id),
            namespace_ref=(
                models.NamespaceRefFilter(eq=self._namespace_id) if self._namespace_id else None
            ),
            unnamespaced=True if self._namespace_id is None else None,
        )
        with _service_errors("recall memories"):
            return self._sdk.search_long_term_memory(
                request=models.SearchLongTermMemoryRequestContent(
                    text=text,
                    filter_=filters,
                    filter_op=models.FilterConjunction.ALL,
                    limit=limit,
                    page_token=page_token,
                )
            )

    def _records(self, owner_id: str, records: list[models.MemoryRecord]) -> list[MemoryRecord]:
        for record in records:
            self._check_scope(owner_id, record)
        return [_record(record) for record in records]

    def _check_scope(
        self, owner_id: str, record: models.MemoryRecord | models.GetLongTermMemoryResponseContent
    ) -> None:
        if record.owner_id != owner_id:
            raise MemoryError(
                "Redis Agent Memory returned a record outside the requested owner scope."
            )
        self._check_namespace(
            record.namespace_ref, legacy=bool(record.model_dump().get("namespace"))
        )

    def _check_namespace(
        self, namespace: models.NamespaceRef | None, *, legacy: bool = False
    ) -> None:
        if legacy or (namespace.namespace_id if namespace else None) != self._namespace_id:
            raise MemoryError(
                "Redis Agent Memory returned data outside the configured namespace scope."
            )
