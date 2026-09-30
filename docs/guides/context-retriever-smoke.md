# Context Retriever setup and service checks

The adviser retrieves purchase history, linked product details and shipment status from
Context Retriever. This guide configures the service and checks its shopper
isolation independently of the model. The standalone check needs no LLM calls.
Catalogue search continues to use the local Redis search index. Keep its
`REDIS_URL`/`REDIS_PORT` separate from the service database's `CTX_REDIS_URL`.

## 1. Inspect the model and data locally

```bash
uv sync --extra context-retriever
uv run --extra context-retriever python -m scripts.check_context_retriever export \
  --output /tmp/camera-context-fixtures.json
```

The export contains the entity model and eleven JSON documents. The source is
[`seed/shop_context.py`](../../seed/shop_context.py):

| Entity | Redis key template | Access |
| --- | --- | --- |
| Shopper | `camera:context-smoke:shopper:{shopper_id}` | Matching `shopper` access tag |
| Purchase | `camera:context-smoke:purchase:{order_id}` | Matching `shopper` access tag |
| Product | `camera:context-smoke:product:{product_id}` | Shared source/demo product data |
| Shipment | `camera:context-smoke:shipment:{shipment_id}` | Matching `shopper` access tag |

Shopper links to its purchase IDs. Purchase links to a shopper, product and
shipment. The Sony and strap products preserve their bundled source JSON.
`MIC-DEMO-01` is an explicitly fictional RØDE VideoMicro II demo record, not a
verified source listing. Alex has `SAM-DEMO-1001` and `SAM-DEMO-1002`; Jordan has
`SAM-DEMO-2001`. These purchases do not prove ownership, compatibility, price or stock.

## 2. Connect a service

Use an existing service, the [Redis Cloud setup](https://redis.io/docs/latest/operate/iris/context-retriever/create-service/),
or the [self-managed setup](https://redis.io/docs/latest/operate/iris/context-retriever/self-managed/).
The ordinary Redis Docker container is only a database; it does not run the
Context Retriever service. The service must reach the database containing the
fixtures. A Cloud service cannot use this laptop's `localhost` database.

The [official quickstart](https://redis.io/docs/latest/develop/ai/context-engine/context-retriever/quickstart/)
explains surface creation with `ctxctl surface create --models`. For this
experiment use `--models ./seed/shop_context.py`. The exported `data_model` is
also suitable for the SDK's surface creation request. The SDK is pinned to
0.0.6; check the deployed service's accepted schema before creating the surface.

For an SSO account, sign in through the Redis Cloud console. The installed
`ctxctl auth login -u ...` uses direct email/password authentication and does not
complete the browser SSO flow. Generate an admin key under **Context Retriever
→ Admin Keys** and save it as `CTX_ADMIN_KEY` in the ignored `.env`. If the
account has no services yet, the console may require creating the first service
before displaying the Admin Keys tab. Save the created service ID as
`CTX_SURFACE_ID`. These are setup credentials; agent reads use scoped agent keys.

The live API rejects `redis_indices` on a field marked `is_key_component`.
Keep the Shopper primary key unindexed; Purchase's non-key `shopper_id` retains
its TAG index for filtering.

On **Shopper, Purchase and Shipment**, the model explicitly includes:

```json
{"acl_field_mappings": [{"document_field": "$.shopper_id", "access_tag": "shopper"}]}
```

Create separate agent keys on that surface, with these access tags:

- Alex: `{"shopper": ["alex"]}`
- Jordan: `{"shopper": ["jordan"]}`

The console's **Agent Keys → New Agent Key** form supports these tags. Add a tag
named `shopper`, enter the corresponding value, and finish editing the value
before generating the key. The console defaults to a 90-day expiry. Copy each
new key when shown; the list only displays masked values afterwards.

The CLI's agent creation command supports `--access-tags`. The SDK's lower-level
`ContextSurfacesClient.create_agent_key` accepts `CreateAgentKeyRequest` with
`access_tags`; the 0.0.6 `UnifiedClient.create_agent_key` convenience method does
not expose that argument. An agent key's tags and the entity field mapping are
both required; declaring a TAG index alone does not establish isolation.

Put the following in your ignored `.env` file, using the service's actual values:

```dotenv
CTX_REDIS_URL=rediss://default:password@host:port
CTX_MCP_URL=https://your-service/mcp
CTX_ALEX_AGENT_KEY=your-alex-scoped-key
CTX_JORDAN_AGENT_KEY=your-jordan-scoped-key
```

Admin credentials are only needed to configure the service. The check command
uses the two agent keys. Keep secret values out of reports and source control.

## 3. Upgrade an existing demo

For the existing `camera-shop-context-smoke` surface, keep `CTX_ADMIN_KEY` and
`CTX_SURFACE_ID` configured for publishing. Run:

```bash
make context-migrate
make context-publish
make context-check
```

Migration accepts only the exact original six records or the new fixtures,
creates the missing records, and refuses any conflicting value before writing.
Publishing updates only the model and saves the previous model to
`/tmp/camera-context-model-before.json`; credentials and data source are preserved.
The command refuses a surface with another name, entity set or key prefix.

For a newly created surface using the new model, seed and check with:

```bash
make context-seed
uv run --extra context-retriever python -m scripts.check_context_retriever check \
  --output /tmp/camera-context-report.json
```

Seeding writes Redis JSON directly, matching the app's storage format. It watches
all eleven keys and refuses to replace any differing record; a second identical
run verifies the existing records and creates nothing. It never seeds the live
catalogue prefix. The keys remain available for inspection and subsequent checks.

The read-only check discovers tools independently for each agent key, validates
the inputs against their returned JSON schemas, then performs 27 probes:

- Retrieve each shopper and all their purchases and shipments, using filters
  and individual ID lookups. Missing, duplicate or changed fixture rows fail.
- Follow the returned purchase fixture's product ID to the shared product lookup
  and compare all source fields. This checks linked IDs; generated relationship
  tools are not exercised yet.
- Attempt to retrieve the other shopper, purchases and shipments by ID and
  the other shopper's purchases and shipments by filter.

**Pass** requires the expected permitted records and empty foreign results.
For ID lookups, the checker also accepts the live service's exact `access denied:
document not found` error for the requested fixture key, with no extra result
content. Both empty results and explicit denials remain inconclusive if the
corresponding permitted lookup failed. Generic tool errors, unavailable tools,
schema changes and unknown result formats remain inconclusive.

The live service exposes `filter_purchase` with
`tag_conditions=[{"field": "shopper_id", "value": "alex"}]` (or `jordan`),
rather than a separate filter tool for each field. The checker validates these
arguments against the discovered tool schema before calling it.

The report includes discovered tool schemas, input arguments, returned IDs and
timings. Exit codes: `0` all probes passed, `1` failed or inconclusive probes,
`2` missing configuration or an execution error. No successful live result is
claimed until this command runs against the configured service.

## 4. Use it in the adviser

The backend requires `CTX_MCP_URL`, `CTX_ALEX_AGENT_KEY` and
`CTX_JORDAN_AGENT_KEY` alongside its Agent Memory and model settings. Restart
`make serve` after saving them. Admin credentials and the direct database URL
are only used during setup and seeding; chat and the read-only check use the scoped keys.

Select Alex, start a new conversation and ask “What camera did I buy here, and
when?” Repeat with Jordan in a new conversation. In **What the model saw**, check
the generated definitions under **Available tools** and actual MCP calls under
**Tool calls** (for example, `filter_purchase` or `get_purchase_by_id`, then
`get_product_by_id`). The model chooses the sequence; the application does not
preselect it. Alex should receive
`SAM-DEMO-1001` dated 2026-04-18 and the microphone order `SAM-DEMO-1002` dated
2026-09-22; Jordan should receive `SAM-DEMO-2001` dated
2026-06-03. Product descriptions come from the service's linked product records.

At the beginning of each turn, the backend calls MCP `tools/list` with the
selected shopper’s key. It forwards each generated name, description and input
schema to the model alongside local `search_catalogue`. Each model-selected
call is validated against that schema and sent through MCP `tools/call`.
The backend validates the session owner and binds the key independently of
model arguments. An ID or filter cannot change the credential’s access scope.
History remains available in every memory mode. RAM still supplies session
messages and long-term preferences; a past purchase does not prove ownership.

An empty result stays empty. Known unindexed-filter errors can be corrected by
the model, while missing/denied IDs produce a neutral “no accessible record”
outcome. Expired keys, timeouts, malformed records and foreign shopper data return
a Context Retriever error before conversation events are saved. There is no local history fallback. The model has a six-call
budget and receives pagination metadata; it must disclose any partial results. Renew scoped keys before their configured expiry.

See the [chat integration design](../architecture/context-retriever-chat.md)
for the runtime adapter and verification details.
The [presenter walkthrough](../demos/context-retriever.md) covers both shoppers,
the missing-microphone question, shipment freshness, accessory recommendations
and a current-ownership correction.

The eleven records are seeded fixtures. There is no automatic purchase ingestion or
synchronization from **Manage shop** into the retriever's product records.

## Verification

```bash
make context-test
uv run --extra context-retriever pytest tests/test_shop_context_retriever*.py tests/test_shop_mcp.py -q
# Use an isolated test database URL or your local demo Redis:
TEST_REDIS_URL=redis://localhost:6379 make context-test
```

Transport tests use the real SDK with an HTTP test transport. They verify our
client and report logic, not Redis service enforcement. The opt-in Redis test
creates unique temporary keys, verifies JSON round trips and conflict handling,
and deletes only its own keys. Neither test proves live Context Retriever access
control. Demo shopper selection also remains unauthenticated in the main app.
