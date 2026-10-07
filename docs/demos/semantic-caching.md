# Semantic caching: a 15-minute camera-shop demo

Teach three checks: **scope**, **answer applicability**, and **freshness**. RedisVL
finds a candidate in the allowed scope; Jev decides whether its exact answer covers
the new request. A cache hit is an opportunity for reuse, not proof of correctness.

## Setup

Complete the [adviser quickstart](../guides/agent-memory-quickstart.md) first. The
cache uses the existing local Redis and pinned MiniLM encoder. No additional
Python dependency or embedding API key is required. Add these settings to `.env`:

```dotenv
SHOP_CACHE_ENABLED=true
OPENROUTER_API_KEY=your-key
SHOP_CACHE_DISTANCE=0.2
SHOP_CACHE_TTL=3600
SHOP_JEV_MODEL=typesafe/jev-1.13
SHOP_JEV_CONFIDENCE=0.5
SHOP_JEV_TIMEOUT=5
```

Keep the key local. Jev calls use OpenRouter's paid Decisions API. Build and restart
with `make build` and `make serve`. Chat settings report whether cache configuration
is ready. When the key is missing, ordinary chat remains available without caching.
Runtime cache/verifier errors appear in the inspector and fall back to generation.

Distance is Redis cosine distance (0–2; smaller is closer). The inspector's cosine
similarity is `1 - distance`, not a correctness probability. The confidence cutoff
is a starting point from the article, not a calibrated camera-shop guarantee.

## Rehearse before presenting

1. Prepare Alex's memory using the existing runbook and keep it stable during the
   main sequence. Use fictional preferences such as filming indoors and preferring
   compact gear. Start a fresh conversation so earlier corrections do not intrude.
2. Clear Alex's cache through chat settings. Shared entries have a separate opt-in
   clear control. Never reset all Redis data for this demo.
3. Ask: “I film indoor interviews on my laptop and prefer compact equipment.
   Recommend two compact microphones from the catalogue, explaining their tradeoffs
   and anything unverified. Give your best complete answer with the available
   information; no follow-up question.” The adviser
   chooses retrieval and may nominate its final answer with `store_in_cache`.
4. Inspect the actual result. A reusable turn should show **Stored** after final
   validation. If the model used remote purchase tools, the nomination is skipped;
   provide the equipment explicitly and rehearse another turn. Never label a miss
   or skipped nomination as a successful stored example.
5. Start another Alex conversation and try “For filming interviews indoors with my
   laptop, suggest two small microphones from the catalogue. Explain the pros and
   cons and any unverified compatibility. I prefer compact gear; please give a
   complete answer without follow-up questions.” Check the actual candidate, Jev decision and
   timings. The embedding/verifier outcome is measured, not scripted.
6. Rehearse a similar request with an unmet requirement: “I now film interviews
   outdoors in strong wind instead of indoors, using my laptop. Recommend two compact
   microphones from the catalogue, explaining their tradeoffs, the wind protection
   I need and anything unverified. Give your best complete answer with the available
   information; no follow-up question.” It should generate if the cached answer
   cannot cover the new constraint.
   A distance miss demonstrates retrieval; use a candidate that reaches Jev to
   demonstrate verification. Keep the confidence threshold fixed during evaluation.
7. Check Jordan's same request does not find Alex's private entry. The shopper
   selector demonstrates scope; it is not production authentication.

For a simpler shared example, use **No conversation memory**, a fresh session and
“Explain aperture”. Only a small allowlist of standalone general camera questions
can be admitted as shared, and only with no supplied personal, product or Playbook
context. A shared nomination that fails those checks stays shopper-scoped. When
Playbook is configured, leave its normal guidance intact and demonstrate private
scope; public admission is intentionally conservative.

## Timed walkthrough

For a short look at implementation, use the
[three-minute code tour](../guides/code-walkthrough.md#three-minute-live-code-tour).
It opens the real orchestration, cache policy, RedisVL filters and a behaviour test.
Use it in place of part of the discussion or during questions after the demo.

| Time | Action | Evidence |
| --- | --- | --- |
| 0–2 min | Generate Alex's recommendation. | Memory, catalogue evidence, actual final answer and storage nomination. |
| 2–5 min | Paraphrase as Alex in a new conversation. | Candidate similarity, Jev acceptance/confidence, no answering-model request on a hit. |
| 5–8 min | Repeat as Jordan. | Private scope excludes Alex's candidate before verification. |
| 8–11 min | Add a requirement the answer does not cover. | Jev rejection/uncertainty/low confidence leads to fresh generation. |
| 11–15 min | Discuss stale preferences and production operation. | TTL, entry removal, threshold evaluation and full-request timings. |

The cache toggle bypasses both lookup and storage for a comparison request. Compare
separate fresh sessions with the same prepared context; the toggle does not replay
an identical request or establish a controlled benchmark by itself.

## What we claim, and what remains a production decision

- Cache scope and memory mode are exact filters; similarity is used within those
  boundaries. Model-supplied tool arguments never choose a shopper ID or Redis key.
- Jev uses the new question, original question/answer and available context. It
  judges answer applicability, not equivalence between the two questions.
- The backend rechecks cached product evidence against the current local catalogue.
  Memory snapshots in the cache are historical. A relevant-memory search does not
  establish a complete current profile, and supplied memory is not a dependency list.
- Obvious live purchase, delivery, stock and price requests bypass lookup. Answers
  involving remote purchase/shipment tools are not stored. The keyword bypass is
  conservative rather than a complete intent classifier; Jev also rejects requests
  requiring fresh retrieval.
- Entries have fixed absolute expiry plus Redis TTL. Lookups cannot extend the
  logical lifetime. TTL limits age and does not detect changed preferences.
- There is no automatic memory-change invalidation. For production, decide which
  changes are observable, which make an answer unsuitable, and what staleness is
  acceptable. Streams could deliver change events once a reliable source exists.
  Use the explicit removal control to demonstrate invalidation without implying
  that a background memory integration has been implemented.
- A hit still reads the normal RAM/guidance context and calls Jev. Measure total
  time, false reuse, missed valid reuse and fallback generation costs. The UI shows
  actual timings and provider-reported Jev usage, never estimated savings presented
  as measured results. General grounding limitations of the adviser still apply.

## Evaluation

```bash
# Validate labelled cases without API calls.
uv run python -m eval.cache --dry-run

# Paid live Jev applicability checks. Optional JSON output stays at a chosen path.
uv run python -m eval.cache --repeat 3 --output /tmp/camera-cache-eval.json

# Automated orchestration, HTTP and verifier transport tests.
uv run pytest tests/test_shop_cache_flow.py tests/test_shop_cache_api.py tests/test_shop_jev.py

# Real RedisVL filter/expiry tests: creates and removes isolated test indexes.
TEST_REDIS_URL=redis://127.0.0.1:6379 uv run pytest tests/test_shop_cache.py
```

The ten labelled cases are synthetic and include fictional microphone examples.
They test verification only, not Redis candidate recall, live catalogue truth,
memory freshness or end-to-end savings. The command reports valid reuse, missed
reuse, unsuitable reuse, errors and measured verification latency. It exits nonzero
on an unsuitable reuse or API error; missed valid reuse is reported separately.
Review labels and use additional held-out examples before tuning thresholds.

Read the [implementation boundaries](../architecture/semantic-caching.md) and
[Using Jev to verify cached LLM answers](https://samuelagbede.com/posts/using-jev-to-verify-cached-llm-answers/).
