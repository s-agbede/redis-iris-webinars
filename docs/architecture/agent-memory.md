# Sam's Camera Shop: agent memory design

How the `agent-memory` branch implements the camera adviser. For your first run,
start with the [beginner quickstart](../guides/agent-memory-quickstart.md).
The search and management labs share the same catalogue.

## Experience

The primary page is **Sam's Camera Shop — helping you fulfil your videography
dreams**. A conversational adviser asks one relevant question at a time, recalls
the shopper's camera and interests, searches the existing catalogue, and returns
real product cards with source details. Product IDs and links come from the
catalogue, never from generated URLs. Missing prices, stock and compatibility
evidence remain unknown.

The chat fills the viewport without a site header or promotional intro. Its composer
stays visible beneath the scrolling conversation. One ellipsis dropdown contains
new conversation, shopper selection, memory mode, the
inspector toggle and lab links. The inspector opens on demand and has a close
button; on narrow screens it appears as an overlay.

Two explicitly fictional shoppers make owner isolation demonstrable. Shoppers
share their camera, filming interests and preferences in conversation; Redis Agent
Memory (RAM) extracts facts from the saved events. The direct fact-writing API
remains available for evaluation and presenter setup. A new conversation changes
the session ID but preserves the owner. The selected memory mode controls context
inclusion: none, session only, or session plus long-term. It does not claim to
disable the service's background extraction.

Fictional purchase records reference real bundled products. They are historical
records, separate from current ownership. A sold camera remains a past purchase.

## Memory and evidence

Use the official Python `redis-agent-memory` SDK against the configured service.
Append user and assistant events; retrieve session history before a turn; search
long-term memory with explicit owner and application scope. Credentials stay on
the backend. Session IDs are server-generated and tied to a demo shopper in Redis.

The app never updates memories to manufacture the automatic-reconciliation demo.
The presenter captures a memory snapshot, sends a contradictory ownership event,
then refreshes RAM until the change is visible. Compare IDs and text before/after.
Extraction timing is measured; pending is distinct from failure and success.
Fresh-session recall must not include the correcting transcript.

The optional sensitive-data experiment uses fictional email addresses and configured
RAM exclusions. It is not part of the introductory walkthrough; the earlier rehearsal
retained the fictional email. The inspector
explains the boundary: exclusions act on automatic extraction, not original session
events or direct onboarding writes. Inspect actual records; an empty similarity
search alone is not a passing exclusion test. Onboarding only accepts the three
camera-related fields; it is not a general-purpose PII filtering claim.

Every completed turn exposes the session context and long-term records supplied,
the catalogue query/results, purchase evidence, guidance source/version, and timings.
Memory or model failures are explicit, never replaced with simulated successful
responses. Search remains usable independently when chat is unconfigured.

## Playbook

A narrow optional adapter discovers relevant published FAQs and Skills, loads the
exact Skill version, and records provenance. A bundled camera-adviser instruction
provides the ordinary application system prompt. When no Playbook is configured,
additional guidance context is empty. The system prompt appears once in the
provider's instructions and remains visible under **What the model saw →
Instructions**. The repository includes a publishable camera-adviser Skill package.
Configured Playbook failures are surfaced rather than silently bypassed.

## Architecture

Keep Python/FastAPI and strict React/TypeScript. Use small typed modules for memory
models/client, chat orchestration/model transport, demo purchases and HTTP routes.
Inject adapters for tests. Reuse the existing Searcher and product/photo models.
Keep server session ownership and saved assistant card IDs in namespaced Redis
records, enabling refresh without trusting client-supplied transcripts.

The chat model and RAM credentials are loaded from `.env` by `ShopSettings`.
The default chat model is `gpt-5-mini`. Playbook configuration is optional.

## Verification

Write failing tests first for direct memory writes, owner-scoped recall, session
ownership, context modes, real product-card validation, failure propagation,
purchase ownership and snapshot comparisons. Test SDK and HTTP boundaries with
controlled transports, then exercise the configured live services separately.
Live checks never claim that transport tests prove extraction quality.

A reproducible evaluation/runbook covers onboarding recall, conversational
references, cross-session recall, ownership reconciliation, retained historical
purchase, PII exclusion, second-user isolation and product grounding. Report
individual observations and elapsed times; unresolved asynchronous checks stay
pending or fail at a declared deadline. No fabricated benchmark scores.

## Fifteen-minute session

Complete setup and extraction checks before presenting. The core sequence is
session recall, memory off, recall in a new conversation, shopper isolation, then
one useful recommendation. See the [presenter runbook](../demos/agent-memory.md).
Corrections, Playbook, custom types and exclusion testing are
[advanced follow-ups](../guides/agent-memory-advanced.md).
