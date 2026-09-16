# Claude Design brief: three production search patterns

Create exactly six slides, two per pattern, continuing the attached **Retrieval at scale — Session 1: Full-text, Hybrid & Vector Search** deck. Deliver editable slides. These slides describe the planned demo; do not represent unfinished functionality or unmeasured results as completed work.

## Audience and narrative

The audience is software engineers. They have just seen full-text, vector and hybrid retrieval in Sam’s Camera Shop. Now move from relevance to three operational questions:

1. Can shoppers find catalogue changes?
2. Does search still respond under concurrent demand?
3. Can we replace an index while the shop stays open?

Keep the camera-shop scenario throughout. Each pair has a concrete failure followed by its engineering solution. Use six slides total, with no additional cover or recap. Place this segment after the initial retrieval demo and before “Three takeaways.” The presenter can alternate the slides with the corresponding live demonstrations.

## Match the attached deck

- Use the attached PDF as the visual authority. Continue its dark navy backgrounds, white text, bright lime emphasis, subtle blue-grey borders and darker teal panels. Do not switch to a white theme.
- Reference PDF pages 6–9 for cards and architecture, page 4 for visual emphasis, and page 11 for spacing and hierarchy.
- Suggested brand tokens if needed: Midnight #091A23, Dusk #163341, lime #DCFF1E, white #FFFFFF, Sky Blue #80DBFF, Redis red #FF4438. Match the supplied deck where these differ.
- Match the existing heading and body typography; Space Grotesk headings, Inter body and Space Mono technical labels are suitable if the original fonts cannot be recovered.
- Preserve the source aspect ratio, footer position, Redis logo treatment and copyright. Continue page numbering according to final placement; do not copy an existing page number.
- Use sentence-case titles, left-aligned copy, generous whitespace and a clear title/content/footer hierarchy. Avoid decorative title underlines.
- Enlarge diagrams relative to pages 8–9: each slide should communicate one idea from the back of a room. Keep roughly 30–55 visible words excluding short diagram labels. Put implementation detail in speaker notes.
- Use editable shapes, arrows and text. Simple product cards may be illustrative, but label them as such. Do not invent screenshots of completed app functionality.
- Lime marks the active path or successful state. Muted blue-grey marks waiting or inactive states. Use a small red interruption marker for failure; never rely on colour alone.
- Vary the layouts: split-state illustration, pipeline, request fan-in, measurement loop, parallel lanes, cutover sequence. Avoid six identical grids of cards.

---

## Slide 1 — Freshness: “Saved doesn’t mean searchable”

**Purpose:** Make the difference between the live catalogue and its search representation immediately visible.

**Small section label:** `01 / Freshness`

**Visible copy:**

- Title: **Saved doesn’t mean searchable**
- Left panel: **Catalogue** — “Demo camera saved”
- Centre interruption: **Indexing paused**
- Right panel: **Search index** — “New listing not indexed”
- Takeaway: **A successful product write is only the first step.**

**Visual composition:**

Use a large split-state diagram. On the left, a simple camera product card for a clearly fictitious “Demo Trail Camera.” On the right, a search box containing that exact title and an empty result outline labelled “New listing absent.” Between the panels, show a broken synchronization arrow with a pause symbol. A small “Same product ID” label connects the comparison conceptually.

Keep the example specific to this newly created listing: do not suggest that the whole catalogue or search service has disappeared. The two panels represent different data states within the application, not necessarily separate databases.

**Presenter notes:**

Pause synchronization, add a product, then show that the product record exists while its indexed passage count remains zero. Verify absence by the new product ID because other similar products might still match. This demonstrates freshness independently of relevance or query speed.

**Transition:** “How do we preserve the change until indexing can catch up?”

---

## Slide 2 — Freshness solution: “Record the change. Catch up safely.”

**Small section label:** `01 / Durable synchronization`

**Visible copy:**

- Title: **Record the change. Catch up safely.**
- Diagram: **Product change → Catalogue + change event → Worker → Search passages**
- Queue label: **Redis Stream**
- Worker label: **Clean · split · embed**
- Three short callouts: **Record atomically** / **Retry safely** / **Acknowledge after success**
- Takeaway: **Resume indexing without resubmitting the product.**

**Visual composition:**

Use a broad horizontal pipeline. Draw a single boundary around the catalogue write and stream append to show that they happen atomically in the standalone Redis deployment. Draw the Redis Stream as three small queued event tiles. Highlight one event moving through the worker into indexed passages.

Under the pipeline, use a compact two-state strip: “Paused: changes accumulate” → “Resumed: backlog drains.” Show it as a conceptual state change without fabricated counters or timings.

**Presenter notes:**

The consumer-group worker acknowledges only after indexing succeeds. Retries must be idempotent, and abandoned pending work must be recoverable. Read current product state and respect version/order rules so replaying an old event cannot resurrect a deleted product. Follow the addition demo with deletion and passage cleanup. Live product validation can hide orphan candidates while cleanup catches up.

Do not claim exactly-once delivery, immediate consistency, or zero synchronization delay. Do not imply a paused worker is the same as a crashed worker. The durable change log makes recovery possible; worker logic makes retries safe.

**Demo cue:** Resume the worker; repeat the search; show the same product ID becoming searchable.

---

## Slide 3 — Performance: “One shopper isn’t a load test”

**Small section label:** `02 / Performance under load`

**Visible copy:**

- Title: **One shopper isn’t a load test**
- Diagram: **Concurrent shoppers → FastAPI → Query embedding → Redis search → Product lookup**
- Main question: **Where does time accumulate?**
- Measurement labels: **p95 latency** / **Completed searches/sec** / **Failures + timeouts**
- Takeaway: **Measure the whole request and its stages.**

**Visual composition:**

Show multiple small shopper/request icons converging into a single large request path. Make the three backend stages readable. Beneath the path, place a simple timing strip labelled by stage, including “Queue wait, if present.” Mark it “Illustrative timing breakdown” and do not use numeric durations or proportional widths that imply measurements.

The three measurement labels sit in one compact bottom row. Do not build a fake monitoring dashboard or add invented KPI values.

**Presenter notes:**

Use the actual single-method hybrid search endpoint. The comparison endpoint executes multiple retrieval modes and is unsuitable as the normal-shopper baseline. Run a bounded workload with a fixed mix of queries and filters. Measure client-observed latency, throughput, errors, sample count and duration, then correlate them with backend embedding, retrieval and product-fetch timings. Any queue wait must be visible where a queue exists.

Local embedding, the application, Redis and the traffic generator share laptop resources. Do not assume Redis is the bottleneck or extrapolate this run to production capacity.

**Transition:** “Choose the fix from the limiting stage, then repeat exactly the same experiment.”

---

## Slide 4 — Performance solution: “Fix the measured bottleneck”

**Small section label:** `02 / Measure → improve → verify`

**Visible copy:**

- Title: **Fix the measured bottleneck**
- Main sequence: **Baseline → Locate the bottleneck → Apply one change → Repeat the workload**
- Supporting line: **Same queries. Same filters. Same concurrency.**
- Three conditional options:
  - **Repeated embedding work → Versioned query-embedding cache**
  - **Embedding saturation → Bounded concurrency**
  - **Redis search dominates → Evaluate index strategy**
- Takeaway: **Count rejected work as well as successful requests.**

**Visual composition:**

Use a large measurement-and-improvement loop, with the three conditional options in a restrained row beneath it. They are alternatives, not a required three-step solution. Highlight only the measured remedy when results become available.

Do not show a speedup chart yet. If verified measurements are supplied later, replace the option row with a small baseline/changed comparison containing p95, completed searches/sec, errors/rejections, sample count and duration. Never populate it with plausible-looking example numbers.

**Presenter notes:**

A query-embedding cache saves repeated embedding computation; it is not a semantic response cache. Its identity must include the model version and the actual embedding input. Bounded concurrency controls contention but can introduce queueing or rejections. An index strategy change requires a relevance/recall check as well as a latency check. The remedy is selected after measurement; no particular speedup is promised.

Keep search quality and filters unchanged in the comparison. Lower latency among successful requests alone is insufficient if more requests fail or are rejected.

**Demo cue:** Run the baseline, identify the stage, apply the chosen improvement and repeat the fixed workload.

---

## Slide 5 — Safe deployment: “Rebuild without closing the shop”

**Small section label:** `03 / Safe index deployment`

**Visible copy:**

- Title: **Rebuild without closing the shop**
- Main path: **Shoppers → Serving alias → Index v1**
- Parallel path: **Live catalogue → Build index v2 → Validate**
- v1 label: **Serving searches**
- v2 label: **Separate passage keys**
- Takeaway: **Build the replacement while the current index serves.**

**Visual composition:**

Use two wide parallel lanes. The top lane is the live traffic path, highlighted in lime. The lower lane is the replacement build, outlined in muted blue-grey. Keep the serving alias visually distinct from either index: it is the stable name queries use.

Draw separate passage stores beneath v1 and v2 so the audience sees that the build does not overwrite v1’s documents. The build lane ends at a validation gate, not directly at live traffic. Avoid extra infrastructure boxes.

**Presenter notes:**

The setup seed operation can rebuild destructively; a live deployment needs a separate rebuild path. Give each index version its own passage-key prefix. A second index name alone does not isolate documents if both versions use the same keys. Build from the live catalogue and track a version/event watermark so changes during the build can be replayed safely.

Use the same embedding model for this first demonstration. This is safe index replacement, not an embedding-model migration. Both versions need temporary storage and compute.

**Transition:** “Finishing the build doesn’t make it ready to serve.”

---

## Slide 6 — Safe deployment solution: “Validate. Catch up. Switch.”

**Small section label:** `03 / Controlled cutover and rollback`

**Visible copy:**

- Title: **Validate. Catch up. Switch.**
- Three gates: **Validate coverage + relevance → Catch up catalogue changes → Switch the serving alias**
- Technical label: `FT.ALIASUPDATE`
- Before: **Alias → v1**
- After: **Alias → v2**
- Return arrow: **Rollback while v1 remains current**
- Takeaway: **The alias switch is atomic; readiness needs coordination.**

**Visual composition:**

Across the top, draw the three readiness gates. Below, show a large before/after alias diagram: the lime serving arrow moves from v1 to v2. Retain v1 in muted colour with a clearly labelled rollback arrow. A fine shared change-event line reaches both versions during the rollback window, showing that the old version is retained and maintained, not merely abandoned.

Keep only the command name on-slide; do not add an unverified code listing. If the deck tool supports build animations, reveal validation, catch-up, switch and rollback in that order, but keep the static export fully understandable.

**Presenter notes:**

Validate completeness and relevance against a defined catalogue version. Replay intervening updates and deletions, and coordinate writes around cutover. The atomic alias command does not by itself guarantee that v2 contains every catalogue change. Keep per-version processing checkpoints; one shared consumer group must not distribute required events between versions when both need every event.

Keep v1 synchronized during the rollback window, and block rollback if it is stale or incompatible. Failed builds or failed validation leave the serving index in place. Retire old keys only after the retention window. For a future model migration, query-model and index configuration must move together.

**Demo cue:** Search while building, validate, catch up, switch, show the active version, then roll back to the maintained previous version.

---

## Final checks for the designer

- Exactly six slides; no more than two per pattern.
- Preserve the existing deck’s dark visual style and camera-shop context.
- Every slide has one dominant, readable diagram and one main takeaway.
- Keep visible copy concise; retain technical qualifications in speaker notes.
- No fabricated benchmark results, counters, app screenshots or completion claims.
- No claims of exactly-once processing, free rebuilds, guaranteed speedups or alias-only consistency.
- Make the three solutions memorable: **durable change events**, **measured optimization**, **validated index cutover**.
