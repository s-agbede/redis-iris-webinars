# Advanced agent-memory examples

Complete the [beginner quickstart](agent-memory-quickstart.md) first. These are
optional extensions; they are not prerequisites for chat or cross-session recall.
Use fictional details throughout.

## Playbook guidance

Playbook supplies published instructions for the adviser. Memory supplies facts
about the shopper. The app works with its built-in instructions when Playbook
is not configured.

This repository does not start the separate Playbook demo service. If you have
access to that service, start its UI adapter and data plane, then run:

```bash
uv run python -m scripts.setup_shop_playbook
```

The defaults are adapter `http://127.0.0.1:18080/demo/api` and data plane
`http://127.0.0.1:9301`; use `--adapter` and `--data-plane` for other ports.
The script publishes the bundled camera-adviser Skill in a dedicated playbook
and writes `SHOP_PLAYBOOK_URL`, `SHOP_PLAYBOOK_ID` and `SHOP_PLAYBOOK_API_KEY`
to `.env`. It preserves a complete existing configuration and resumes an
interrupted setup from its private checkpoint. Restart the backend afterwards.

All three settings must be supplied together. Configured service errors are
reported rather than silently replaced with local instructions. For a completed
reply, inspect the guidance entry ID and version under **What the model saw**.
This example pins one published Skill; it does not benchmark semantic discovery.

## Changing an existing fact

**Reconciliation** is the memory service deciding how a new fact relates to what
it already knows. For example, current camera ownership changes when Alex sells
one camera and buys another.

1. In Alex’s memory inspector, verify the existing Sony ownership fact and click
   **Capture before**.
2. Send “I sold my Sony ZV-E10 and no longer own it. My only camera now is a Canon
   EOS R50.”
3. Enable **Refresh every 10 seconds**. Compare the actual record IDs and text
   after background extraction runs.
4. Once the change is visible, start a new conversation as Alex, select
   **Short-term + long-term**, and ask which camera Alex owns.

The acknowledgement in chat only shows the adviser read the correction. A record
with the same ID and changed text is an update; a new ID is an addition. A historical
Sony fact can remain useful, but should not assert current ownership. The app does
not manually update records to manufacture this result. If the service has not
processed the correction, report it as pending. The
[earlier rehearsal](../archive/agent-memory-rehearsal.md) took roughly five minutes;
use a prepared before/after example when presenting to a fixed time limit.

## Custom memory types

The first exercise uses built-in memory types. Custom types let you choose
structured fields for a particular use case; the app’s conversation prompt does
not create those types in Redis Cloud.

For the custom-memory demonstration, use a fresh shopper prefix. Keep
short-term plus long-term memory enabled and
stay in the same conversation while the adviser asks relevant questions. The
application's adviser prompt gathers useful details for `owned_gear`,
`shooting_profile` and `purchase_intent`, one question at a time. It reuses supplied
facts and respects skipped questions; it does not need every field to recommend.

Rehearse a natural exchange such as this; actual questions can vary:

| Speaker | Example |
| --- | --- |
| Shopper | I want better audio for my videos. |
| Adviser | What camera will you use the microphone with? |
| Shopper | My Sony ZV-E10. |
| Adviser | What do you mainly film? |
| Shopper | Walking tours outdoors. |
| Adviser | What matters most about the microphone for those walks? |
| Shopper | Keeping it compact and cutting wind noise. |
| Adviser | What maximum budget and currency should I keep in mind? |
| Shopper | Up to 150 GBP. |

The app records both questions and answers as ordered session events. Short
answers therefore have conversational context. Redis extracts memories in the
background on the configured cadence, rather than after each field is answered.
Observe the actual records and attributes before claiming a complete custom
memory or a durable update; this prompt change does not configure the cloud
memory types or establish their merge behavior. The catalogue has no prices, so
the adviser cannot promise that a recommendation meets the remembered budget.

Add the following instruction to each custom type's extraction prompt when
configuring it in Redis Cloud:

> Use the provided conversation context to interpret short answers to preceding
> questions. Extract only facts the shopper states or unambiguously confirms.
> Assistant questions, suggestions and hypothetical examples are not evidence
> that the shopper has a preference or owns equipment. Do not invent missing
> field values to complete a record. Keep separate shopping goals and recipients
> distinct, and preserve the scope of explicit corrections.

Check partial-information cases in the configured service before the webinar;
the available schema and extraction behavior determine how absent fields are
represented. Inspect structured attributes through the API because the current
shop memory boundary exposes record text and identity, not custom attributes.
See the [Redis developer guide](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/developer-guide/#define-custom-memory-types).

## Sensitive-data exclusions: a separate experiment

Do not promise this as part of the introductory webinar. The
[earlier rehearsal](../archive/agent-memory-rehearsal.md) retained a fictional email,
so the repository does not establish that the configured store excludes it.

Before testing, configure the service’s Email address detector if that feature
is available for your account. A possible fictional test message is:

> My fictional contact email is alex-camera-demo@example.invalid. I prefer purple camera straps with tiny yellow ducks.

Wait for the useful preference to be extracted, then inspect the full memory
inventory. An empty similarity search alone is insufficient evidence. Original
session events retain their content; exclusions apply to automatic extraction,
not direct memory writes. See the
[Redis exclusion guide](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/developer-guide/)
for the service’s limits. Do not use real personal details for this experiment.

## Repeatable live RAM evaluation

This is an advanced service evaluation, not the beginner setup check. It writes
fictional fixtures to your configured cloud store and tests correction and
exclusion behaviour as well as recall. An exclusion failure does not, by itself,
mean basic session memory is unavailable.

The evaluator creates new owner and session IDs on every run. It writes one initial Sony onboarding fact, then submits the Canon correction and fictional-email/preference pair as session events. It does not call the model, update memories, change service exclusions, or alter Alex/Jordan's presentation data.

```bash
uv run python -m scripts.evaluate_shop_memory \
  --timeout 420 \
  --poll-interval 10 \
  --output /tmp/shop-memory-evidence.json
```

The JSON file is updated after setup stages and each poll. It contains the initial records, submitted event IDs/text, every full paginated inventory, elapsed times, second-owner inventory and semantic recall, and empty new-session context. In-flight service requests may finish after the polling deadline.

- **Confirmed / exit 0:** Every check has direct evidence. Automatic reconciliation requires unambiguous Canon ownership and no remaining Sony record; exclusion requires an affirmative useful preference plus absence of the email and its unique local marker.
- **Failed / exit 1:** A leak, isolation failure, unexpected new-session context, or service error was observed. A later clean snapshot cannot erase an earlier leak.
- **Pending or manual review / exit 2:** Extraction has not produced enough evidence, or natural-language wording needs inspection. The evaluator deliberately refuses to infer success from negations, qualified claims, or historical Sony records.

The exclusion verdict covers **record text across the observed inventory**. The app's memory boundary does not expose structured custom-memory attributes, so inspect those separately if your store extracts them. A single fictional-email observation does not establish general PII safety or guarantee that later extraction will remain clean. Exclusions act on automatic extraction: original session events retain their content, and direct onboarding writes are not filtered by those exclusions. [Redis developer guide](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/developer-guide/).

Complete the browser smoke checks separately: new-session recall with empty prior context, “the second one” product reference, a fictional purchase with real catalogue links, and published Skill provenance. Generated recommendations remain limited by the catalogue; prices, stock and compatibility are not guaranteed.

## Inspect the exact model request

Under any new reply, expand **What the model saw**. It shows the captured answer
request, including full instructions, session events/summary, retrieved memories,
the current message, optional Playbook context, and each retrieval tool call with
its arguments and result. The raw provider JSON body is available below the
readable view. The application uses native function calling; there is no separate
search-planning request. Provider reasoning is not exposed as readable text.

Ask the same ownership question with memory off and on, then open both replies.
The off reply explicitly shows no previous turns and no long-term memories.
Changing the current mode does not alter either historical request. Replies from
before this feature show an unavailable-capture notice; they are not reconstructed.
The request body is saved alongside the local conversation (seven-day session
retention), without authorization headers, and is not printed to application logs.
Use fictional details for this teaching view.

## Demonstrate the two retrieval tools

The adviser chooses whether to call these Python-backed tools during a turn:

| Tool | Behavior |
| --- | --- |
| `get_purchase_history()` | Returns fictional orders for the current demo shopper, including dates and actual catalogue products. The backend supplies the shopper identity; the model cannot select another shopper. Orders are historical evidence, not proof of current ownership. |
| `search_catalogue(query)` | Runs the existing hybrid keyword and semantic search and returns up to five catalogue products. The model can refine its query using earlier tool results. Products have descriptions and links, but no prices or live stock. |

As Alex, ask **“Find a microphone for the camera I bought here.”** Open **What the
model saw** to inspect the expected sequence: purchase history, a search informed
by the purchased Sony ZV-E10, then the reply. Model decisions can vary; show the
actual recorded calls. A greeting or conversation ending can produce a reply
without retrieval.

Calls execute sequentially, with at most three tool calls followed by a final
answer request that disables further calls. Invalid names or arguments and
unavailable retrieval fail explicitly. An empty successful result is distinct
from a service failure. Product cards are checked against the supplied evidence,
including earlier searches in the same turn. Redis Agent Memory reads and event
writes remain automatic around the model loop.

See [verification](verification.md) for local checks and their limits. A live
rehearsal calls your configured external services; transport tests do not establish
live extraction quality or model behaviour.
