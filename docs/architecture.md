# Retrieval architecture


```text
Original source records → cleaned, overlapping passages → Redis JSON index
                                                           ↑
Query ───────────────────────────────→ BM25 full-text ──────┤
      └→ local embedding, once ──────→ cosine vector KNN ───┤
                                      native RRF hybrid ───┘
                    passage rankings → distinct products → source inspector
```

- **Full-text:** RedisVL `TextQuery`, BM25STD, English stopword removal and
  OR-matching of remaining words on `search_text`. It is not exact-phrase search.
- **Vector:** RedisVL `VectorQuery`, normalized 384-dimensional MiniLM embeddings,
  cosine distance, initially a FLAT index. The UI displays `1 - distance`.
- **Hybrid:** RedisVL `HybridQuery`, Redis `FT.HYBRID`, reciprocal rank fusion
  with window 100 and constant 60. Its lexical expression is explicitly aligned
  with the full-text query; RedisVL 0.26's optional-text default would otherwise
  give unmatched passages lexical rank contributions.
- **Shared constraints:** the same exact, case-sensitive source-brand filter,
  index and candidate limit apply to each method. Model/mount text in a query is
  a relevance signal, not a hard compatibility constraint.

The search box accepts plain-language queries. Before constructing either lexical
query, the app replaces ASCII punctuation (except underscores) with spaces, then
lets RedisVL remove stopwords and escape the resulting terms. Thus `Sony ZV-E10`
and `sony zv e10` both search `@search_text:(sony | zv | e10)`. Escaping the original
hyphen would request a single `zv-e10` token, while the existing TEXT index stores
`zv` and `e10` separately. See [Redis tokenization rules](https://redis.io/docs/latest/develop/ai/search-and-query/advanced-concepts/escaping/).
This query-side change needs no reindexing. Quotes and operators entered in the
search box do not enable advanced Redis query syntax. Full-text highlights use
the same normalized terms. If no terms remain after punctuation and stopword
removal, Full-text and Hybrid report an explicit error; Vector can still run.
Basic's literal title lookup, the embedding input and source-judgement lookup
retain the original query. Consequently, equivalent lexical queries can still
have different vector rankings and different hybrid rankings.

Full-text and vector each retrieve up to 100 **passage** candidates. Hybrid fuses
the union of its top 100 lexical and top 100 vector passages, returning up to 200
rows so the explanation can see every contributing candidate. Each method keeps
the best-ranked passage per distinct product and fetches five products for the
UI; three are visible initially. Hybrid fuses passages before product
deduplication. A product with many passages can occupy several candidate
positions, so this is not product-level RRF and may return fewer than five
distinct products even when more exist in the catalogue.
BM25, cosine and RRF scores use different scales; compare ranks and evidence
across columns rather than numeric scores.

The shared evidence panel uses each method's actual winning passage. Its expanded
indexed text includes bounded title, brand and color context. Literal query-word
overlap is highlighted directly in full-text result titles and excerpts, as well
as in the full-text evidence panel. Excerpts start near the first literal match;
each displayed field has its own Unicode code-point offsets. These annotations
are explicitly labelled as literal overlap: the tested Redis JSON index rejects
native `HIGHLIGHT`, and the annotations do not show stemming or explain BM25
scoring. See the [Redis indexing limitations](https://redis.io/docs/latest/develop/ai/search-and-query/indexing/).

Hybrid returns native branch-score aliases in the **same execution**. The app
reconstructs possible ordinal passage ranks, resolves ties against the native RRF
score, and shows contributions only when exactly one pair reconciles within
`1e-12`. Otherwise it says the explanation is unavailable. Redis's score and order
remain authoritative; this is a verified reconstruction, not native
`EXPLAINSCORE`. Incomplete or warning-bearing hybrid responses become explicit
mode errors. Missing from the fetched top five does not mean a product cannot
match, and a failed method is shown separately from a successful empty result.

Passages cover cleaned titles, descriptions and bullet points, with bounded title
context and a default 32-token overlap. The complete source fields stay intact.
The passage builder respects a 240-token content budget; the local model accepts
256 tokens including special tokens. Overlong queries produce an explicit model
error instead of being silently truncated. Offsets refer to the **cleaned** field.

The local encoder is `sentence-transformers/all-MiniLM-L6-v2` at revision
`c9745ed1d9f207416be6d2e6f8de32d1f16199bf`, running on CPU with ONNX Runtime,
attention-mask mean pooling and L2 normalization. File hashes and license metadata
are recorded in `seed/local-model.json`. Set `MODEL_PATH` to a directory containing
the exact pinned `tokenizer.json` and `onnx/model.onnx` files to use a prepared
local copy. Query embeddings are computed once per comparison and shared by the
vector and hybrid requests. There is no hosted model call or query cache.

Camera keys use `camera:product:us:<id>`, `camera:passage:<passage-id>` and
`camera:manifest`; the index is `camera_passages`. `NAMESPACE` allows another
independent camera instance. Historical apparel assets are preserved in Git; see [repository history](history.md).

### Timing and architecture

The UI separates shared embedding time, each backend-to-Redis round trip,
application evidence-processing time and total comparison wall time. The three Redis queries execute sequentially. These
numbers include client and response handling overhead and are influenced by warm
connections and caches. They are not Redis-only execution times, p95 latency,
throughput or index-freshness measurements.

For the webinar, explain that query latency, update-to-search visibility, indexing
throughput and concurrent-query throughput require different experiments. This
small FLAT corpus establishes retrieval behavior. An HNSW scale experiment should
measure recall against FLAT as well as latency and memory. Change
`INDEX_ALGORITHM` and rebuild deliberately; do not extrapolate the interactive
numbers into production capacity claims.

## Autocomplete

`GET /api/suggestions?prefix=so` uses Redis `FT.SUGGET` to return up to six
prefix suggestions. Startup populates a separate, source-versioned dictionary
with `FT.SUGADD`, using product titles and brands weighted by distinct product
coverage. Suggestions longer than 200 characters are omitted. No embeddings or
search index rebuild are needed. Historical dictionary versions can remain
until explicitly removed; they are not queried by a newer catalogue.

The UI waits 180 ms after typing at least two characters, cancels obsolete
requests, and supports arrow keys, Enter and Escape. Choosing a suggestion fills
the query; submitting the search runs retrieval. Suggestions cover all brands and are not
filtered by the brand control. This is prefix completion, not semantic search,
substring matching, spelling correction or a relevance assessment.

Redis command references: [FT.SUGADD](https://redis.io/docs/latest/commands/ft.sugadd/)
and [FT.SUGGET](https://redis.io/docs/latest/commands/ft.sugget/).

## Code walkthrough for the demo

1. Open [`schemas/passages.yaml`](../schemas/passages.yaml) to show text, vector,
   and brand fields.
2. Open [`app/queries.py`](../app/queries.py): `build_text_query`,
   `build_vector_query`, then `build_hybrid_query`. These are the actual builders
   the application uses, not separate demonstration examples.
3. Show `align_hybrid_lexical_branch` below the hybrid builder when explaining
   the RedisVL 0.26 adjustment. The builder also fetches the full candidate union
   for evidence; neither change is hidden in a demo-only implementation.
4. Follow `Searcher.compare` in [`app/search.py`](../app/search.py) for the shared
   embedding, filters, Redis execution, and result processing.

Builders receive the normalized lexical text or a precomputed vector, the same
filter expression, and a candidate limit. They construct query objects without
connecting to Redis or calling the embedding model.
