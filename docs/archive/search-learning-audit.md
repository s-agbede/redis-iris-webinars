# Camera search learning audit

Checked on 2026-09-14 against the running app at http://127.0.0.1:8001/.

## Learning acceptance

The implemented flow lets an engineer answer these questions using actual results:

| Question | Verified interaction / evidence |
|---|---|
| How do the methods rank the same product? | `sony zv e10`: the white ZV-E10 is product #1 in full-text, #5 in vector and #1 in hybrid. Its shared panel still shows #5 when only three products are visible. |
| What was actually indexed and retrieved? | Each method shows its own winning passage; expanded indexed text includes bounded title, brand and color context. Original source expands separately with the seven verbatim fields and revision. |
| Why did hybrid give this passage its score? | ZV-E10 title: native score 0.0308861962461; verified reconstruction `1/(60+1) + 1/(60+9)`. Product rank #5 is not substituted for vector passage rank #9. |
| Does a natural-language query guarantee a suitable product? | `a compact camera for filming myself`: full-text's first result is a Manfrotto video head, vector's is a Vmotal camcorder, hybrid's is an AbergBest camera. Engineers must read the evidence and assess the need. |
| Are words in a query hard constraints? | `sony camera for vlogging with interchangeable lenses`: initial visible results include Canon, MELCAM and Keculbo. Applying Sony keeps the query unchanged and makes every returned brand Sony; removing it restores the baseline. Mount compatibility is still not a hard constraint. |
| Is an absent result the same as a failed search? | Nonsense token `zzqxabsenttoken931` gives a successful empty lexical list. A query of 256 repetitions of `a ` followed by `sony` exceeds the local model limit; lexical results remain usable while vector/hybrid say unavailable. |
| What do the timings establish? | Architecture details separate shared embedding, Redis round trips, evidence processing and sequential wall time. They explicitly exclude p95, throughput under load and index freshness. |

These are authored teaching scenarios, not new relevance judgements. Actual top-five
results for seven scenarios are preserved in `eval/learning-observations.json`.
This is an implementation and rehearsal audit, not an audience comprehension study.

## Browser checks

- **Desktop, 1280 × 900:** three columns, three compact cards per mode; all nine
  cards can be compared in one scrolled viewport. No horizontal page overflow.
- **Mobile, 390 × 844:** all-method product-rank matrix and one active list. Arrow
  keys switch method tabs and move focus correctly. No horizontal page overflow,
  including expanded source JSON. The normal app viewport after resetting the
  override was 382 × 745 and also passed the overflow check.
- **Three/five toggle:** changes visible cards using the same fetched response;
  recorded method timings remain unchanged. A selected product beyond the visible
  three is still explained from the fetched five.
- **Selection and return:** selecting a card or matrix row focuses its shared
  evidence heading. Escape/Close returns to the source control. After selecting
  #4 and reducing to three, focus falls back to a visible results control. After
  selecting a mobile vector card and switching to full-text, focus returns to
  the selected product's visible matrix row.
- **Source fidelity:** expanded white ZV-E10 source retains missing description,
  original bullet points, seven fields and source revision. Its local image loads
  with the body/lens caption, Solomon203 attribution and CC BY-SA 4.0 link.
- **Partial failure:** the real overlong-query example retains full-text results,
  shows N/A in the matrix and Unavailable in evidence, and prints “Command not
  run” with the model-limit error for vector/hybrid.
- **Empty lexical list:** remains distinct from a service failure. Hybrid has
  no lexical contribution when the lexical expression has no matches.
- No browser console warnings or errors were observed during these checks.

## Automated checks

- Python suite: **41 passed**, one opt-in integration test skipped in the ordinary
  run. The opt-in live Redis/local-model test was then run explicitly and passed.
- Focused evidence/search/live run: **16 passed**. Includes literal overlap offsets,
  native fusion arithmetic, ambiguous ties, absent branches, duplicate product
  passages, shared embedding, identical filters and warning-bearing hybrid errors.
- Frontend: **11 tests passed**, covering request cancellation/error boundaries,
  rank visibility, shared selection, product unions and Unicode offset rendering.
- Strict TypeScript/Vite build, Ruff and mypy passed.
- **Seven before/after live comparisons:** identical ordered product IDs and scores
  within absolute tolerance `1e-12`, across all modes, including Sony filtering
  and a query with no lexical matches.

Commands for repeat verification are in README. Re-run browser checks after any
change to selection, filters, evidence rendering, result counts or layout.

## Review findings resolved

1. Closing an inspector could lose focus if its selecting card was hidden or
   removed. Added visible product/matrix/control fallbacks and reproduced both
   failure paths in the browser after the fix.
2. A method skipped after embedding failure could display an empty command block
   under text implying execution. Command traces now distinguish executed,
   attempted and not-run commands; verified with a real model-limit failure.
3. The constraint guidance referred to a filter “below” even though it appears
   above the next step. Removed the directional wording. Context documentation
   now includes color as well as title and brand.

## Evidence limits to preserve

The tested Redis 8.6.2 JSON index rejects native `HIGHLIGHT`. Highlighted spans
therefore show explicitly labelled literal query-word overlap, excluding
query-time stopwords; they are not engine match offsets or BM25 attribution.
Stemming may produce matches that these annotations do not highlight.

Native `FT.HYBRID` scores remain authoritative. The app requests raw branch-score
aliases and the complete candidate union in the same execution. It publishes
component passage ranks only when their uniquely reconstructed arithmetic agrees
with the native fused score. Ambiguous explanations remain unavailable; native
warnings or incomplete unions become mode errors. This is not native
`EXPLAINSCORE` or product-level RRF.

Future context retrieval, memory and semantic caching episodes can reuse product
IDs, source revisions and passages. Those capabilities are not implemented here.
