# Documentation

## Start here

Want to understand or present the implementation? Follow the
[code walkthrough](guides/code-walkthrough.md) for the reading order and a short live tour.

New to the adviser? Follow the [beginner quickstart](guides/agent-memory-quickstart.md):
connect RAM, Context Retriever and the model, then try a conversation with a check
at each step. You do not need Playbook
or custom memory types.

- [Local development reference](guides/local-development.md): prerequisites, ports,
  search controls, commands and the code map.
- [Advanced memory guide](guides/agent-memory-advanced.md): optional Playbook,
  corrections, custom types and service evaluation.

## Understand the system

- [Search architecture](architecture/search.md): retrieval, indexing and result evidence.
- [Shopping assistant and memory design](architecture/agent-memory.md): conversation flow and external services.
- [Memory follow-ups](architecture/agent-memory-follow-ups.md): known limitations and remaining work.
- [Context Retriever setup and checks](guides/context-retriever-smoke.md): scoped purchases
  and shipments, JSON fixtures and service verification.
- [Context Retriever chat integration](architecture/context-retriever-chat.md): runtime
  flow, failure handling and verification results.
- [Adviser UI verification](architecture/context-retriever-ui-checks.md): browser
  journeys, recovery fixes, code review and remaining answer-grounding issues.
- [Shipment demo verification](architecture/shipment-demo-verification.md): live delivery
  lookups, status changes, shopper isolation and automated checks.
- [Dataset and provenance](guides/dataset.md): source records, selection and licences.
- [Sample passages](guides/sample-passages.md): examples of the indexed data.
- [Verification](guides/verification.md): automated checks and manual verification.

## Run a demo

- [Search comparison](demos/search.md).
- [Production patterns](demos/production.md): freshness, performance and index replacement.
- [Agent memory](demos/agent-memory.md): the core lesson in 15 minutes, after setup.
- [Semantic caching](demos/semantic-caching.md): scoped RedisVL lookup, Jev verification,
  expiry and the production trade-offs in 15 minutes.
- [Context Retriever](demos/context-retriever.md): the missing microphone, live shipment
  lookups, repeatable status changes and shopper isolation.

The [semantic-cache architecture](architecture/semantic-caching.md) describes the
integration boundaries, stored evidence and deliberate freshness limitations.

## Prepare presentation material

- [Search slide brief](presentations/search.md).
- [Production-pattern slide brief](presentations/production-patterns.md).
- [Webinar series constraints](presentations/series-constraints.md).
- [Article draft: What happens after search works?](articles/search-beyond-the-query-draft.md).

## Historical context

These records describe plans or observations at a point in time. Use the architecture
and demo guides above for the current implementation.

- [Repository history](archive/history.md).
- [Search learning audit](archive/search-learning-audit.md).
- [Production planning](archive/production-planning.md).
- [Agent-memory implementation plan](archive/agent-memory-plan.md).
- [Agent-memory rehearsal](archive/agent-memory-rehearsal.md).
