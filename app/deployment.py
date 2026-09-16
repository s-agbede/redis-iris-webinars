"""Versioned passage builds, revision-guarded promotion, and retained rollback."""

import json
from threading import Event, RLock, Thread
from typing import Any, cast
from uuid import uuid4

import yaml
from fastapi import APIRouter, HTTPException, Request
from redis.exceptions import RedisError, WatchError
from redisvl.index import SearchIndex

from app.catalog import make_passages
from app.failures import SyncFailures
from app.indexing import PassageEncoder, prepare_product_passages
from app.models import Passage
from app.product_store import ProductStore
from app.queries import build_hybrid_query, build_text_query
from app.settings import ROOT
from eval.models import ReviewedCase


class DeploymentManager:
    """Keep the original index and at most one alternate serving version."""

    def __init__(self, store: ProductStore, encoder: PassageEncoder, base_index: SearchIndex):
        self.store = store
        self.encoder = encoder
        self.base_index = base_index
        self.key = f"{store.settings.namespace}:deploy"
        self.alias = f"{store.settings.namespace}_serving"
        self.mutex = RLock()
        self.stopping = Event()
        self.thread: Thread | None = None
        initial: dict[str, Any] = {
            "active": {
                "name": store.settings.products_index,
                "prefix": store.settings.passage_prefix,
                "count_key": store.count_key,
            },
            "candidate": None,
            "previous": None,
            "stage": "idle",
            "completed": 0,
            "total": 0,
            "error": None,
            "validation": [],
            "validated_revision": None,
        }
        store.client.set(self.key, json.dumps(initial), nx=True)
        state = self._read()
        if state["stage"] == "building":
            state.update(stage="failed", error="Build interrupted. Reset and rebuild.")
            self._write(state)
        store.client.execute_command("FT.ALIASUPDATE", self.alias, state["active"]["name"])  # type: ignore[no-untyped-call]

    def _read(self) -> dict[str, Any]:
        return cast(
            dict[str, Any], json.loads(cast(bytes, self.store.client.get(self.key)) or b"{}")
        )

    def _write(self, state: dict[str, Any]) -> None:
        self.store.client.set(self.key, json.dumps(state))

    def status(self) -> dict[str, Any]:
        state = self._read()
        return {
            **{
                key: state.get(key)
                for key in (
                    "stage",
                    "completed",
                    "total",
                    "error",
                    "validation",
                    "validated_revision",
                )
            },
            **{
                f"{role}_index": state[role]["name"] if state.get(role) else None
                for role in ("active", "candidate", "previous")
            },
            "alias": self.alias,
        }

    def _idle(self) -> None:
        if self.thread and self.thread.is_alive():
            raise ValueError("A build is running. Wait for completion.")

    def _caught_up(self) -> None:
        if SyncFailures(self.store).count():
            raise ValueError("Resolve failed synchronization events before deployment.")
        if any(self.store.backlog().values()):
            raise ValueError("Resume synchronization and wait for the backlog to reach zero.")

    def start_build(self) -> dict[str, Any]:
        with self.mutex:
            self._idle()
            state = self._read()
            if state.get("candidate") or state.get("previous"):
                raise ValueError("Reset the retained alternate version before another build.")
            version = uuid4().hex[:12]
            target = {
                "name": f"{self.store.settings.namespace}_version_{version}",
                "prefix": f"{self.store.settings.namespace}:version:{version}",
                "count_key": f"{self.store.settings.namespace}:version-count:{version}",
            }
            schema = self.base_index.schema.to_dict()
            schema["index"].update(name=target["name"], prefix=target["prefix"])
            index = SearchIndex.from_dict(schema, redis_client=self.store.client)
            index.create(overwrite=False)
            with self.store.client.lock(self.store.lock_key, timeout=60, blocking_timeout=30):
                self.store.client.set(target["count_key"], 0)
                state.update(
                    candidate=target,
                    stage="building",
                    completed=0,
                    total=0,
                    error=None,
                    validation=[],
                    validated_revision=None,
                )
                self._write(state)
            self.thread = Thread(
                target=self._build, args=(target,), daemon=True, name="passage-deployment"
            )
            self.thread.start()
        return self.status()

    def _build(self, target: dict[str, str]) -> None:
        try:
            ids = list(self.store.all())
            state = self._read()
            state["total"] = len(ids)
            self._write(state)
            for completed, pid in enumerate(ids, 1):
                if self.stopping.is_set():
                    raise RuntimeError("Build interrupted. Reset and rebuild.")
                self._copy_product(pid, target)
                state = self._read()
                state["completed"] = completed
                self._write(state)
            state = self._read()
            state["stage"] = "ready"
            self._write(state)
        except Exception as exc:
            state = self._read()
            state.update(stage="failed", error=str(exc))
            self._write(state)

    def _copy_product(self, pid: str, target: dict[str, str]) -> None:
        client = self.store.client
        for _attempt in range(10):
            with client.pipeline() as pipe:
                pipe.watch(self.store.key(pid), self.store.revision_key(pid))  # type: ignore[no-untyped-call]
                product = self.store.get(pid)
                active = self._read()["active"]

                def reuse_embedding(
                    passage: Passage, prefix: str = active["prefix"]
                ) -> list[float] | None:
                    # Rebuilds use the same pinned model as the serving index.
                    cached = client.json().get(f"{prefix}:{passage.passage_id}")
                    if (
                        isinstance(cached, dict)
                        and cached.get("search_text") == passage.search_text
                    ):
                        return cast(list[float] | None, cached.get("embedding"))
                    return None

                records = prepare_product_passages(
                    product, self.encoder, self.store.settings, reuse_embedding=reuse_embedding
                )
                # Embedding happens outside the lease; only the small commit blocks sync.
                with client.lock(self.store.lock_key, timeout=60, blocking_timeout=30) as lease:
                    pipe.watch(self.store.lock_key)  # type: ignore[no-untyped-call]
                    old = list(
                        client.scan_iter(match=f"{target['prefix']}:us:{pid}:*", count=10000)
                    )
                    if not lease.owned():
                        raise RuntimeError("Build commit lease expired.")
                    pipe.multi()
                    if old:
                        pipe.delete(*old)
                    for record in records:
                        pipe.json().set(
                            f"{target['prefix']}:{record.passage_id}", "$", record.model_dump()
                        )
                    pipe.incrby(target["count_key"], len(records) - len(old))
                    try:
                        pipe.execute()
                        return
                    except WatchError:
                        continue
        raise RuntimeError("Product kept changing during build; reset and retry.")

    def validate(self) -> dict[str, Any]:
        with self.mutex:
            self._idle()
            state = self._read()
            target = state.get("candidate")
            if not target or state["stage"] == "failed":
                raise ValueError("Build a candidate successfully before validation.")
            self._caught_up()
            revision = int(cast(bytes, self.store.client.get(self.store.catalog_revision_key)) or 0)
            expected: dict[str, dict[str, Any]] = {}
            for product in self.store.all().values():
                for passage in make_passages(
                    product,
                    self.encoder.tokenizer,
                    self.store.settings.passage_tokens,
                    self.store.settings.passage_overlap,
                ):
                    expected[f"{target['prefix']}:{passage.passage_id}"] = passage.model_dump()
            keys = [
                key.decode()
                for key in self.store.client.scan_iter(match=f"{target['prefix']}:*", count=10000)
            ]
            coverage = set(keys) == set(expected)
            content = coverage
            for key in keys:
                raw = self.store.client.json().get(key)
                content = (
                    content
                    and isinstance(raw, dict)
                    and all(
                        raw.get(field) == value for field, value in expected.get(key, {}).items()
                    )
                )
                content = (
                    content
                    and isinstance(raw, dict)
                    and len(raw.get("embedding", [])) == self.store.settings.embedding_dims
                )
            index = SearchIndex.from_existing(target["name"], redis_client=self.store.client)
            count = int(index.info()["num_docs"])
            checks = [
                {
                    "name": "Live passage coverage",
                    "passed": coverage,
                    "detail": f"{len(keys)} stored passages; {len(expected)} expected.",
                },
                {
                    "name": "Source content and vectors",
                    "passed": bool(content),
                    "detail": "Passages match current source fields and vector dimensions.",
                },
                {
                    "name": "Search index count",
                    "passed": count == len(expected),
                    "detail": f"{count} searchable passages.",
                },
            ]
            # Small deterministic retrieval cases exercise tag filtering on the real candidate.
            for pid in sorted({row["product_id"] for row in expected.values()})[:3]:
                from redisvl.query import FilterQuery
                from redisvl.query.filter import Tag

                rows = index.query(
                    FilterQuery(
                        filter_expression=Tag("product_id") == pid,
                        return_fields=["product_id"],
                        num_results=1,
                    )
                )
                checks.append(
                    {
                        "name": f"Reachability: {pid}",
                        "passed": bool(rows),
                        "detail": "Current product is retrievable through the candidate index.",
                    }
                )
            checks.extend(
                self._quality_checks(index, {row["product_id"] for row in expected.values()})
            )
            with self.store.client.pipeline() as pipe:
                pipe.watch(self.store.catalog_revision_key)  # type: ignore[no-untyped-call]
                if int(cast(bytes, pipe.get(self.store.catalog_revision_key)) or 0) != revision:
                    raise ValueError("Catalogue changed during validation. Validate again.")
                self._caught_up()
                state.update(
                    validation=checks,
                    validated_revision=revision,
                    stage="validated" if all(c["passed"] for c in checks) else "ready",
                )
                pipe.multi()
                pipe.set(self.key, json.dumps(state))
                pipe.execute()
        return self.status()

    def _quality_checks(self, index: SearchIndex, product_ids: set[str]) -> list[dict[str, Any]]:
        """Run the existing reviewed top-three expectations against this candidate."""
        from app.search import normalize_lexical_query

        checks: list[dict[str, Any]] = []
        cases = [
            ReviewedCase.model_validate(value)
            for value in yaml.safe_load((ROOT / "eval/cases.yaml").read_text())
        ]
        for case in cases:
            targets = {pid for pid, label in case.judgements.items() if label == "relevant"}
            if case.brands or not targets.intersection(product_ids) or not case.required_modes:
                continue
            query_text = normalize_lexical_query(case.query)
            lexical = build_text_query(
                query_text, filters=None, candidate_limit=self.store.settings.candidate_limit
            )
            vector = self.encoder.embed_many([case.query])[0]
            hybrid = build_hybrid_query(
                query_text,
                vector,
                lexical=lexical,
                filters=None,
                candidate_limit=self.store.settings.candidate_limit,
            )
            for mode, query in (("text", lexical), ("hybrid", hybrid)):
                if mode not in case.required_modes:
                    continue
                if mode == "hybrid":
                    response = self.store.client.ft(index.name).hybrid_search(
                        query=hybrid.query,
                        combine_method=hybrid.combination_method,
                        post_processing=hybrid.postprocessing_config,
                        params_substitution=hybrid.params,
                    )
                    from redis.commands.search.hybrid_result import HybridResult
                    from redisvl.redis.utils import convert_bytes

                    result = cast(HybridResult, response)
                    if result.warnings:
                        raise ValueError("Candidate evaluation returned incomplete hybrid results.")
                    rows = convert_bytes(result.results)
                else:
                    rows = index.query(query)
                ranked = list(dict.fromkeys(str(row["product_id"]) for row in rows))
                limit = case.required_top_k or 3
                passed = bool(targets.intersection(ranked[:limit]))
                checks.append(
                    {
                        "name": f"Reviewed {case.case_id}/{mode}",
                        "passed": passed,
                        "detail": f"Known relevant product required in top {limit}; "
                        f"returned: {', '.join(ranked[:limit])}.",
                    }
                )
        return checks

    def _promote(self, rollback: bool) -> dict[str, Any]:
        with self.mutex:
            self._idle()
            with self.store.client.lock(  # noqa: SIM117
                self.store.lock_key, timeout=60, blocking_timeout=30
            ):
                with self.store.client.pipeline() as pipe:
                    pipe.watch(self.store.catalog_revision_key, self.key, self.store.lock_key)  # type: ignore[no-untyped-call]
                    state = self._read()
                    self._caught_up()
                    role = "previous" if rollback else "candidate"
                    target = state.get(role)
                    if not target:
                        raise ValueError(f"No {role} version is available.")
                    if not rollback and (
                        state["stage"] != "validated"
                        or state["validated_revision"]
                        != int(cast(bytes, pipe.get(self.store.catalog_revision_key)) or 0)
                    ):
                        raise ValueError(
                            "Validate the candidate against the current catalogue first."
                        )
                    info = self.base_index.info(name=target["name"])
                    expected = int(cast(bytes, self.store.client.get(target["count_key"])) or 0)
                    if int(info["num_docs"]) != expected:
                        raise ValueError("Retained index is incomplete; rebuild before promotion.")
                    state.update(
                        active=target,
                        previous=state["active"],
                        candidate=None,
                        stage="serving",
                        validated_revision=None,
                        validation=[],
                    )
                    pipe.multi()
                    pipe.execute_command("FT.ALIASUPDATE", self.alias, target["name"])  # type: ignore[no-untyped-call]
                    pipe.set(self.key, json.dumps(state))
                    pipe.execute()
        return self.status()

    def switch(self) -> dict[str, Any]:
        return self._promote(False)

    def rollback(self) -> dict[str, Any]:
        return self._promote(True)

    def reset(self) -> dict[str, Any]:
        """Remove an alternate created by this manager; never delete the seed index."""
        with self.mutex:
            self._idle()
            with self.store.client.lock(self.store.lock_key, timeout=60, blocking_timeout=30):
                state = self._read()
                targets = [state.get("candidate"), state.get("previous")]
                state.update(
                    candidate=None,
                    previous=None,
                    stage="idle",
                    completed=0,
                    total=0,
                    error=None,
                    validation=[],
                    validated_revision=None,
                )
                self._write(state)
                for target in targets:
                    if target and target["name"].startswith(
                        f"{self.store.settings.namespace}_version_"
                    ):
                        self.store.client.execute_command("FT.DROPINDEX", target["name"], "DD")  # type: ignore[no-untyped-call]
                        self.store.client.delete(target["count_key"])
        return self.status()

    def close(self) -> None:
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=30)


router = APIRouter(prefix="/api/lab/deployment", tags=["deployment"])


@router.get("")
def deployment_status(request: Request) -> dict[str, Any]:
    if request.app.state.deployment is None:
        raise HTTPException(503, "Deployment lab is not ready.")
    return cast(dict[str, Any], request.app.state.deployment.status())


@router.post("/{action}")
def deployment_action(action: str, request: Request) -> dict[str, Any]:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Deployment controls are local only.")
    if request.app.state.deployment is None:
        raise HTTPException(503, "Deployment lab is not ready.")
    manager: DeploymentManager = request.app.state.deployment
    actions = {
        "build": manager.start_build,
        "validate": manager.validate,
        "switch": manager.switch,
        "rollback": manager.rollback,
        "reset": manager.reset,
    }
    if action not in actions:
        raise HTTPException(404, "Unknown deployment action.")
    try:
        return actions[action]()
    except (ValueError, WatchError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RedisError, RuntimeError) as exc:
        raise HTTPException(503, str(exc)) from exc
