# Production patterns: presenter runbook

Keep the comparison demo first. Then open one production section at a time.
Open **Manage shop** from the header (`/?view=manage`) for production controls.
The customer search page (`/?view=compare`) keeps only filters and comparison
settings under Advanced. Product Search buttons open Hybrid results in a new tab.
Use one local backend process, bound to `127.0.0.1`; these are presenter controls.

## 1. Freshness — “We added a camera. Why can't customers find it?”

1. Open **Production lab**.
2. Click **Pause indexing**.
3. Add the prefilled fictional Aurora camera. You can change its name first.
4. Point to **Source: exists**, **0 passages**, and the unread event count.
5. Use the camera's **Search** button. It selects Hybrid and clears filters.
   The new camera is absent because its searchable passages do not exist yet.
6. Click **Resume indexing**. Wait for unread/pending/failed to reach zero and
   passages to appear. Search again: the camera is now returned.
7. Explain: the product and change event were saved in one Redis transaction.
   Pausing stops consumption, not event recording. The worker reads current source
   state, writes deterministic passage keys, then acknowledges the event. Retried
   delivery does not create duplicate passages. This is backlog recovery, not a DLQ.

Optional deletion follow-up: pause and delete the demo camera. Normal search
continues to hide the deleted product. Use Redis Insight to inspect its remaining
passages, then resume synchronization and verify those passages are removed.
**Reset demo** cleans presenter-created products and their history through the
same queue, then resumes synchronization.

Source hydration prevents displaying a deleted product. It cannot make a newly
added product discoverable: that requires index synchronization. Filtering stale
hits can also leave fewer than the requested number of results.

If a change fails three processing attempts, it moves to the failed stream and
the original event is acknowledged. Unread and pending can therefore be zero
while failed changes remain. Inspect **Failed changes**, fix the cause, and click
**Retry** to enqueue the product's current state with a fresh retry budget.
Resuming indexing alone does not retry failed-stream entries. Unresolved failures
block deployment validation and cutover.

## 2. Performance — “It works for me. What happens when everyone arrives?”

1. Open **Performance details**, set 1 concurrent request and 5 seconds. Start.
2. Set 10 concurrent requests; rerun and observe p95, throughput and errors.
3. Leave concurrency/duration unchanged. Select **Reuse repeated queries** and run.
4. Compare the current and previous completed runs. Explain the one change:
   a bounded, per-process cache reuses exact query embeddings, keyed by model and
   revision. Every request still searches Redis and reads live product records.
5. Use **Stop** if needed. An interrupted run discards partial metrics explicitly.

The workload rotates four queries, two with brand filters, requesting six results
from `/api/search`. This endpoint runs Hybrid alone; the comparison page runs
multiple retrieval methods and is a different workload. The client is a separate
process on the same computer. It is closed-loop: each worker waits for a response
before its next request. A request has a 3-second deadline.

Local observations on 16 September 2026, full 2,317-product / 8,472-passage bundle:

| Run | Concurrent | Cache | p95 HTTP | Completed/sec | Errors / timeouts |
| --- | ---: | --- | ---: | ---: | ---: |
| Initial baseline | 1 | Off | 12.8 ms | 94.9 | 0 / 0 |
| Matched comparison | 10 | Off | 90.5 ms | 163.2 | 0 / 0 |
| Matched comparison | 10 | On | 83.1 ms | 177.3 | 0 / 0 |

These are single short observations, not production capacity estimates. Cache
benefits depend on repeated queries; unique queries still need embedding. The
cache holds 256 vectors, clears on process restart, and does not coalesce
simultaneous cold misses. Do not claim this alone solves overload. Real capacity
planning needs representative query distributions, longer runs, separate load
hosts, resource monitoring, arrival-rate tests and an explicit latency target.

## 3. Safe deployment — “Can we rebuild search while the shop stays open?”

1. Open **Safe deployment**, click **Build replacement**. Continue searching Sony
   ZV-E10 while the product progress counter advances. Build time depends on the
   machine; start the build before explaining the pattern.
2. Click **Validate replacement** when ready. Expand the check summary if useful.
   It checks passage IDs, current source fields, vector dimensions, searchable
   count, sample reachability and seven unfiltered reviewed queries in both text
   and hybrid (known relevant product in the top three).
3. Click **Switch index**. Show the serving name changing; search Sony again.
4. Click **Roll back**. Show the original serving name and search again.
5. Click **Clean up alternate** after rollback for a repeatable starting state.

Each version owns a separate passage-key prefix. The Stream worker writes all
retained targets and acknowledges only after their writes commit together.
Product revision checks prevent stale build work from overwriting a newer change.
Cutover requires an empty backlog and validation at the current catalogue revision.
A catalogue change after validation requires validation again. The retained index
must also have its expected searchable count before promotion or rollback.

Redis `FT.ALIASUPDATE` and the serving registry update commit together. The app
resolves the registry once per comparison and pins its concrete index version so
that the methods in one comparison use the same version across a cutover.
If cleanup removes that version during a request, the whole comparison retries
once against the current serving target.
The alias is available for direct Redis inspection as `camera_serving`.

This demo retains the same embedding model and reuses unchanged passage vectors.
It does not demonstrate a model migration. A real migration must coordinate query
embeddings, index schema and model version, and budget temporary storage/compute.
The full catalogue rehearsal passed all 20 checks and served search during the
build, switch and rollback. If a build is interrupted, restart marks it failed;
clean up the candidate and rebuild while the original continues serving.

## Code map

- `app/product_store.py`: live products, revisions and transactional Stream events.
- `app/sync.py`: pause, replay, passage replacement and acknowledgment.
- `app/embedding_cache.py`: exact-query vector reuse with bounded memory.
- `app/traffic.py` / `scripts/search_load.py`: bounded subprocess and HTTP metrics.
- `app/deployment.py`: version lifecycle, validation, promotion and cleanup.
- `web/src/ProductionLab.tsx`, `TrafficLab.tsx`, `DeploymentLab.tsx`: collapsed controls.

## Verification and boundaries

Run `TEST_REDIS_URL=redis://localhost:6381/0 uv run pytest -q`, `uv run ruff check
app scripts tests`, `uv run mypy app scripts`, `node --test web/src/*.test.mjs`
and `cd web && npm run build`. The live catalogue test expects the original
bundle, so reset demo products first. Integration tests use unique namespaces.

Tests cover paused addition, unacknowledged-event recovery, duplicate delivery,
change during embedding, stale deletion, reset isolation, incomplete candidate
rejection, validation invalidation, rollback completeness, cache reuse and traffic
accounting/cancellation. Checks include Ruff, mypy, frontend logic tests and the
frontend production build. Browser rehearsal exercised the real
add/resume/delete/stale/reset flow and traffic Start/Stop controls. The full
catalogue build, 20 validation checks, switch and rollback passed through HTTP.

Keep seeding as bootstrap, not a live deployment operation. Use the replacement
workflow for the running shop. This implementation deliberately uses one backend
process, local controls, a small catalogue and same-model versions. The Stream
needs a retention/reconciliation policy for long-running deployments. Exhausted
changes stay in the failed stream until explicitly retried. Per-product passage lookup still uses
SCAN, which should become explicit passage membership at larger catalogue sizes.
These are working demonstrations of the patterns, not a packaged production service.

## Query interpretation

The search UI opts into the backend's `interpret_brand` rule. A single leading
brand from the bundled catalogue becomes a filter on every search method. Manual
brand selections win. Compatibility, negation, alternatives and multiple-brand
requests are left unfiltered. The original text remains intact for model matching
and evidence. This is deliberately conservative and does not infer specs or price.
The removable “From your query” chip disables inference for that query in the tab.
API callers opt in with `interpret_brand: true`; evals and traffic retain their
explicit filter configuration. Rules live in `app/query_understanding.py`.
