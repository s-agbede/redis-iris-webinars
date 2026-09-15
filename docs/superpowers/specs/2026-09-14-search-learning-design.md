# Search learning experience

The user approved the five improvements discussed in the conversation and asked for implementation with an explicit developer-experience check. Continue without another design gate. Preserve existing uncommitted camera-lab work and its local models, source records, image credits and native Redis hybrid retrieval.

## Learning outcome

An engineer can inspect one product across full-text, vector and hybrid, explain what was retrieved, distinguish relevance words from eligibility filters, and choose a next experiment.

## Interaction

- Three compact results per method initially; an explicit toggle reveals the five fetched products. Same query, source passages and brand filter across modes.
- Three guided authored examples: exact model `sony zv e10`, intent `a compact camera for filming myself`, and constraints `sony camera for vlogging with interchangeable lenses`. Each has a learning objective and a next action; examples begin with no brand filter so their baseline is reproducible.
- Explain the selected brand as a hard eligibility rule. Provide a visible way to apply/remove Sony for the constraint experiment, preserving query text and rerunning the same comparison.
- Clicking any result selects that product and opens one inline shared evidence panel. It shows all three product ranks, per-method winning passages, lexical highlights, vector similarity, and hybrid passage-fusion evidence. Source record and full technical commands are expandable.
- Small screens keep a rank comparison matrix visible and use method tabs for detailed ranked lists. Do not stack three long lists. Controls work by keyboard, have selected states, and do not erase context or move focus unexpectedly.
- Keep photos secondary with existing attribution; missing photos do not occupy large blank cards.

## Evidence contract

Search hits gain indexed text (including title/brand context), explicitly labelled literal query-word overlap spans, a one-based passage rank before product deduplication, and optional fusion evidence. Never infer why an embedding matched. Describe the actual passage and cosine score, with a note that similarity does not establish compatibility or correctness.

The live Redis 8.6.2 check rejects HIGHLIGHT on this JSON index. Literal overlap is an application annotation, not engine-reported match offsets or a BM25 explanation; Redis stemming can match additional words. Preserve the JSON index and retrieval behavior.

Native FT.HYBRID remains authoritative. Probe its component score aliases and rank support; only label RRF decomposition verified when it can be reconciled with native output. Missing or unreconstructable evidence is explicitly unavailable. Do not substitute product ranks into a passage RRF formula. Tests cover ties, absent candidates, partial mode failure and nonmatching terms.

Timing separates embedding, retrieval round trips and explanation work. Architecture details explain that single sequential queries do not measure p95, throughput, freshness or performance under load.

## Acceptance

Run exact, intent and constrained examples against live Redis/local embeddings; inspect one product across all modes; demonstrate lexical words versus brand filter; inspect RRF arithmetic; validate empty results, partial failure, stale-request cancellation and unchanged source fidelity; test keyboard and desktop/narrow layouts; record a final learning-workflow audit with evidence and limitations.
