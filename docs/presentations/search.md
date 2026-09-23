# Claude Design prompt: a 15-minute engineering webinar on search

Create an editable presentation for a 15-minute live webinar titled **“Finding the right product: full-text, vector and hybrid search.”**

The audience is software engineers from different companies and industries. Assume familiarity with APIs and databases, but no prior knowledge of embeddings or RedisVL. Use a fictional **Sam’s Camera Shop** to make the problem concrete. The concepts should transfer to searching documentation, support knowledge and internal records.

This is an engineering lesson with a working demonstration. RedisVL and Redis are the implementation tools. Keep the presentation focused on the engineering problem, observable behaviour and trade-offs. Use independent technical styling unless I supply a brand template.

Produce 11 main slides following the timing below, plus clearly separated appendix slides. The entire main presentation, including live demonstrations and transitions, must fit within 15 minutes. Do not add a separate cover slide. Include the talk title and presenter attribution discreetly on the opening slide.

## What engineers should leave with

Engineers should be able to:

- Distinguish a request for a known product from a request describing a need or a set of constraints.
- Explain what full-text, vector and hybrid retrieval contribute, including their limitations.
- Trace product data through preparation, schema definition, indexing and retrieval using RedisVL.
- Judge results using the source evidence, and distinguish ranking signals from eligibility filters.
- Identify the separate measurements needed for relevance, end-to-end latency, update freshness and throughput.

The question running through the presentation is: **“Which retrieval approach fits this query, and how will I know whether it works?”**

## Visual direction

Use a clean 16:9 composition with generous whitespace, strong contrast and large text suitable for screen sharing. Prefer one central visual argument per slide. Use consistent, labelled colours for full-text, vector and hybrid throughout the presentation. Do not rely on colour alone.

Use authentic product images and actual demo screenshots when supplied. Keep attribution where needed. If an asset is missing, use an explicitly labelled placeholder. Do not generate lookalike Sony or Canon product photographs or fabricate screenshots, rankings or performance numbers.

Make text, code, tables and technical diagrams editable. Keep code snippets short, with attention directed to the lines being discussed. Put implementation detail and qualifications in speaker notes when they do not need to be visible. Keep qualifications that change a statistic’s meaning on the slide itself.

Use varied layouts. Reserve the three-column comparison layout for comparing retrieval methods. Avoid decorating every slide like an application dashboard. Cut copy before shrinking text.

## Main slides and timing

### 1. Product search matters — 0:00–0:45

Establish the problem with two clearly labelled research findings:

- **Roughly half** of participants across Baymard’s ecommerce usability testing preferred search for finding products.
- **56% of sites** in Baymard’s 2026 benchmark failed to adequately support users’ search needs. The benchmark covered 170+ sites and apps.

Make the numbers prominent, with the population and scope immediately readable. A subtle product-catalogue image can provide context.

Include a visible source footer: **Baymard Institute, updated April 29, 2026**. Link the source in the notes:
https://baymard.com/blog/ecommerce-search-query-types

Do not change these into “half of all shoppers” or “56% of searches fail.” Do not claim search is the number one discovery channel across all businesses.

Speaker message: Search is an important route into a catalogue, and supporting the requests people actually make remains difficult.

### 2. We have the product. Can the customer find it? — 0:45–1:30

Show a catalogue of camera products with three illustrative customer requests:

- `sony zv e10` — “I know the model.”
- `a compact camera for filming myself` — “I know what I want to do.”
- `white 4k camera which is small` — “I know the properties I need.”

Include this exact quotation excerpt as a supporting element, preserving the initial ellipsis:

> “…more and more customers are going to type whatever they want, and we've got to do something helpful with it.”

Attribute it to **Rajiv Mehta, VP of Conversational Shopping at Amazon**, discussing conversational shopping. Source:
https://www.aboutamazon.com/news/retail/alexa-for-shopping-learn-and-be-curious-podcast

The quote supports the diversity of customer requests. It does not establish the market share of search or prove a particular retrieval technique is best.

Suggested speaker notes, written as my narration rather than an external quotation:

“As our catalogue grows, asking customers to inspect every product becomes impractical. Search lets them describe what they want, but people describe it differently. Some know the model. Some know the activity. Some have a set of requirements. Our job is to turn those requests into useful results quickly, using the product information we actually have.”

These are customer requests, not promises that every requested product or combination of features exists in our data.

### 3. Sam’s Camera Shop: the data we can search — 1:30–2:30

Introduce the real demonstration corpus: a selected English/US photography-query subset of **Amazon ESCI**.

Show **2,317 product records** prominently. Include 183 original queries and 3,147 query–product judgements as secondary context. Put the 8,472 derived retrieval passages in the technical notes or the next indexing slide.

Show one actual product record beside a readable schema containing the original fields:

- Product ID
- Title
- Description
- Bullet points
- Brand
- Colour
- Locale

Use a record supplied with the repository. If unavailable, leave a labelled product-record placeholder instead of inventing a listing.

Explain briefly that this is a query-selected corpus. It retains the judged candidates for the selected queries, including accessories and irrelevant products. It is not a complete or perfectly classified camera catalogue.

The original data has no supplied prices, stock levels, images or verified compatibility rules. Missing information stays missing. The app’s attributed reference photographs are a separate enrichment, and do not influence retrieval.

Source:
https://github.com/amazon-science/esci-data

### 4. A simple title match reaches its limits — 2:30–3:15

Show this deliberately simple Python baseline:

```python
matches = [
    product for product in products
    if query.casefold() in product.product_title.casefold()
]
```

Use `sony zv e10` to illustrate how a literal substring test can miss a title containing a different representation such as `ZV-E10`.

Explain the two separate concerns: matching behaviour and the cost of scanning the catalogue. The loop inspects N titles; total work also depends on the strings being searched. If showing O(N), label it as a catalogue scan with title length treated as bounded.

Do not suggest that exact lookup is impossible or inherently requires a linear scan. A normalised product identifier can support efficient exact lookup. Our demonstration concerns the richer problem of free-text product discovery.

### 5. Product records become a searchable index — 3:15–4:30

Create an editable diagram showing these operations in order:

1. Preserve source product records.
2. Clean text and create overlapping passages.
3. Generate passage embeddings with a local model.
4. Load passage documents into a Redis JSON search index using RedisVL.
5. Retrieve ranked passages, group them into distinct products and inspect the source.

Show the role of the schema through a small, accurate field mapping: `search_text` as TEXT, `brand` as TAG, and `embedding` as VECTOR.

The actual implementation uses `sentence-transformers/all-MiniLM-L6-v2`, 384-dimensional embeddings, cosine distance and a FLAT vector index. The model runs locally on CPU. Once dependencies and model files are prepared, inference requires no hosted model API.

Include a brief RedisVL schema and create/load example taken from the supplied project. Keep it readable. If source code is unavailable, use labelled pseudocode and identify the missing snippet in the handoff. Do not invent executable APIs or imply that schema creation automatically generates embeddings.

### 6. Full-text search: matching the words — 4:30–6:30

Live demo query: `sony zv e10`. Preserve that exact spelling in the run sheet.

Show a compact RedisVL `TextQuery` excerpt from the application beside a lexical-retrieval diagram: query terms, inverted index, BM25 ranking, results.

The implementation uses BM25STD, English stopword removal and OR-matching of remaining terms. Explain enough to show why this behaves differently from a substring test.

Demo sequence: run the shared comparison, inspect the full-text column, select the Sony ZV-E10 and examine its actual source passage. The recorded demo places the ZV-E10 first for this query; refresh the screenshot and verify behaviour before presenting.

Explain that full-text search is useful when terms and identifiers carry strong meaning. A request describing an activity may use different language from a listing. Synonyms, normalisation and structured metadata can also improve lexical retrieval.

Avoid claiming that full-text search only supports exact text or can never accommodate broader language.

### 7. Vector search: matching a described need — 6:30–8:30

Live demo query: `a compact camera for filming myself`.

Show query embedding, similarity retrieval and the returned product passages. Use a simple conceptual diagram, explicitly labelled as illustrative if spatial positions are not computed from the actual embeddings.

Show a concise local embedding and RedisVL `VectorQuery` excerpt. Explain that similarity can surface related descriptions even when the wording differs.

During the demo, compare the retrieved products and read the source evidence. The current corpus produces imperfect results; do not script vector search as automatically finding the ideal camera.

Make the limitation clear: semantic similarity does not guarantee a particular model, colour, feature or compatibility requirement.

If complexity appears, distinguish embedding computation from retrieval. The demonstrated FLAT search calculates distances across the eligible vectors, with distance work proportional to N × d. Put detailed complexity discussion in the appendix. Do not label this demonstration as HNSW or promise universal logarithmic vector search.

### 8. Hybrid search: combining ranking signals — 8:30–10:30

Live demo query: `white 4k camera which is small`. Then apply and remove the same Sony brand filter across all three methods.

Show lexical and vector candidate rankings feeding reciprocal rank fusion, followed by grouping passages into distinct products. Include a concise RedisVL `HybridQuery` excerpt from the actual implementation.

Explain RRF as combining rank positions. If using a worked example, label it illustrative and keep it separate from measured results.

Implementation notes: native Redis hybrid search, RRF constant 60, a candidate window of 100 per branch, and fusion at passage level before product deduplication. A passage missing from a branch’s candidate list contributes nothing from that branch. Product ranks shown after grouping are not the original passage ranks used in fusion.

Demonstrate the distinction between relevance signals and eligibility: the word “Sony” in a query influences ranking; the exact source-brand filter restricts the eligible records. The implemented shared filter is brand. Do not show unimplemented colour, price or compatibility filters as working features.

Compare ranks and source passages. BM25, cosine similarity and RRF scores have different scales and should not be compared numerically across modes.

Hybrid can improve the balance of signals, but its outcome depends on the candidates, model, data and query. Do not manufacture a different winner for every mode or describe hybrid as always best.

### 9. A useful result must arrive in time — 10:30–12:30

Connect customer expectations to the measurements engineers need:

| Concern | Measurement |
|---|---|
| Relevance | Judged top results, failure cases and constraint violations |
| Responsiveness | End-to-end latency, including query embedding, with p50/p95 under a defined load |
| Freshness | Time between an accepted data update and its visibility in search |
| Capacity | Queries per second at a latency target, plus ingestion throughput and resource use |

Include this supporting research callout:

**Google’s 2009 controlled experiments: adding 100–400 ms to search results delivery reduced daily searches per user by 0.2–0.6%.**

Keep “2009,” “added delay” and “searches per user” visible. Source:
https://services.google.com/fh/files/blogs/google_delayexp.pdf

Explain in notes that this was search-results delivery latency, not an isolated database benchmark. It motivates measuring responsiveness; it does not establish a universal SLA or predict a conversion uplift for this application.

Use the app’s timing breakdown to distinguish shared embedding time, backend-to-Redis round trips, application evidence processing and total comparison wall time. The three Redis requests run sequentially in this lab. Its displayed timings are individual observations, not p95, sustained throughput or index-freshness measurements.

Show an illustrative timing breakdown only if real measurements are unavailable, and label it. Keep production scale experiments as proposed work. Discuss HNSW as a future recall, latency and memory comparison against FLAT.

### 10. Which approach fits the request? — 12:30–14:00

Create a readable comparison table:

| Approach | Useful starting point | Main limitation or evaluation question |
|---|---|---|
| Full-text | Names, terminology and queries with strong lexical clues | Does the system handle the wording, variants and synonyms users actually use? |
| Vector | Descriptions of activities, needs and related concepts | Are semantically similar results suitable, and do they respect required attributes? |
| Hybrid | Queries needing evidence from both wording and meaning | Does fusion improve judged relevance enough to justify its extra work? |

Below the table, add: **“Use explicit filters for hard constraints that your data can reliably represent.”**

Speaker message: choose representative queries, define useful results and evaluate the alternatives. For an exact SKU or normalised identifier, direct lookup can remain the appropriate path.

### 11. Run the lab and continue the series — 14:00–15:00

Provide two large, separately labelled QR areas:

1. **Run the lab and get the resources**: one landing page containing the repository, RedisVL documentation, slides and my LinkedIn profile.
2. **Join the discussion**: the supplied Discord invitation.

Show a readable short link beneath each code when final destinations are available. If links are missing, use visibly labelled QR placeholders. Do not invent destinations or render decorative codes that look scannable.

Close with one short line about extending this same shop and source corpus in future sessions:

- Context retrieval: assemble relevant product passages with provenance.
- Agent memory: retain useful preferences across explicitly simulated customer sessions.
- Semantic caching: reuse suitable answers to equivalent requests within defined context and freshness rules.

These are future sessions, not current capabilities. The static dataset does not contain customer histories, and new illustrative interaction data must be labelled.

Keep this slide displayed during any remaining questions.

## Appendix and supporting material

Include separate, untimed appendix slides for the full code excerpts, detailed schema, evaluation and scale experiments, and source references. Keep them out of the 15-minute main sequence.

The source appendix should preserve the three research sources above, the Amazon ESCI repository and this optional historical quotation:

> “Amazon Search powers the majority of Amazon’s sales.”

Attribute it to **Daria Sorokina and Erick Cantú-Paz, SIGIR 2016**, from “Amazon Search: The joy of ranking products.” Source:
https://www.amazon.science/publications/amazon-search-the-joy-of-ranking-products

Keep its date and scope explicit. It concerns Amazon’s sales at that time. It is not evidence for a current, industry-wide discovery share. Include it as supporting historical context rather than adding another quote to the opening.

## Deliverables and final review

Provide the editable presentation, a PDF export if supported, speaker notes and a timed demo run sheet. Notes should include the purpose, spoken explanation, transition, source links and live-demo action for each slide. The run sheet should include the exact query strings, filter actions and screenshot fallback for each demonstration.

Use the repository’s README, search implementation and learning observations as the source of truth for demo behaviour. If I have not supplied the repository or screenshots, complete the design with labelled placeholders and give me a concise asset list. Do not infer actual results from the intended narrative.

Before delivering, inspect rendered slides for readability, overflow, contrast, consistent method labels, working links and source attribution. Check that the timings sum to 15 minutes including demos. Verify quotations, dates, populations and units. Test real QR codes when supplied.

Finally, review the deck from an engineer’s perspective: can they explain why the methods return different results, inspect evidence behind a ranking, distinguish relevance from filters, understand what the code does, and identify what still needs measuring? Revise any slide that obscures those lessons.
