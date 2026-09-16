# Production demo planning notes

Updated 2026-09-16. Agreed planning scope; implementation tasks below remain open.
This document records the design discussion, not completed features.

## Agreed three failure points

1. **Freshness:** a camera was added while indexing was paused; search cannot find it.
2. **Performance:** search works for one shopper but slows or fails under concurrent demand.
3. **Safe deployment:** rebuilding the serving index interrupts search or exposes incomplete data.

The third topic replaces embedding-failure fallback. Fallback is deferred, not a
required fourth demonstration. Keep the initial retrieval-comparison demo separate
from this production-pattern segment, within the same calm camera-shop application.

## 1. Freshness: catalogue changes while synchronization is unavailable

Lead with adding a product while synchronization is paused, then resume and show
that the queued change makes it searchable without submitting the product again.

### Agreed demonstration

1. Pause the synchronization worker; continue accepting and recording changes.
2. Add a clearly identified demo camera through a small product-entry UI.
3. Show that its live product record/page exists, but the specific listing has no
   indexed passages and is absent from passage-based search.
4. Resume synchronization. The worker processes the queued event, creates passages
   and local embeddings, writes them to Redis, and acknowledges success.
5. Repeat the query and show the new listing in search results.
6. Follow with deletion of that listing to demonstrate stale indexed data and cleanup.

This demonstrates durable backlog recovery, not dead-letter handling. Recovering
an event read before a worker crash additionally requires reclaiming unacknowledged
work. Dead-letter policy is a later design choice, not an agreed live scenario.

### Required changes

- [ ] Read current product data from Redis rather than the bundled startup snapshot.
  Bundled files remain the initial seed and explicit reset source.
- [ ] Add a small product form (proposed fields: title, brand, colour, description,
  features; generated product ID) and add/delete operations.
- [ ] On product writes, atomically save/delete the product and append a change event
  to a Redis Stream in the current standalone deployment.
- [ ] Implement a consumer-group worker with pause/resume controls, acknowledgement
  after successful indexing, safe retries, and recovery of abandoned pending work.
- [ ] Track passage keys per product; synchronize creations, replacements and deletions.
  Prevent stale/replayed work from resurrecting deleted products. Design versioning
  and event ordering before implementation.
- [ ] Refresh catalogue counts, product detail reads, and autocomplete consistently.
- [ ] Show actual product existence, indexed passage count, synchronization state, and
  outstanding work. Distinguish unread events from delivered/unacknowledged events.
- [ ] Keep presenter controls small and separate from the calm search experience.
- [ ] Provide an explicit reset/restore action scoped to demo-created records.
- [ ] Use existing Redis keys by default; an isolated copy is not architecturally required.

### Deletion demonstration design to finalize

An explicitly labelled indexed-data view may show a real stale product using
stored search-record fields; opening it checks the live catalogue and reports
unavailability. Then show live product validation hiding orphan candidates and
synchronization removing them. Never fabricate stale results in the frontend.
Product lookup must not crash on orphan candidates. Basic title search needs an
explicit live-catalogue behavior; it is not passage-index search.

### Verification

Real Redis integration checks for paused addition, resume without resubmission,
search visibility, deletion cleanup, retry idempotency, worker recovery, and reset.
Verify every method's result by product ID, since similar listings may still match.
Manual Redis Insight writes do not enqueue application events; reconciliation of
out-of-band changes is a separate concern.

## 2. Performance: does search respond when everyone arrives?

### Demonstration

1. Establish a single-request baseline on the actual hybrid search path.
2. Start bounded concurrent traffic using a fixed mix of queries and filters.
3. Continue searching interactively while measuring the same background workload.
4. Identify the bottleneck, implement an appropriate improvement, and compare the
   same workload before and after. Do not manufacture a predetermined speedup.

### Tasks

- [ ] Add a single-method `/api/search` endpoint using existing query builders,
  filters and product handling. Preserve `/api/compare` for teaching retrieval.
- [ ] Instrument embedding, Redis retrieval, product fetching, total backend time,
  and queue wait where a queue exists.
- [ ] Build a separate-process traffic runner with fixed query mix, configurable
  concurrency, bounded duration, request deadlines, and Start/Stop controls.
- [ ] Record client-observed end-to-end latency, including failures/timeouts;
  report p95, completed searches/sec, error/rejection counts, sample count and duration.
- [ ] Add a compact presenter panel showing actual measurements and workload settings.
- [ ] Run the baseline and identify the limiting stage before choosing optimization.
- [ ] Apply only the measured remedy: bounded embedding concurrency/queue,
  model-versioned query-embedding cache, index strategy change, or admission control.
  These are alternatives to evaluate, not a commitment to implement all of them.
- [ ] Repeat the same workload and relevance checks. Report rejected work explicitly;
  lower successful-request latency alone does not establish improvement.
- [ ] Verify traffic stops cleanly and controls cannot start unbounded overlapping runs.

Local results reflect shared CPU between the generator, model, Redis and app; do not
claim production capacity from the laptop run. Browser cancellation alone does not
prove backend work has stopped. Keep dependency fault injection out of this segment.

## 3. Safe deployment: can we rebuild search while the shop stays open?

Current `seed/load.py` uses `index.create(overwrite=True, drop=True)` before loading
passages. Retain seeding as an explicit setup operation; introduce a separate live
rebuild path that does not drop the serving index.

### Demonstration

1. Search against serving index v1.
2. Start building v2 in the background; keep searching against v1 while it builds.
3. Display real build progress and run completeness and relevance checks on v2.
4. Catch up catalogue changes made during the build, then switch the serving alias.
5. Search against v2 and show the active version.
6. Demonstrate rollback to v1 while it is still retained and current enough to serve.

Use the same embedding model for the first version of this demonstration. This
teaches safe index replacement without claiming to demonstrate a model migration.

### Tasks

- [ ] Introduce a stable serving alias and explicit versioned index names.
- [ ] Give each version its own passage-key prefix. Separate index names alone are
  insufficient: shared document keys would let building or deleting v2 affect v1.
- [ ] Route queries through the alias; adapt startup identity/count verification
  and runtime metadata so the reported version matches the index actually queried.
- [ ] Build a replacement from the live Redis catalogue, preserving the serving index.
- [ ] Define a catalogue version/event watermark and replay strategy so changes
  during the scan, including deletions, cannot be lost or resurrected by older writes.
- [ ] Keep v1 and v2 synchronized during the cutover/rollback window, with per-target
  processing checkpoints. A single shared consumer group must not divide events
  between versions when both need every change.
- [ ] Verify index readiness, expected passage coverage, indexing failures and
  relevance evals before enabling switch. Validate against a defined catalogue
  version, not a count that is changing underneath the check.
- [ ] Switch the serving alias with `FT.ALIASUPDATE` after readiness and catch-up;
  define how writes around cutover are fenced/coordinated rather than assuming the
  alias command alone makes the entire migration consistent.
- [ ] Retain the previous version for rollback; block rollback if its state is stale
  or incompatible. Delete only retired version keys after the retention window.
- [ ] Add presenter controls: Build replacement, Validate, Switch, Roll back;
  show active version, build progress, catch-up status and validation outcome.
- [ ] Verify uninterrupted search during building, failed-build isolation, failed
  validation blocking cutover, concurrent add/delete catch-up, switch and rollback.
- [ ] Provide an explicit cleanup/reset action for experiment-created index versions.

For a future embedding-model migration, switch query-model configuration and index
version consistently; an index alias alone does not ensure embedding compatibility.
Plan temporary storage and compute for both versions; do not promise free rebuilds.

## Delivery order and scope

1. Finish freshness first: live catalogue reads, product form, durable change events,
   worker, presenter controls and real Redis verification.
2. Add a true single-hybrid request path and traffic measurements; select the
   performance improvement from the baseline evidence.
3. Reuse the change pipeline for versioned rebuilds, validation, cutover and rollback.
4. Rehearse both webinar demo segments with deterministic reset steps and timing.

Keep existing user changes intact. No external catalogue service, new embedding
provider or separate Redis deployment is required for the agreed initial scope.
Detailed concurrency/cutover choices must be resolved before implementation.

## Production references

- [Algolia ecommerce indexing and temporary-index replacement](https://www.algolia.com/doc/integration/magento-2/how-it-works/indexing)
- [Redis FT.ALIASUPDATE](https://redis.io/docs/latest/commands/ft.aliasupdate/)
- [Vespa model-change lifecycle and costs](https://blog.vespa.ai/tailoring-frozen-embeddings-with-vespa/)
- [Vespa query degradation under time budgets](https://docs.vespa.ai/en/performance/graceful-degradation.html)

These document operational patterns, not a ranking of incident frequency.

## Implementation delivered — 16 September 2026

The three demos are implemented. See [the presenter runbook](production-demo-runbook.md)
for exact steps, measured results, reset instructions and current limits.
Queries pin the registry-resolved index once per comparison; the serving alias and
registry switch together. Retained versions share one atomic write/acknowledgment
checkpoint rather than independent consumers. Performance optimization is a bounded
exact-query embedding cache, with live result retrieval on every request.
The checklists above record the original design scope; the runbook describes the
implemented behaviour and explicitly calls out scale work beyond this local demo.
