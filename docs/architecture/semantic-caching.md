# Scoped RedisVL answer caching

The optional feature preserves the existing FastAPI/React adviser and adds a
cache-aside path before the answering model. The user-selected RedisVL backend
shares the local Redis connection and local MiniLM encoder, but uses its own index.

## Components

- `app/shop/cache.py`: lazy RedisVL `SemanticCache`, mandatory scope/mode/version
  filters, typed payload validation, expiry, scoped deletion and reset.
- `app/shop/jev.py`: OpenRouter Decisions HTTP adapter, fixed Choice question and
  typed `ReuseRequest` plus a validated accept/reject/uncertain distribution. It exposes errors without raw
  response bodies or credentials. Confidence is distinct from `probabilities.accept`.
- `app/shop/reuse.py`: candidate validation, catalogue evidence checks, Jev routing,
  conservative public admission and deferred final-answer storage. Lookup returns
  a `ReuseResult` containing answer, cards and trace; it leaves the input context unchanged.
- `app/shop/service.py`: owns the context → reuse/generate → validate → persist →
  cache sequence, shopper/session identity and real memory-event writes.
- `app/shop/tools.py`: catalogue/MCP tool execution and optional `store_in_cache`
  nominations. Tools accumulate product evidence for final validation.
- `app/shop/prompts.py`: shop and tool-use instructions, kept separate from orchestration.
- `app/shop/routes.py` and `settings.py`: opt-in construction, request bypass,
  readiness metadata and local presenter removal/reset controls.
- `web/src/CacheEvidence.tsx`: cache evidence in the existing inspector.
- `web/src/useShopConversation.ts` and `ShopSettings.tsx`: conversation requests and
  settings respectively; `Shop.tsx` assembles the screen.
- `eval/cache.py`: labelled synthetic applicability evaluation with no fallback
  generation or invented end-to-end savings.

## Storage and eligibility

An entry contains original question, final answer, product cards, historical
TurnContext, creation/absolute-expiry times, an opaque ID, scope, memory mode and
configuration signature. Scope is `shared` or the server-derived RAM owner. The
configuration signature covers answering model/instructions, embedding revision
and supplied Playbook guidance; it is not a hash of shopper memories.

The RedisVL index is named from the catalogue namespace and demo owner prefix.
Filter fields include scope, memory mode, configuration version and entry token.
Unique tokens prevent identical prompts from overwriting independent entries.
Public entries can be searched from either memory mode; private entries require
the original memory mode. The payload is checked again before exposure.

The model can nominate `shopper` or `shared` storage, but cannot supply the owner,
answer, payload, key or lifetime. Shared admission requires an allowlisted general
camera question and absence of session/memory/product/guidance context. Otherwise
the entry remains private. Remote retrieval turns and live-data requests are skipped.

RedisVL 0.26 refreshes a configured global TTL on lookup. This adapter sets no
global TTL and supplies an individual TTL on storage. The absolute timestamp in
the payload independently prevents reuse after its fixed expiry.

## Request and failure behavior

RAM and guidance load as before. Lookup errors produce a visible cache error and
continue to ordinary generation. A candidate with changed/missing catalogue
evidence is rejected before Jev. An accepted Jev choice must meet the confidence
threshold; uncertainty, low confidence, malformed output or transport failure
causes generation. No cached answer is served merely because Jev is unavailable.

Cache hits carry no current answering-model request or tool calls. Their source
context is explicitly historical; validated local cards are supplied separately.
Both normal replies and hits append USER/ASSISTANT RAM events and persist the
session. A nomination is stored only after final validation and successful session
persistence; the tool itself acknowledges nomination rather than successful storage.

Reset/removal endpoints share the chat turn lock to avoid interleaving with a new
cache write. They only delete entries in this cache's index and selected scope;
they do not use FLUSHDB. Demo shopper selection is not authentication.

## Deliberate limits

This is a 15-minute teaching integration, not a complete cache-invalidation system.
No whole-user hash, dependency graph, authoritative preference profile, Streams
consumer or RAM-change subscription is implemented. Cached memory is evidence of
what the model received, not proof that every supplied fact influenced the answer.
Prepare stable memories for the primary demonstration. Immediate explicit changes
are visible to Jev through the current request/context, but this does not guarantee
observation of all asynchronous memory changes. Reuse quality must be evaluated.

The keyword live-data bypass is an intentionally conservative teaching guard.
Product comparison uses the current local catalogue, which itself is not a live
stock/price/compatibility authority. Jev error fallback and typed transport tests
do not establish live verifier accuracy.

## Rehearsal evidence: 7 October 2026

The full app was exercised using local Redis, the real RAM service, gpt-5-mini and
`typesafe/jev-1.13-20260917`, with an isolated QA shopper prefix. The configured
optional Playbook service was unreachable, so this QA process used built-in shop
guidance through environment overrides. Saved Playbook settings were preserved.

| Request | Observed result | Actual total |
| --- | --- | --- |
| Alex: two compact microphones for indoor laptop interviews | Miss, catalogue retrieval, model nomination, final answer stored privately | 12,762.5 ms |
| Alex: paraphrase in a fresh conversation | Hit; distance 0.1145; Jev accepted at confidence 0.73; exact answer and cards reused | 2,057.0 ms |
| Jordan: same paraphrase | Scope miss; no Jev call; fresh answer generated and stored for Jordan | 10,322.3 ms |
| Alex: now outdoors in strong wind, requesting wind protection | Candidate found at distance 0.1517; Jev rejected at confidence 1.0; fresh answer generated | 13,233.9 ms |

The hit recalled eight memory records, validated two returned product cards,
saved conversation events, and made no answering-model request or retrieval tool
calls. Jev took 541.9 ms, consumed 6,037 input tokens and reported $0.000253554 cost.
These are single observed requests with different wording and evolving context,
not a controlled latency benchmark or a measurement of total cost savings.

The ten labelled synthetic verifier cases separately produced 2/4 valid reuses,
2 missed valid reuses, 0/6 unsuitable reuses and no API errors. Median verification
time was 257.34 ms; total provider-reported cost was $0.000291732. The confidence
cutoff stayed at 0.5. The indoor paraphrase was rejected and the unrelated-memory
case was accepted below the confidence cutoff. This small sample demonstrates
missed-reuse tradeoffs; it does not establish production accuracy.

Final automated checks: 382 Python tests passed (42 service-dependent tests skipped
in the default run); all seven cache integration tests separately passed against
disposable Redis 8. All 40 frontend tests, the production build, Ruff and strict
mypy checks passed. Review also covered expiry during verification and failure to
save optional cache evidence after the conversation was already persisted.

## Readability refactor verification: 7 October 2026

The subsequent teaching refactor keeps both instruction strings unchanged, returns
cache evidence explicitly, and separates orchestration from tools, transport and
screen sections. See the [code walkthrough](../guides/code-walkthrough.md).

- Default Python suite: **386 passed, 42 skipped**.
- The 39 self-contained Redis integration checks passed on a disposable database.
  The remaining three real-model search checks passed against the already-seeded
  local catalogue; they require its full product dataset and passage index.
- Frontend: **45 tests passed**, TypeScript/Vite production build passed.
- Ruff and strict mypy passed across **48 source files**.
- Search results matched the starting implementation in 1,008 comparisons when
  measured timings were excluded. Twelve representative React renders were identical.
- Browser smoke verified saved-session restoration, shopper switching, cache-toggle
  state, cache-hit evidence rendering and inspector-close focus. The restarted backend
  restored the existing rehearsal conversation.

The browser smoke reused an existing rehearsal turn. It was not another paid Jev
accuracy evaluation. The recorded live measurements above remain the rehearsal evidence.

## Sources

- [RedisVL SemanticCache](https://redis.io/docs/latest/develop/ai/redisvl/api/cache/)
- [OpenRouter Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)
- [Jev confidence](https://docs.typesafe.ai/confidence)
- [The author's Jev experiment](https://samuelagbede.com/posts/using-jev-to-verify-cached-llm-answers/)
