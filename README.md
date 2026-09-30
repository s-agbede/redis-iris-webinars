# Sam’s Camera Shop

A small camera adviser for learning **Redis Agent Memory and Context Retriever**.
Ask about an earlier purchase, get recommendations based on retrieved product
details, and see how the adviser remembers preferences across conversations.

The app supplies context with each request to the model:

- **Session memory:** messages from the current conversation.
- **Long-term memory:** facts saved for the shopper and retrieved across conversations.
- **Orders and deliveries:** fictional purchases, linked products and shipment records retrieved live
  through Context Retriever, using a separate scoped key for each demo shopper.
- **Catalogue search:** products found through the existing local Redis hybrid search.

Redis Agent Memory extracts long-term facts from conversations in the background.
The app lets you turn memory context off and inspect exactly what the model received.
Purchase retrieval remains available in every memory mode. A historical purchase
does not prove current ownership; the adviser can use a current correction or
remembered preference when giving advice.

## Start here

**[Follow the beginner quickstart →](docs/guides/agent-memory-quickstart.md)**

It takes you through setup, one conversation, and checks of the supplied context.
You need basic terminal skills, Docker, Python/uv, Node.js, Redis Agent Memory and
Context Retriever services, and an OpenAI API key. The guide explains where to
get them. Allow several minutes for the first setup and for background memory extraction.

For Context Retriever, follow the [service setup and checks](docs/guides/context-retriever-smoke.md).
Chat requires `CTX_MCP_URL`, `CTX_ALEX_AGENT_KEY` and `CTX_JORDAN_AGENT_KEY` in
`.env`, alongside RAM and OpenAI settings. `REDIS_URL`/`REDIS_PORT` configure the
local catalogue; `CTX_REDIS_URL` configures the separate database used when seeding
the retriever's records. The running adviser uses the MCP endpoint and scoped keys.

Playbook, custom memory types and privacy-filter demonstrations are optional.
They are not needed for your first run.

Already set up? From the repository root:

```bash
make redis
make serve
```

Open [the adviser](http://127.0.0.1:8000/), then follow
[your first memory conversation](docs/guides/agent-memory-quickstart.md#4-try-one-memory-conversation).
Use fictional details: Alex and Jordan are demo shoppers, not authenticated accounts.

To try Context Retriever, ask **“What did I purchase here, and when?”** and open
**What the model saw → Available tools** and **Tool calls**. The model discovers
and calls generated MCP tools such as `filter_purchase` and `get_product_by_id`.
Alex's seeded orders include a Sony ZV-E10 and a September 22 RØDE microphone;
Jordan's order is a JJC hand strap. The backend retrieves each order and its
product from the service. Retrieval failures produce explicit errors;
there is no hard-coded purchase-history fallback.

To run the deck's delivery demo, select Alex and ask **“Hi, my new mic still
hasn’t arrived. It was meant to come on Tuesday.”** The adviser retrieves the
microphone purchase and linked shipment: held at the local depot, originally
September 29, now expected Thursday, October 1, 2026. These are dated fictional
records. See the [presenter walkthrough](docs/demos/context-retriever.md) for
setup and the repeatable status-change demonstration.

## Other ways to explore

| You want to… | Go here |
| --- | --- |
| Try search without cloud credentials | [Local search setup](docs/guides/local-development.md#run-locally), then [Search lab](http://127.0.0.1:8000/?view=compare) |
| Set up Context Retriever and check shopper isolation | [Service setup and checks](docs/guides/context-retriever-smoke.md) |
| Demonstrate delivery lookups and changing shipment status | [Context Retriever walkthrough](docs/demos/context-retriever.md) |
| Present the 15-minute memory webinar | [Presenter runbook](docs/demos/agent-memory.md) |
| Change ports, edit code or troubleshoot local setup | [Local development reference](docs/guides/local-development.md) |
| Understand how the memory code works | [Memory architecture](docs/architecture/agent-memory.md) |
| Understand the purchase retrieval code | [Context Retriever architecture](docs/architecture/context-retriever-chat.md) |
| Explore optional memory features | [Advanced memory guide](docs/guides/agent-memory-advanced.md) |
| Browse the search and production webinars | [Documentation index](docs/README.md) |

The catalogue contains real product listings. Purchase histories are fictional;
the adviser cannot verify prices, stock or compatibility. The same catalogue also
supports the search and production-pattern demos.
Live UI testing found that the model can still assert technical details absent
from retrieved listings, including when an earlier answer has become a memory.
See the [UI verification record](docs/architecture/context-retriever-ui-checks.md)
for tested flows, fixes and remaining answer-quality limitations.
The retriever reads eleven seeded documents (two shoppers, three purchases,
three products and three shipments). The microphone is an explicit demo product
record; the Sony and strap retain their source catalogue records. New purchases
and catalogue edits are not automatically synchronized into those records.
