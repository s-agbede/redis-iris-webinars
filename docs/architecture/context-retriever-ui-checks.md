# Camera adviser UI verification

This review records the implementation before the generated MCP tool correction.
References below to `get_purchase_history` describe that earlier version. See
the [current architecture and checks](context-retriever-chat.md) for the replacement.

Checked on 2026-09-30 on the `context-retriever` branch. This is a browser and
code-review record, not a guarantee that every generated answer is correct.

## Test environment

The browser exercised the built React UI and production FastAPI adapters with
the real local Redis catalogue, Context Retriever on `sam-test-db`, OpenAI,
Playbook and Redis Agent Memory. A temporary server used a separate RAM owner
prefix so test conversations did not become preferences for the usual demo
shoppers. Controlled server wrappers injected restore, status and purchase-source
failures without changing Cloud configuration or stored order records.

## Confirmed fixes

- Unsupported saved model-context shapes could crash the evidence panel. It now
  validates the fields it renders, displays an explicit readable-view fallback,
  and leaves the raw request available. A regression test first reproduced the
  crash; malformed `{}` context was also checked in the browser.
- A successful session-restore retry left the old failure notice visible. The
  notice now clears when retrying; the browser restored the same conversation
  without the stale message.
- A failed restore followed by a failed status request during retry re-enabled
  the composer. The restore block now remains until the saved session is restored
  or confirmed absent. The browser verified that both the disabled composer and
  retry button survive this sequence, then verified successful recovery.

## Answer-quality findings

Order retrieval worked for both selected shoppers. Alex received the Sony ZV-E10
dated 2026-04-18; Jordan received the JJC hand strap dated 2026-06-03. The displayed
tool outputs matched `SAM-DEMO-1001` and `SAM-DEMO-2001`, respectively. Both answers
labelled the orders fictional and distinguished historical purchase from current
ownership. Asking Jordan's conversation for Alex's orders did not expose Alex's
order. Shopper selection is still a demo control, not authentication.

**Unresolved: technical recommendation prose is not reliably grounded.** In the
microphone recommendation journey, product cards belonged to retrieved results,
but the adviser asserted Sony ZV-E10 audio-port and microphone cable details that
were absent from those results. Stricter source-only instructions did not remove
the problem when earlier incorrect answers were in session/RAM context. A trial
with medium reasoning also retained unsupported assertions, so the final setting
remains low. Higher reasoning is not a demonstrated fix.

A later memory-off recommendation with no earlier turns or retrieved memories
correctly left cable/adapter compatibility unverified and declined to invent
prices or stock. Its product descriptions matched the supplied listings. That
passing case does not erase the failures with earlier incorrect context.

RAM also promoted some assistant-generated technical statements into memories.
This can repeat an earlier unsupported assertion in later answers. Retrieved
memories are useful profile context, but their existence is not independent proof
of a product specification. The application validates product identities; it does
not validate every factual assertion in free-text answers.

The next correctness change needs an explicit evidence contract for technical
claims, backed by sufficient product specification data, and an evaluation that
includes conversations containing earlier incorrect claims. Another prompt-only
change should not be treated as a verified solution. Some replies also exposed
internal product IDs and offered unsolicited recommendations after a profile
correction; these are remaining response-quality issues.

## Browser coverage

| Journey | Observed result |
| --- | --- |
| Blank input, Enter submission, busy state | Blank messages blocked; a submitted turn disables the composer until completion. |
| Alex and Jordan purchase lookup | Correct separate fictional product/date and scoped tool evidence. |
| Cross-shopper request | Jordan's conversation did not disclose Alex's order. |
| Recommendation tools | History then catalogue search; cards matched retrieved products. Technical grounding remains a failure as described above. |
| Session-only correction recall | Recalled Canon EOS R50 and preference for lightweight walking-tour gear; capture contained prior turns and no long-term memories. |
| Memory off | Neither prior turns nor long-term memories were supplied; the model did not recall the Canon camera. Purchase retrieval remained available and returned Jordan's order. |
| New conversation with long-term memory | Correctly recalled Jordan's Canon EOS R50 and lightweight walking-tour preference; capture showed eight Jordan-scoped memories and no previous turns. |
| Price and stock | Explicitly said it could not verify either; no prices or stock values invented. |
| Product-detail link | Opened the recommended Rode VideoMic GO record in a new tab, with matching title/source description and no invented price or stock. |
| Search lab smoke check | Navigation and method controls worked. `sony zv e10` returned five Full-text, Vector and Hybrid results; Basic correctly reported no literal phrase match. Detailed filters/source evidence passed in the live API tests. |
| Retrieval outage and retry | Explicit unavailable message, typed question restored, no added assistant reply; retry succeeded after recovery. |
| Empty history | A controlled `purchases: []` result produced no purchase claim or product card, distinct from the outage response. |
| Session restore and retries | Restored saved turns; controlled failure paths pass after the fixes above. |
| Malformed saved evidence | Readable fallback and raw request remain available; chat does not crash. |
| Memory inspector | Opens, refreshes, captures a baseline, selects an earlier turn, closes on Escape and restores focus to Chat settings. |
| Mobile layout | Chat and inspector checked at 390 × 844; document width remained 390 with no page-level horizontal overflow. Temporary viewport override reset. |

## Readability changes

The Context Retriever adapter now separates purchase-record validation from linked
product loading, leaving the public method to assemble purchases and reuse fetched
products. The model transport separates request construction and answer parsing
from the bounded tool loop. The chat UI uses named props and small turn/card
components; the inspector uses a named snapshot type. Dense JSX and type
declarations were formatted consistently. No application dependencies were added.

## Automated checks

- Python suite: 261 passed, 30 opt-in tests skipped.
- Opt-in catalogue/fixture run against local Redis: 22 passed. A stale assertion
  expecting exactly 2,317 products failed against the valid 2,318-product managed
  catalogue. It now checks that catalogue and health report the same nonempty
  inventory; the source evidence, filtering and ranking assertions remain intact.
- Frontend regression tests: 23 passed.
- TypeScript and Vite production build passed.
- Ruff and mypy passed; existing RedisVL experimental API warnings remain.
- Independent review of the final recovery/evidence changes found no further
  actionable implementation defects. It did not certify generated prose.

The adviser was restarted on port 8000 with the reviewed code. The temporary QA
server and browser tabs were removed after verification. The browser exercise
focused on adviser journeys and read-only product/search navigation; it did not
exercise every management mutation, browser engine or possible model answer.

See [contributor verification commands](../guides/verification.md) and the
[Context Retriever integration record](context-retriever-chat.md).
