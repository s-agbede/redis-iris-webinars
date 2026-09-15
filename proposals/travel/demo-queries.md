# The five demo queries

One query per episode, verbatim, against the layered travel corpus. This
document is the domain lock test: if these five beats hold, travel carries
the series; if one collapses, better to know before writing any seed data.

Claims marked **[VERIFY]** are mechanisms I believe but have not run against
real embeddings. They become eval cases the moment the data is loaded —
that is the gate for locking the domain, same discipline as the retail
baseline (where 7 of 33 predicted values were wrong until executed).

Corpus layers, for reference throughout:

| layer | size | source | role |
|---|---|---|---|
| heroes | ~100 destinations | hand-curated, photographed, facts checked | everything that appears on screen |
| bulk destinations | ~2,000–5,000 | Wikivoyage (CC BY-SA 4.0) | the haystack retrieval must beat |
| guide chunks | ~50,000 | Wikivoyage sections, chunked | text-mode territory; where BM25 wins and fails |
| schedules | `direct_months` tag on each destination | authored | seasonal reachability; origin is fixed (Dublin operator) |
| policy docs | fares.md, disruption.md + siblings | authored, invented airline | episode 3's corpus |

---

## Episode 1 — Search

> **"somewhere warm in February, direct from Dublin, not too touristy"**

Run identically in all three modes, then add filters. The order of failure IS
the episode.

**TEXT (BM25).** Two failures, both explainable in one sentence each:

- *Negation*: BM25 has no notion of "not". "not too touristy" scores UP the
  guide chunks most saturated with "touristy" — Playa de las Américas's guide
  says it plainly. Same mechanism as retail's H00003 ("not built for
  sustained rain"), but here the trap is in the query, not the document,
  which is stronger: the shopper set the trap themselves.
- *Vocabulary*: "warm" matches summer prose about anywhere. The words carry
  no month.

Predicted top results: arbitrary bulk-layer guide chunks that happen to
contain "warm", "February", "touristy". The bulk layer supplies text mode's
wrong answers for free — no curation needed. **[VERIFY: exact ranking]**

**VECTOR.** Gets the *intent* — and hands you Santorini. The summary prose is
saturated with sun and warmth because it was written about July, and the
photo on screen makes it look even more correct. 12°C in February, half the
island shut, no direct February service. Meaning is not constraints.
**[VERIFY: Santorini in top 3 for the vector-only run — this is the one
prediction the episode cannot survive losing]**

**FILTERS (orthogonal, applied to any mode).**

```
temp_feb_c >= 17
Tag(direct_months) == "feb"
crowd_level != "overrun"
```

Each clause kills a named decoy — see the table. The app is a Dublin-based
tour operator, so origin is fixed and reachability is one plain tag set: the
months a direct flight runs. The month dropdown does double duty, picking
both the `temp_<month>_c` field and the `direct_months` value.

**HYBRID.** The fusion beat is honest but subtle, and it is the claim I
trust least on paper: Funchal's copy genuinely discusses winter ("winter is
the growing season; nothing shuts"), so BM25 lifts it, while Santorini's
winter-relevant text is negative ("buses... thin out considerably in
winter") — which BM25 scores UP, negation again. If live runs show hybrid
merely matching vector here, the retail lesson transfers unchanged: fusion
is real work, not magic, and the eval scoreboard says so on screen.
**[VERIFY: whole beat]**

### Near-miss table

| decoy | fails on | axes | caught by | layer |
|---|---|---|---|---|
| Santorini | 12°C Feb + no Feb DUB service | 2 | temp filter (route filter redundant) | hero |
| Amalfi | 11°C Feb | 1 | temp filter | hero |
| Lisbon | 14°C Feb — *almost* | 1 | temp filter, barely | hero |
| Playa de las Américas | crowds | 1 | crowd filter | hero |
| Santa Maria (Sal) | connection only, no direct | 1 | `direct_months` (empty) | hero |
| **Agadir** | **service is summer-only** | **1** | **`direct_months` ONLY** | hero |
| Dubai | budget | 1 | price filter | hero |
| Reykjavik | 1°C — control | all | everything | hero |
| Puerto de la Cruz | nothing — legitimate #2 | 0 | — (episode 2's answer) | hero |
| ~4,900 others | not warm / not served / both | — | never surface past retrieval | bulk |

Agadir is the load-bearing decoy: warm (20°C), quiet, walkable, in budget —
fails on exactly one axis, and that axis is a property of the *route*, not
the place. Every other decoy confounds two failures; Agadir isolates one.

The honesty check the table encodes: every named decoy is hero-layer *by
design* (it must be photographable and fact-checked to appear on screen),
but each one must out-rank ~5,000 bulk documents to reach the results panel
at all. Retrieval works for its living; the demo just controls what it finds
when it works.

---

## Episode 2 — Memory

> **"same kind of trip as last time, sometime in February"**

Meaningless query. That is the point — it is how returning customers
actually talk.

**Without memory:** generic warm-places results. Nothing wrong, nothing
right.

**With memory** (facts stored across sessions): travels with a toddler ·
hated the crowds on a prior trip · went to Funchal last February and wants
somewhere new. The agent expands the query into constraints it was never
given today:

```
temp_feb_c >= 17, crowd_level != "overrun", family_suitable == true,
Tag(direct_months) == "feb", destination_id != D0001
```

**The beat: the answer moves from Funchal to Puerto de la Cruz (D0011).**
Same index, same documents, zero writes — only the remembered facts changed,
and the correct answer changed with them. This is the series thesis
("context engine") in a single before/after, the same pattern retail's
petite jacket played. No [VERIFY] needed: it is pure filter logic.

---

## Episode 3 — Policies (RAG where one chunk is a wrong answer)

> **"my flight to Funchal on the 14th was cancelled — can I move to the
> Tuesday flight without paying the change fee?"**

The corpus contains a deliberate two-document conflict, already drafted:

- `fares.md`: Standard fare changes cost **€45** (with a same-day airport
  exception).
- `disruption.md`: if Northwind cancels or delays >3h, **fee rules are
  overridden** — rebooking is free.

**Top-1 retrieval answers confidently and wrongly** ("€45 fee applies"),
because the fare-rules chunk is the best single match for "change fee". The
correct answer requires retrieving *both* documents and letting the
precedence clause in one override the other. This is the policy-RAG
equivalent of episode 1's negation trap: the most relevant chunk is the
wrong answer. Beat: show top-1 fail, widen to top-k with citations, show the
agent reconcile. Invented airline, so the policy text is safe to author
freely — the retail licensing lesson, carried over.

---

## Episode 4 — Caching

> **"is Funchal warm in February?"** … then, minutes later:
> **"what's the weather like in Funchal in Feb?"**

Different tokens, identical meaning. Exact-match caching misses; semantic
caching hits. The receipt (already in the UI: `embed_ms`, now `llm_ms`,
cost) shows the second query collapsing to single-digit ms and zero LLM
spend. The embeddings cache in `app/embeddings.py` has been previewing this
argument since the first commit.

Travel gives this episode something retail could not: **a real TTL
judgement**. Climate normals are stable for decades — cache for a month.
Seat availability changes by the minute — do not cache it at all. "What is
cacheable" becomes a domain-reasoning beat instead of a toggle, and both
examples live naturally in the same app.

---

## Episode 5 — The agent (everything is now a tool)

> **"my Lisbon flight tomorrow just got cancelled — sort me out, I still
> want my week of winter sun"**

Nothing new is built this episode; that is the payoff. The agent composes:

1. **Policy** (ep 3): cancellation ⇒ free rebooking + duty of care — what is
   the customer owed?
2. **Memory** (ep 2): toddler, crowd aversion, budget, where they have been.
3. **Search** (ep 1): warm + February + served from their airport — the
   alternatives, ranked, with each candidate's receipt.
4. **Cache** (ep 4): repeated destination lookups inside the agent loop are
   near-free, visible in the trace.

Output: "You're entitled to a free rebooking. Funchal has seats Tuesday
(direct, 4h05). If you'd rather somewhere new: Puerto de la Cruz — quieter,
and you haven't done it. Here's why." — every clause traceable to a prior
episode's capability.

---

## Verdict this document supports

- Episodes 3 and 5 are **stronger** in travel than their retail equivalents
  (the two-document conflict survives the move unchanged; disruption is a
  real story with stakes); episode 2 matches retail's petite-jacket pattern
  with a warmer story.
- Episode 4 gains the TTL-judgement beat retail lacked.
- Episode 1 carries three risks, all testable in an afternoon once heroes +
  routes + a few hundred bulk destinations are loaded: Santorini must top
  the vector run, text mode's failures must be legible (not just noise), and
  the hybrid beat must survive contact with real embeddings.

Gate to lock the domain: load a minimal corpus (10 heroes + ~300 bulk
destinations + the sample guides), port these five queries into
`eval/cases.yaml`, run `make eval`. Green on the ep-1 [VERIFY] items → lock.
