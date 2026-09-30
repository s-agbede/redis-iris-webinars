# Context Retriever: the missing microphone

This is the delivery scenario in slides 5–16 of the Context Retriever deck.
The shopper describes a problem without supplying an order ID. The model uses
retrieved purchases, product identity and the purchase-to-shipment link to answer.
Generated tools are discovered over MCP; the application does not prescribe a
three-call sequence. RAM and catalogue search remain available for other questions.

## Prepare

Complete the [adviser quickstart](../guides/agent-memory-quickstart.md) and
[retriever setup](../guides/context-retriever-smoke.md). For the existing service:

```bash
make context-migrate
make context-publish
make shipment-delayed
make context-check
make serve
```

Publishing needs the existing `CTX_ADMIN_KEY` and `CTX_SURFACE_ID`; runtime chat
uses only the two scoped agent keys. Migration refuses unknown changed records.
For repeat rehearsals, use `make shipment-delayed` before `make context-check`;
the checker expects the initial delayed snapshot. It runs 27 probes.
Restart an already-running backend after code changes. Open
[the adviser](http://127.0.0.1:8000/).

The fixture story takes place on September 30, 2026. Tuesday is September 29;
Thursday is October 1. The adviser gives explicit dates so the story remains
understandable when rehearsed later. These are fictional dated snapshots, not a
live carrier feed. The delivery replay deliberately switches between snapshots.

| Shopper | Order / purchase date | Product | Shipment snapshot |
| --- | --- | --- | --- |
| Alex | `SAM-DEMO-1001` / April 18 | White Sony Alpha ZV-E10 | `SHIP-1001`, delivered April 22 |
| Alex | `SAM-DEMO-1002` / September 22 | RØDE VideoMicro II | `SHIP-1002`, held at local depot; original ETA September 29, revised ETA October 1 |
| Jordan | `SAM-DEMO-2001` / June 3 | JJC mirrorless camera hand strap | `SHIP-2001`, delivered June 6 |

The microphone is an explicitly fictional product record added for this story.
Its name is a demo reference, and its record does not verify specifications,
price, availability or compatibility. The Sony and strap retain source listings.

## Show the missing-microphone answer

1. Select **Alex** under **⋯ Chat settings** and start a **New conversation**.
   Choose **No conversation memory** to demonstrate source retrieval alone, or
   **Short-term: this session only** for the freshness follow-up below.
2. Ask: **“Hi, my new mic still hasn’t arrived. It was meant to come on Tuesday.”**
3. Expect a concise answer identifying the RØDE VideoMicro II and explaining
   that its demo shipment is held at the local depot, now due October 1, 2026.
   It must not offer a delivery investigation or courier contact.
4. Open **What the model saw → Available tools / Tool calls**. Show the actual
   purchase, product and shipment results. The service currently exposes
   `filter_purchase`, `get_product_by_id`, `get_shipment_by_id`, `expand_results`
   and other generated tools. The model may choose another valid sequence.
   The deck's tool names and exactly three calls are illustrative.
5. In a fresh conversation ask **“Where is my last order?”**. Expect the September
   microphone purchase, rather than the older Sony purchase, and its shipment.

A request can start from purchases or shipments. Either path must establish
which product was ordered using linked records. A shipment row alone does not
identify a microphone. Internal record IDs stay visible in the inspector.

## Demonstrate freshness

Keep the same Alex conversation with session memory enabled:

```bash
make shipment-delivered
```

Ask **“Has that microphone arrived now? Check the latest delivery record.”**
The answer should report **delivered to the recipient** using a new shipment
lookup, even though the previous assistant answer says it was held at the depot.
The delivered demo event is dated September 30 at 14:00 UTC; the original delayed
snapshot is September 30 at 09:00 UTC. This replays a fictional update in Redis.
It does not demonstrate synchronization from a separate carrier/source system.

Reset for the next rehearsal:

```bash
make shipment-delayed
make context-check
```

Ask again to show the changed source result. This is an explicit replay reset,
not a real parcel moving backwards. Both commands touch only `SHIP-1002` and
refuse unrecognized values.

## Show access scope and missing records

Switch to **Jordan** and start a new conversation:

- **“Where is my last order?”** should return Jordan's delivered hand strap.
- **“Show me shipment SHIP-1002.”** must not disclose Alex's parcel details.
- As either shopper, **“Look up shipment SHIP-9999.”** should report no accessible
  record without inventing contents or distinguishing missing from unauthorized.

Shopper selection is a teaching control, not account authentication. The backend
selects separate scoped keys; access mappings protect Shopper, Purchase and
Shipment. Slide 20's shared app key plus signed user token is a production pattern,
not implemented login functionality in this local demo.

## Optional memory and recommendation continuation

Ask **“Find a lightweight microphone for the camera I bought here.”** Purchase
history should inform local `search_catalogue`; product compatibility still needs
source evidence. Say **“I sold that Sony. My only camera now is a Canon EOS R50.”**
Then ask which camera you currently use with session memory enabled. The correction
changes the remembered setup; it does not rewrite a historical order.

## Boundaries

The service reads eleven seeded documents. New purchases and edits in **Manage
shop** are not synchronized into these records. There are at most six tool calls
per turn. Pagination metadata reaches the model; it must disclose incomplete
results if the budget is exhausted. Retrieval failures return explicit errors
without a fabricated reply or local fixture fallback. Empty results stay empty.
A missing shipment means unavailable delivery status, not permission to invent a
carrier lookup. The browser inspector records the actual evidence for each reply.

See the [September 30 verification record](../architecture/shipment-demo-verification.md)
for live rehearsal results and automated checks.
