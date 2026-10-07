# Read the camera shop as a story

Start with a request and follow the functions it calls. The same code serves the
browser, the automated tests and the live demo.

## One adviser turn

Open [`ShopService.turn`](../../app/shop/service.py). This is the reading spine:

1. **Load context.** Validate the shopper/session, then read the selected RAM
   history and relevant memories. Guidance, when configured, is loaded here too.
2. **Try reuse.** Pass the question, context and server-derived owner to the cache
   policy. It returns an optional answer, its product cards, and a decision trace.
3. **Generate if needed.** The answering model can choose catalogue or scoped MCP
   tools. Those tools accumulate evidence in the current turn.
4. **Validate and save.** Check the answer's product IDs against supplied evidence,
   append the two conversation events to RAM, and persist the local session.
5. **Consider storage.** A model nomination becomes a cache write only after the
   answer has passed validation and the conversation has been saved.

`_load_context`, `_try_reuse` and `_save_conversation` explain each stage. Timing
and inspector fields record what happened; they do not decide whether reuse is valid.
[`prompts.py`](../../app/shop/prompts.py) contains the instructions, and
[`tools.py`](../../app/shop/tools.py) contains the tool definitions and execution.

Useful data types live in [`shop/models.py`](../../app/shop/models.py):

| Type | Meaning |
| --- | --- |
| `TurnContext` | Context available for this turn, including evidence accumulated by tools |
| `ModelAnswer` | Final text, selected product IDs and captured model/tool activity |
| `CacheEntry` | Saved question, final answer, evidence, scope and fixed expiry |
| `ReuseResult` | Optional reusable answer plus its cards and cache decision trace |
| `ChatTurn` | The saved reply and evidence displayed by the inspector |

On a cache hit, the service attaches the checked product cards explicitly.
`AnswerReuse.find` never quietly changes its input context. Cached source context
remains historical; it is not displayed as a new model request.

## Follow the cache decision

Read [`AnswerReuse.find`](../../app/shop/reuse.py) from top to bottom:

```text
question + currently available context
  → bypass requests needing live records
  → retrieve one candidate within scope/mode/configuration filters
  → recheck scope before exposing candidate details
  → check expiry and saved product evidence
  → ask Jev whether this exact answer covers the new request
  → accept above the confidence cutoff, or continue to generation
```

The named helpers keep the decisions visible:

- `stale_evidence_reason` compares saved product cards with today's local catalogue.
- `can_share_answer` allows only a small set of standalone educational questions
  with no supplied personal context. Other eligible answers stay shopper-scoped.
- `cache_version` fingerprints application rules and guidance. It does not hash all
  of Alex's memories or invalidate the cache for every new memory.

Then open [`RedisAnswerCache.lookup`](../../app/shop/cache.py). RedisVL owns vector
lookup; the adapter supplies exact metadata filters and validates the stored
payload. Similarity selects a candidate. It does not authorize another shopper's
entry or establish that an answer is still appropriate.

Finally, [`ReuseRequest`](../../app/shop/jev.py) makes Jev's input explicit: the new
question and available context, plus the cached question, answer and context.
`JevVerifier.verify` sends that request and validates the returned decision.
Timeouts, malformed decisions and uncertainty lead back to generation.

**The important unresolved production question:** which changes make an answer
unusable, and how does the application learn about them? Retrieved memory is
incomplete and may evolve asynchronously. The demo checks local product evidence,
uses fixed expiry, and shows current supplied context to Jev. It has no automatic
memory-change invalidation. Supplied memories are not a proven dependency list;
Streams would transport change events once their source and meaning are defined.

## The browser tells the same story

Start with [`Shop.tsx`](../../web/src/Shop.tsx), which assembles the screen:

| File | Responsibility |
| --- | --- |
| [`useShopConversation.ts`](../../web/src/useShopConversation.ts) | Restore a saved session, send a message, remember the reply and handle failures |
| [`ShopSettings.tsx`](../../web/src/ShopSettings.tsx) | Shopper, memory mode, cache toggle and scoped cache clearing |
| [`ShopInspector.tsx`](../../web/src/ShopInspector.tsx) | Retrieved memories and evidence for the selected turn |
| [`ModelEvidence.tsx`](../../web/src/ModelEvidence.tsx) | Captured model request, source context and tool calls |
| [`CacheEvidence.tsx`](../../web/src/CacheEvidence.tsx) | Candidate distance, Jev decision, storage outcome and measured timings |

Switching shopper remounts conversation state. Cache clearing and chat share a
busy guard. The inspector distinguishes a fresh model request from reused text
and the historical context behind it.

## Search and production patterns

You can explore these independently of the cloud adviser services:

| Read in this order | What to follow |
| --- | --- |
| [`search_routes.py`](../../app/search_routes.py) → [`Searcher.compare`](../../app/search.py) | HTTP input → query preparation → requested retrieval methods → ranked product evidence |
| [`queries.py`](../../app/queries.py) | RedisVL lexical, vector and hybrid query construction with common filters |
| [`evidence.py`](../../app/evidence.py) | Literal matches and verified hybrid score contributions |
| [`product_store.py`](../../app/product_store.py) → [`SyncWorker.process_one`](../../app/sync.py) | Source write and Stream event → current product state → passage replacement and acknowledgement in one transaction |
| [`DeploymentManager.validate`](../../app/deployment.py) | Candidate content/vector checks → retrieval checks → confirmation that the source revision stayed unchanged |
| [`main.py`](../../app/main.py) | Application assembly and shared resource startup/shutdown |

The indexing Stream handles catalogue updates. It does not invalidate cached
answers when RAM changes. The worker's lease, watched source revision and atomic
acknowledgement preserve its retry behaviour when a process fails or data changes.

## Three-minute live code tour

Have these four files open before presenting. Use the inspector for the visible
result, then show the code responsible for that result.

| Time | Open | Explain |
| --- | --- | --- |
| 0:00–0:45 | `app/shop/service.py` → `ShopService.turn` | “Load context, try reuse, generate if needed, save. Both paths become a normal conversation turn.” |
| 0:45–1:30 | `app/shop/reuse.py` → `AnswerReuse.find` | “The nearest question is a candidate. Scope, evidence and Jev still have to approve reuse.” |
| 1:30–2:15 | `app/shop/cache.py` → `RedisAnswerCache.lookup` | “One RedisVL cache; exact metadata filters limit which entries can compete.” |
| 2:15–3:00 | `tests/test_shop_cache_flow.py` | Open the cross-shopper test or the changed-product test. “This is the observable behaviour we must preserve.” |

For a closer look at the verifier, replace the test stop with `ReuseRequest` and
the decision prompt in `app/shop/jev.py`. Open `.env.example` if discussing
configuration; keep the actual `.env` off the projector.

## Check your changes

From the repository root:

```bash
uv run pytest -q
make lint
npm --prefix web test
npm --prefix web run build
```

The default Python suite needs no live model calls. Redis integrations are skipped
unless `TEST_REDIS_URL` points to a test database; use a disposable Redis 8 instance.
See [verification](verification.md) and the
[semantic-cache runbook](../demos/semantic-caching.md#evaluation) for integration
and paid Jev evaluation commands.

Tests to read alongside the code:

- [`test_shop_cache_flow.py`](../../tests/test_shop_cache_flow.py): hit, miss,
  rejection, scope, bypass, nomination and persistence failure paths.
- [`test_shop_reuse.py`](../../tests/test_shop_reuse.py): returned evidence and
  unchanged input context.
- [`test_shop_jev.py`](../../tests/test_shop_jev.py): request serialization,
  malformed responses, confidence and transport failures.
- [`test_sync.py`](../../tests/test_sync.py) and
  [`test_deployment.py`](../../tests/test_deployment.py): real Redis publication,
  retries, catalogue changes and index replacement.
