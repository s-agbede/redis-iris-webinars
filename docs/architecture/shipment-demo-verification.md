# Shipment demo verification — September 30, 2026

The running adviser retrieves the deck's microphone delivery story from the live
Context Retriever service. The records are fictional; no carrier integration is
configured. Follow the [presenter runbook](../demos/context-retriever.md).

## Published state

- Existing surface `camera-shop-context-smoke` updated with Shopper, Purchase,
  Product and Shipment entities; sixteen generated MCP tools are available.
- Eleven isolated fixture documents contain two shoppers, three purchases,
  three products and three shipments. The guarded migration changed eight keys.
- Existing source configuration and Alex/Jordan scoped credentials were retained.
- Pre-push service check at 12:53 UTC passed all 27 probes, including foreign
  purchase and shipment ID/filter isolation.
- Alex's microphone shipment was restored to the original delayed snapshot.

## Live adviser rehearsal

Seven API conversations/checks passed using the live model and service:

1. The missing-microphone question identified RØDE VideoMicro II, the depot event,
   original ETA September 29 and revised ETA October 1.
2. “Where is my last order?” selected September's microphone purchase.
3. After switching the Redis snapshot to delivered, a follow-up in the same
   conversation retrieved and reported the new delivery event.
4. Restoring the delayed snapshot and asking again retrieved the changed record.
5. Jordan's latest order returned the delivered hand strap.
6. Jordan's request for Alex's shipment did not reveal Alex's delivery data.
7. A missing shipment ID produced an unavailable-record answer.

The main app on port 8000 was restarted and the missing-microphone question was
also exercised through the browser with session and long-term memory enabled.
The displayed answer contained the correct product, depot event and both dates.
The inspector showed four actual calls: `filter_purchase`, `get_shipment_by_id`,
`get_purchase_by_id` and `get_product_by_id`, with the retrieved shipment fields.
Generated tool selection and the number of calls may vary between model runs.

During development, the new demo product initially caused a validation failure
because catalogue products accept only the `us` locale. A separate validated demo
product boundary and regression tests fixed that case. An earlier latest-order
rehearsal also returned an untraced 503; its cause was not captured. Subsequent
traced latest-order checks passed. These results verify the tested runs, not an
absence of intermittent upstream or model failures.

## Automated checks

| Check | Result |
| --- | --- |
| Full Python suite with Context Retriever extra | 309 passed, 35 skipped |
| Fixture/setup tests against local Redis JSON at port 6381 | 39 passed |
| Ruff on application, shipment seed/scripts and tests | Passed |
| Mypy on application, seed, evaluation and scripts | Passed, 44 source files |
| Frontend TypeScript/Vite build | Passed |
| Frontend Node tests | 29 passed |

The full suite's skipped tests require separately enabled integrations. The
explicit local Redis run exercised migration conflicts, repeatability and replay
against real JSON storage. API regression tests cover linked evidence, fresh
shipment reads despite old conversation memory, and safe rejection of malformed
or foreign shipment records. Code review covered migration scope, response
validation and access checks before completion.
