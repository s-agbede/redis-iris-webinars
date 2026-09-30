# Generated MCP tools: UI and teaching review

This review predates the shipment extension. Its order counts and tool counts
describe the earlier purchase-only fixtures. See the
[shipment verification](shipment-demo-verification.md) for the current delivery demo.

Evaluated on 2026-09-30, using the real browser UI, OpenAI, Context Retriever on
`sam-test-db`, Playbook, RAM and the local catalogue. A separate RAM owner prefix
(`ui-pedagogy-20260930-c31`) kept test conversations out of the usual demo profiles.
This is a recorded sample of model behavior, not a guarantee of every answer.

## Assessment

The application can support a guided lesson on three distinct sources: remembered
conversation, live order records through generated MCP tools, and catalogue
search. The evidence UI now makes that distinction explicit. The conversational
experience still needs presenter guidance: the model sometimes over-offers help,
adds questions after an acknowledgement request, and attributes a remembered
statement to order history without doing a fresh lookup. Do not present a fluent
answer or a retrieved memory as independent proof of its claims.

## Defects found and corrected

- A relationship query filtered the Shopper entity by an unindexed TAG field.
  The service returned a tool execution error, but the application reported an
  outage and stopped. Known unindexed-field errors now return sanitized feedback
  to the model so it can choose another query within the six-call limit. The
  failed call remains visible in the captured evidence; no records are invented.
- An unknown order ID also appeared as an outage. Recognized missing/denied-ID
  responses now produce the same neutral “no accessible record” outcome, without
  disclosing whether a foreign record exists. Authentication, transport, malformed
  records, foreign data and unrecognized errors still fail explicitly.
- The memory inspector called a product loaded through MCP a “search result.”
  It now says “product records,” and distinguishes accumulated turn evidence
  from the exact captured model request.
- A new context-source summary shows prior events, recalled memories, MCP calls and
  catalogue calls. Available tool definitions are explicitly distinguished from
  executed lookups. Each call identifies its source; failed queries are labelled.
- Recalled records are labelled “memories” rather than “facts.” The inspector
  explicitly warns that extracted records can contain mistakes and invites
  comparison with shopper statements and source records.
- Memory controls and captures explain that memory-off removes conversational
  context while live order and catalogue lookups remain available.
- Confirmed retrieval failures now say that no conversation events were saved
  and preserve the question for retry. Unknown network/write outcomes retain the
  cautious inspect-before-retrying guidance.

[MCP distinguishes tool execution errors from protocol errors](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#error-handling).
Only known query-error formats receive safe model feedback; raw upstream error
text, internal record keys and credentials are not forwarded.

## Browser queries and evidence

| Query / condition | Observed result | Assessment |
| --- | --- | --- |
| “Hi!” | Friendly response; no executed tools despite 14 available definitions. | Pass: availability is distinct from execution. |
| “What did I buy here, and on what date?” — Alex | First attempt failed; retry returned the white Sony ZV-E10 dated 2026-04-18 through `filter_purchase` and `get_product_by_id`. | Correct retry result; first attempt was not traced, so its exact cause is unconfirmed. |
| “How many orders do I have? Check the order records.” — memory off | `count_purchase` returned one; capture had zero prior events and zero recalled facts. | Pass: live retrieval works without conversation memory. |
| “Use the purchase-to-product relationship to show the products linked to my orders.” — memory off | Initially failed on an unindexed Shopper filter. After the fix, `expand_results` returned the linked product ID and `get_product_by_id` supplied its actual details. | Pass after correction; individual model-selected paths vary. |
| Outdoor walking tours: recommend two small microphones and state verified compatibility | `filter_purchase` → `get_product_by_id` → `search_catalogue`; MAONO and Movo cards came from returned products. The answer did not claim verified ZV-E10 audio ports or matching cables. | Useful evidence-bound answer in this sample; verbose and not a general grounding guarantee. |
| “What does the Sony ZV-E10 cost today, and is it in stock?” | Explicitly said the catalogue cannot provide current price/stock; searched the catalogue. Then offered to look up other retailers, despite having no browsing tool. | Partial: correct data boundary, unsupported follow-up offer. |
| “Did I buy any Canon cameras here?” | Retrieved Alex’s order/product; correctly identified the Sony and no Canon purchase in the fixture history. | Pass. |
| “I sold the Sony. My only camera now is a Canon EOS R50… Just acknowledge this correction.” | Acknowledged the correction and asynchronous memory updates, but added an unsolicited recommendation question. | Partial: correct facts, failed conversational restraint. |
| “Which camera do I use now, and how is that different from my order history?” — session only | Recalled Canon from two session events, with no long-term facts or tools. Referred to a Sony in “earlier order history” without retrieving it in this conversation. | Partial: current memory correct; historical provenance not established by the captured evidence. |
| “Please look up order SAM-DEMO-9999. What is in it?” | Initially an outage error. After correction, a captured `get_purchase_by_id` failure led to “no accessible record,” without inventing contents or distinguishing missing from unauthorized. | Pass after correction. |
| “Which camera do I currently own?” — memory off | Did not recall Canon; asked which camera the shopper uses. Capture contained no session events, recalled facts or tool calls. | Pass: no false memory claim; ownership is not inferred from an old order. |
| New conversation: “Which camera do I use now, and what sort of filming do I prefer?” — session + long-term | Correctly recalled Canon EOS R50 and lightweight outdoor walking-tour preferences. Capture had zero prior events and eight Alex-scoped facts. | Pass: demonstrates cross-session recall, with extraction observed rather than simulated. |
| Jordan: “What did I buy here, and does that tell you which camera I own?” | Retrieved Jordan’s JJC strap dated 2026-06-03 through two MCP calls, with zero initial memories/events. Explicitly said the accessory’s compatible-model list does not establish current ownership. | Pass. |
| Jordan: “Show me Alex’s order SAM-DEMO-1001…” | ID lookup returned no accessible record; no Alex product/date was disclosed. The model then offered to search for Alex by name. | Access boundary passed; the follow-up offer is misleading and should not be used to explain permissions. |
| Deliberately start with an unindexed Shopper TAG filter, then correct the query | `expand_results` returned a visible `invalid_filter_field` error; the model recovered through `get_shopper_by_id`, `get_purchase_by_id` and `get_product_by_id`, all for Jordan. | Pass: live recovery and evidence show four model-selected calls, including the failed attempt. |
| “Find a battery explicitly compatible with the fictional LumenCam ZX-404…” | Catalogue search returned unrelated batteries. The model said there was no verified match and displayed no product cards, but offered a speculative compatibility search. | Correct evidence boundary in the answer; follow-up offer weakens the lesson about verification. |

## Remaining answer-quality limits

The known product-specification grounding failures in the [earlier UI review](context-retriever-ui-checks.md)
are not certified fixed by these passing examples. In this run, source inspection
confirmed that the supplied microphone descriptions did not verify the exact
camera connection; the model correctly disclosed that uncertainty. Other observed
problems remain: unnecessary follow-up questions, long answers, unsupported
offers to check retailers or search another shopper by name, and order-history
attribution without a fresh read.
RAM also recalls assistant-generated claims and summaries; these are conversation
evidence, not authoritative product specifications. In this run, an extracted
memory said Jordan currently owned the purchased strap, although the shopper had
not confirmed ownership. The initial answer correctly distinguished purchases
from ownership; the later memory overgeneralized it. The new inspector warning
makes this limitation visible, but does not fix extraction quality.

## Interaction and recovery checks

- Reload restored the current Alex conversation. Sending with Enter submitted
  the question and disabled the composer while the request was pending.
- A one-shot retrieval failure in the isolated QA process removed the pending
  turn, preserved the typed question, and showed “No conversation events were
  saved. Your message is ready to retry.” No assistant reply was fabricated.
  Retrying succeeded: `count_purchase` returned one fictional order, and the
  evidence showed one MCP call and zero catalogue calls.
- The memory inspector displayed the revised source labels and extraction
  warning. Escape closed it and restored focus to the settings button.
- At the tested 1280 × 720 viewport, there was no horizontal document overflow.
  Expanded tool evidence remained readable and the composer stayed visible.
  Long conversations can still make the raw evidence verbose. This was not a
  mobile or comprehensive accessibility audit.

## Suggested teaching sequence

1. Ask about a purchase. Before expanding evidence, have the learner predict
   whether the answer came from memory, order records or catalogue search.
2. Expand **What the model saw → Context sources / Tool calls**. Compare available
   definitions with executed tools; the model can choose different valid paths.
3. Turn conversation memory off and count orders. Contrast this with asking what
   camera the shopper currently owns. Explain why an order is not current ownership.
4. Turn session memory on, correct the camera, then ask what changed. Inspect the
   earlier message rather than assuming a long-term update occurred.
5. Start a new conversation with long-term memory enabled. Show actual recalled
   memories after extraction; compare their wording with the original statements
   and never fake a successful memory update.
6. Switch shoppers and repeat the order question. Explain that the selector is a
   teaching control; scoped service keys enforce record access, and the selector
   itself is not production authentication.
7. Ask for gear, then price or compatibility. Check product evidence and identify
   what is missing. This makes retrieval limits part of the lesson.

## Automated verification

Final code checks: 271 Python tests passed, 30 opt-in tests skipped; 29 frontend
tests passed; Ruff, strict mypy across 42 source files, TypeScript and Vite build
passed. Existing RedisVL experimental API warnings remain. The code review found
no further actionable defects in error normalization, retry guidance or evidence
labels. These checks do not certify every generated sentence.
