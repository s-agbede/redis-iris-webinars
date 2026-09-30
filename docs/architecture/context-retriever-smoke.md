# Context Retriever smoke test

This records the initial purchase-only service on September 29. The subsequent
[shipment verification](shipment-demo-verification.md) covers the current four
entities, eleven documents and 27 service checks. Use the
[setup guide](../guides/context-retriever-smoke.md) for current commands.

Approved scope, 2026-09-29: establish service connectivity, model
`Shopper → Purchase → Product`, and verify generated retrieval tools and shopper
scoping before changing the adviser.

## Design

Use the official `redis-context-retriever` SDK as an optional dependency. Export
three `ContextModel` entities and six fixture records from the existing camera
dataset. Keep product JSON fields unchanged. Put all fixtures under
`camera:context-smoke:` so the experiment cannot change the live catalogue.
Purchases remain explicitly fictional historical records, not current ownership.

Map `$.shopper_id` to the `shopper` access tag on Shopper and Purchase. Products
are shared. Use separate Alex and Jordan agent keys. Check both permitted reads
and attempts to read the other shopper's records, by filter and direct ID.
An empty allowed query, missing tool, malformed payload or upstream error cannot
establish isolation. Inspect generated tool schemas before calling them.

A standalone command exports the schema, seeds JSON records into an explicitly
configured Redis database without overwriting existing values, or runs read-only
MCP checks. Its report distinguishes passed, failed and inconclusive checks.
Credentials stay in environment variables or `.env`, never in the report.

Deployment uses the user's existing Redis Cloud database `sam-test-db` over TLS.
Local JSON round trips and SDK transport tests do not prove service behaviour;
the separate live check uses two shopper-scoped agent keys and the service MCP
endpoint.

## Implementation plan

- [x] Test fixture provenance, JSON shape, relationships and ACL export, then
  implement `seed/shop_context.py`.
- [x] Test seed conflict handling and MCP responses through the SDK's real HTTP
  boundary, then implement `scripts/check_context_retriever.py`.
- [x] Export the schema and verify local Redis JSON reads where available.
- [x] Run the live service checks when the service is configured; record any
  unverified behaviour explicitly.
- [x] Document setup and run focused tests, formatting, lint and type checks.

## Observed on 2026-09-29

The service `camera-shop-context-smoke` is active on `sam-test-db`, with three
entities, 13 generated tools and six isolated JSON fixture records. The two
agent keys were created through the Cloud console with `shopper:alex` and
`shopper:jordan` access tags; they expire on 2026-12-28. Credentials and the actual
MCP endpoint are saved in the ignored `.env`.

All 14 live checks pass. Each key retrieves its shopper, its purchase by ID and
filter, and the shared source product with all expected fields. Foreign filters
return no records. Foreign ID lookups return an explicit access-denied error.
The checker recognizes only the exact observed denial for the requested fixture
key, requires a successful permitted lookup, and rejects error responses with
extra result content.

Live API differences found and handled: primary-key components cannot declare
secondary indexes, and purchase filtering uses `filter_purchase` with
`tag_conditions`. Regression tests cover both changes and ensure generic errors,
denials for another ID, and denials without successful controls cannot pass.

The updated focused suite reports 17 passed and two opt-in Redis tests skipped;
those Redis integration tests passed earlier. Focused lint and type checks pass.
The earlier full Python run reported 223 passed and 30 opt-in tests skipped.
Existing locked dependency versions are unchanged; the SDK remains optional.

The standalone checker does not exercise generated relationship traversal. The
[current chat verification](context-retriever-chat.md#verification) separately
verified the model calling `expand_results` for the Purchase → Product link. The subsequent
[chat integration](context-retriever-chat.md) replaces the adviser's fixture
lookup with live purchase and product reads. This smoke test does not establish
production shopper authentication.

## Sources

- [Redis concepts](https://redis.io/docs/latest/develop/ai/context-engine/context-retriever/concepts/)
- [Redis quickstart](https://redis.io/docs/latest/develop/ai/context-engine/context-retriever/quickstart/)
- [Official Python SDK](https://pypi.org/project/redis-context-retriever/): version
  0.0.6; `ContextModel`, `ContextRelationship`, `export_data_model`, and the
  source distribution's `test_to_entity_dict_with_acl_field_mappings` test.
