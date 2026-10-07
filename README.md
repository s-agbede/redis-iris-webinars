# Sam’s Camera Shop

A working camera shop for learning **search, agent memory, live retrieval, and
semantic caching**. Ask for gear recommendations, inspect the evidence behind an
answer, then see when a previous answer can be reused for the same shopper.

| Lesson | What you can see | Start reading |
| --- | --- | --- |
| Search | One catalogue queried with keywords, vectors and hybrid search | [`Searcher.compare`](app/search.py) |
| Agent memory | Session history and relevant memories supplied to an adviser turn | [`ShopService.turn`](app/shop/service.py) |
| Context Retriever | The adviser choosing scoped tools for purchases and deliveries | [`ShopRetrieval.call`](app/shop/tools.py) |
| Semantic caching | RedisVL finds a scoped candidate; Jev checks whether its answer still fits | [`AnswerReuse.find`](app/shop/reuse.py) |

**[Read the code as a story →](docs/guides/code-walkthrough.md)**
The walkthrough connects these entry points and includes a three-minute live code tour.

## Choose your starting point

This is the **`semantic-caching`** branch. Its setup guides use this branch and
include the earlier search, memory and Context Retriever lessons.

| What you want to run | What you need | Setup |
| --- | --- | --- |
| Search and production-pattern labs | Docker, Python 3.12+/uv, Node.js 22.18+, Git and Make; no cloud API keys | [Local setup](docs/guides/local-development.md#run-locally) |
| Camera adviser with memory and live records | Local setup, Redis Agent Memory, Context Retriever with separate shopper keys, and an OpenAI API key | [Beginner quickstart](docs/guides/agent-memory-quickstart.md) |
| Semantic answer cache | A working adviser and an OpenRouter API key for Jev | [Cache setup and 15-minute runbook](docs/demos/semantic-caching.md) |

The first setup downloads the pinned local embedding model and indexes the bundled
catalogue. Allow several minutes. Cloud services are configured separately in
`.env`; use [`.env.example`](.env.example) as the reference and keep credentials local.
Playbook and advanced memory features are optional.

Already configured and seeded? From the repository root:

```bash
make redis
make build
make serve
```

`make build` updates the browser bundle after pulling changes. Open
[the adviser](http://127.0.0.1:8000/) or
[the search lab](http://127.0.0.1:8000/?view=compare).
Use `make serve PORT=8001` if port 8000 is occupied.

## Follow an answer

An adviser turn loads the selected session history and relevant long-term memories.
The model can then search the local catalogue or call Context Retriever tools for
fictional purchases and deliveries. The inspector shows the supplied context,
actual tool calls, product evidence and measured timings.

With semantic caching enabled, the flow is:

```text
Question + available context
  → RedisVL lookup within scope, memory-mode and configuration filters
  → check saved product evidence and expiry
  → Jev confirms the cached answer still applies
  → reuse it, or ask the answering model for a fresh reply
```

A model can nominate its final reply with `store_in_cache`. The backend validates
and saves the conversation before admitting the answer to the cache. Personalised
answers stay shopper-scoped; only narrowly defined standalone educational answers
can enter shared scope. Live purchase and delivery answers are excluded.

Try the [semantic-cache runbook](docs/demos/semantic-caching.md) to demonstrate an
Alex recommendation, a paraphrase, Jordan's separate scope, and a new constraint
that makes the old answer unsuitable. The inspector reports what actually happened;
a similar question does not guarantee a cache hit.

## Develop and verify

```bash
uv run pytest -q
make lint
npm --prefix web test
npm --prefix web run build
```

The default tests make no paid model calls. Redis integration checks are opt-in;
the real-model search checks also need a seeded catalogue. Follow the
[verification guide](docs/guides/verification.md) for their setup and the
[cache evaluation guide](docs/demos/semantic-caching.md#evaluation) for paid Jev checks.

## Explore the other demos

| Demo | Walkthrough |
| --- | --- |
| Search comparison | [Keywords, vectors, hybrid retrieval and result evidence](docs/demos/search.md) |
| Production patterns | [Catalogue freshness, measured traffic and index replacement](docs/demos/production.md) |
| Agent memory | [Preferences within and across conversations](docs/demos/agent-memory.md) |
| Context Retriever | [The missing microphone and changing shipment status](docs/demos/context-retriever.md) |

See the [documentation index](docs/README.md) for architecture, service setup,
troubleshooting and presentation material.

## Demo boundaries

Alex and Jordan are fictional shoppers selected through local presenter controls;
the selector is not authentication. The catalogue contains real product listings,
but purchase and shipment records are fictional, and the adviser cannot verify
current prices, stock or compatibility. Context Retriever's seeded records do not
automatically receive catalogue edits or new purchases.

Retrieved memories can be incomplete, stale or wrong. Jev checks answer applicability
against the supplied context; it does not establish a complete current profile.
Fixed expiry limits cache age, and there is no automatic memory-change invalidation.
The [cache architecture](docs/architecture/semantic-caching.md) explains these limits
and records the measured rehearsal results. The adviser can still make unsupported
claims; see the [answer-quality verification record](docs/architecture/context-retriever-ui-checks.md).
