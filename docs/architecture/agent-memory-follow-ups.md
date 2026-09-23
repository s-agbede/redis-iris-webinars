# Memory demo follow-ups

Remaining ideas and known limitations, updated on 2026-09-23.

The goal remains a 15-minute webinar: feel the pain of statelessness, see memory improve the experience, and understand what context reaches the model. The per-reply “What the model saw” inspector is already implemented.

## Prioritise next

1. **Make the memory lifecycle visible.** Add a small expandable status after each turn distinguishing session storage, long-term promotion, and retrieval. Report only what actual service results establish. Do not imply that saving a session event means it has become a long-term memory, or that promotion is immediate. Show pending status only when it is supported by service evidence.

The [beginner quickstart](../guides/agent-memory-quickstart.md#4-try-one-memory-conversation)
now provides a repeatable check for session recall, memory off, cross-session
recall and shopper isolation. Keep that sequence as the starting point for future changes.

## Other improvements to consider

- **Clarify the three memory modes:** “Memory off,” “This conversation,” and “Across conversations.” Make starting a new chat the demonstration of what long-term memory preserves.
- **Make corrections inspectable:** after “I sold my Sony; I now use Canon,” show the previous and current records once service reconciliation completes. Historical ownership can remain useful, but recommendations should use current ownership. Do not simulate reconciliation in application code.
- **Use conversation for profile details:** the onboarding form has been removed. Direct fact writes remain available through the API for evaluation and presenter setup.

## Webinar constraints and unresolved checks

- Prefer lifecycle visibility and the repeatable check over adding more features to the live session.
- Reconciliation may work better as a prepared before/after example: the earlier live rehearsal took roughly 283 seconds. Do not promise immediate completion.
- Keep PII filtering out of the promised demo until the configured store’s behaviour is verified. The earlier test retained a fictional email; this is unresolved, not a working capability demonstrated by this app.

Related material: [runbook](../demos/agent-memory.md), [rehearsal](../archive/agent-memory-rehearsal.md), [design](agent-memory.md), and [implementation plan](../archive/agent-memory-plan.md).
