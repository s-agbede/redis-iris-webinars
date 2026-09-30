# Verification

For a first run, use the [quickstart checkpoints](agent-memory-quickstart.md#4-try-one-memory-conversation).
This page is for contributors checking code changes. Run commands from the repository root.

## Local code checks

```bash
make lint
make test
make context-test
npm --prefix web run build
node --experimental-strip-types --test web/src/*.test.mjs
```

The shop tests use controlled transports for external services. Passing them does
not prove that your cloud credentials work or that extraction has completed.
`/api/shop/status` checks settings presence and catalogue availability; verify a
real reply and actual recalled context with the quickstart.
`make context-test` installs the optional Context Retriever SDK and covers its
standalone checker, the runtime HTTP adapter and the complete chat tool loop.
It verifies generated schema forwarding, model-selected calls, selected-shopper
keys, all memory modes, pagination, empty results and safe failures without saved
replies. Nested records and malformed schemas are checked before model use.

## Live Context Retriever and chat checks

Complete the [service setup](context-retriever-smoke.md) and seed its eleven demo
documents. Restore the delayed snapshot if a rehearsal changed it, then run:

```bash
make context-check
```

The 27 read-only probes check both allowed and foreign shopper, purchase and
shipment lookups, plus shared product reads. This verifies the service and scoped
keys independently of RAM and the chat model. It does not exercise chat or
background extraction.

Then follow the [browser walkthrough](../demos/context-retriever.md): retrieve
Alex's missing microphone, replay its delivery update in the same conversation,
and verify Jordan's separate hand-strap order. Inspect the actual tool results,
RAM context and product cards. A correct
answer alone is insufficient: the history must be present in the recorded tool
output, under the selected shopper. Keep historical purchases distinct from
current ownership and remembered preferences.

For the optional fixture-seeding tests, use your actual local Redis port:

```bash
TEST_REDIS_URL=redis://localhost:6379 make context-test
```

Those tests use unique temporary keys and remove only their own records.
The [integration verification record](../architecture/context-retriever-chat.md#verification)
documents the completed live checks and their limits.
The [shipment verification record](../architecture/shipment-demo-verification.md)
covers the current four-entity model, delivery answers and freshness rehearsal.
The [UI verification record](../architecture/context-retriever-ui-checks.md)
covers recovery, memory modes, responsive layout and the unresolved technical
grounding failures found by checking actual replies against their tool evidence.

## Live search checks

```bash
TEST_REDIS_URL=redis://localhost:6379 uv run pytest -q tests/test_live_camera_flow.py
```

The live test needs the prepared model and camera index. It checks all three
methods, combined brand and color constraints (including Basic), unique products, source-passage offsets,
empty filters, literal-overlap offsets, verified native fusion arithmetic and
hybrid's zero lexical contribution when no lexical terms match. The ordinary
suite skips that integration check unless `TEST_REDIS_URL` is set. A real-model
unit check also skips if its pinned files have not been prepared.

For the browser flow, open Advanced and select Brand: Sony before searching for
`camera`, then enable all four methods. Every result should show Sony metadata.
Inspect the Redis commands to verify brand constraints in both Hybrid branches.
Change the query and confirm the filters persist, then use Clear filters and
confirm the brand control resets and results update. Try a query and brand with no
matching products and verify the empty states suggest clearing filters. Check this at
desktop width and at 390px, with no page-level horizontal overflow.

Color filtering is API-only. Use `POST /api/compare` with
`{"query":"camera","brands":["Sony"],"colors":["white"],"include_basic":true}` and
check that results have Sony/White metadata and both Hybrid branches include the
color constraint. The live integration test also covers this combined filter.

## Advanced memory evaluation

The [advanced memory evaluator](agent-memory-advanced.md#repeatable-live-ram-evaluation)
writes isolated fictional fixtures to the configured RAM service and observes
recall, correction and exclusion behaviour. Run it deliberately after cloud setup;
it is not required for the introductory exercise.

The [generated-tool UI and teaching review](../architecture/context-retriever-pedagogy-checks.md)
records varied queries, source attribution, memory contrasts, error recovery and
remaining model-response limitations.
