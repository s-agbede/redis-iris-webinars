# Camera Search Lab

Compare full-text, vector and hybrid retrieval over the same camera-related
catalogue, with RedisVL and a local embedding model. One query produces three
ranked lists, with three results visible initially and five available without
rerunning. Select a product to open one shared panel with its rank and winning
passage from each method, verified hybrid contributions, and original source fields.

## Run locally

Prerequisites: Docker with Compose, Python 3.12+, [uv](https://docs.astral.sh/uv/),
and Node.js 22.18+ with npm. No model API key is required.

```bash
cp .env.example .env  # only for a new checkout; preserve any existing .env
make up
```

Open [the lab](http://127.0.0.1:8000). Use `make up PORT=8001` if 8000 is occupied.
If Redis port 6379 is occupied, set **both** `REDIS_PORT=6381` and
`REDIS_URL=redis://localhost:6381` in `.env`.

The first run installs dependencies, starts Redis, downloads the pinned MiniLM
ONNX model (about 90 MB), builds the frontend and indexes the bundled data. Allow
a few minutes for initial CPU embedding. Later runs verify the cached model and
reuse the index when its data, model and passage configuration match. `make up`
keeps an existing Compose service container; it does not automatically upgrade
an older Redis container. The loader checks that Redis supports native hybrid
search (8.4+); the Compose image is pinned to the tested Redis 8.6.2 digest.

After preparation, `make serve` runs entirely locally. Serving and seeding do not
download a model. For a fully offline restart, use `make redis` and `make serve`
with the image, Python dependencies, model and frontend build already present.
`make up` also runs npm installation, which may need network access.

| Command | Purpose |
|---|---|
| `make model` | Download missing pinned model files; verify and reuse cached files |
| `make redis` | Start the local Redis service and wait for readiness |
| `make seed` | Rebuild the camera passage index and refresh source records |
| `make serve PORT=8001` | Serve the prepared API and built frontend |
| `make build` | Install locked frontend dependencies and build strict TypeScript |
| `make dev` | Vite frontend with hot reload; API proxy targets port 8000 |
| `make eval` | Run the three reviewed demo queries against real retrieval |
| `make lint` / `make test` | Python static checks / test suite |
| `make down` | Stop Compose services while preserving their data |

Stop the app before reseeding and restart it afterwards. The app checks the index
manifest at startup and holds the source catalogue in memory. A missing model,
mismatched index or unavailable Redis produces an actionable error, never
substitute results. If setup was incomplete at startup, complete it and restart
the server. `/api/health` reports readiness.

## What is in the dataset?

The bundled corpus comes from [Amazon ESCI](https://github.com/amazon-science/esci-data)
at revision `7916cdf6ab75a462e77f20ab40428a10923998d5`, with its Apache 2.0 license
and notice in `seed/cameras/`.

| Item | Count |
|---|---:|
| Selected English/US photography queries | 183 |
| Distinct US product records | 2,317 |
| Original query–product judgements | 3,147 |
| Derived retrieval passages with default settings | 8,472 |
| Products without a description | 969 |
| Products without bullet points | 146 |

The initial keyword slice contained 497 queries and 5,602 products. The explicit
inclusion decisions are in `seed/cameras/query-selection.json`. For each selected
query, **all judged candidate products are retained**, including irrelevant
candidates, accessories and unrelated products. This is a query-selected search
corpus, not a verified photography taxonomy or a complete camera catalogue.

Each product preserves the original seven fields: ID, title, description, bullet
points, brand, color and locale. There are no supplied images, prices, stock,
reviews, mount facets or verified compatibility rules. Missing fields remain
missing. Some listings contain contradictory copy; the inspector keeps the
original fields visible instead of filling gaps or resolving claims by guessing.

The app adds **9 locally stored reference photos for 16 product records** as a
separate enrichment. These cover Nikon D610/D5600/W300, Sony A7R II/ZV-E10, and four Canon
lenses. Result cards and the inspector show the photographer, source and licence;
captions identify body-only views, mounted lenses and the W300 colour difference.
Other products show a placeholder. The photos are bundled for offline demos and
do not alter the source records, embeddings or rankings. See
[photo credits](seed/photos/CREDITS.md) and the explicit product-ID mappings in
[the photo manifest](seed/photos/manifest.json). Photos retain their individual
CC BY-SA 3.0/4.0 licences. Startup verifies asset checksums and mapped product IDs.
To extend coverage, add a verified JPEG and attributed entry to that manifest,
then restart the app; no Redis reindex is required.

Original ESCI labels mean Exact, Substitute, Complement and Irrelevant. They are
sparse query–product judgements, not universal product labels. The UI attaches
them only when the submitted query exactly matches the original query text.
**Unjudged does not mean irrelevant.** Labels never enter the search text or
embeddings. Original train/test split values are preserved, but this selected demo
corpus and its chosen examples are not a held-out evaluation.

### Reproduce the subset

Normal setup uses bundled compressed JSONL and verifies its checksums. To rebuild
it, obtain the original `shopping_queries_dataset_products.parquet` and
`shopping_queries_dataset_examples.parquet` from the pinned ESCI revision's
`shopping_queries_dataset/` directory, resolving Git LFS files. Then run:

```bash
uv run --extra prepare python scripts/prepare_cameras.py \
  --products /path/to/shopping_queries_dataset_products.parquet \
  --examples /path/to/shopping_queries_dataset_examples.parquet \
  --output /tmp/camera-subset
```

The arguments also accept HTTPS URLs. The script streams Parquet batches and
uses the bundled reviewed query selection. It verifies every selected source
record against the canonical bundle and fails on missing or changed products or
judgements. Product values and judgement pairs reproduce the bundled
corpus; row order and gzip bytes may differ by source export or compression
runtime. The generated manifest records its actual file checksums. To use a
rebuilt corpus, set `DATA_DIR=/tmp/camera-subset`, reseed and restart.

## How retrieval works

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
indexed text includes bounded title, brand and color context. Literal query-word overlap is
highlighted only in the full-text evidence and explicitly labelled: the tested
Redis JSON index rejects native `HIGHLIGHT`, and these annotations do not show
stemming or explain BM25 scoring. See the [Redis indexing limitations](https://redis.io/docs/latest/develop/ai/search-and-query/indexing/).

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
independent camera instance. The older apparel seed assets remain as historical
material and are not used by this app.

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

## A 15-minute demonstration

| Time | Demonstration | Engineering takeaway |
|---|---|---|
| 0–2 min | State the task, available listing fields and definition of a useful result | Define relevance before choosing a search mode |
| 2–5 min | Run **Start with a model**: `sony zv e10`. Select the ZV-E10 and inspect its ranks and passages | Full-text ranks the ZV-E10 first; vector ranks it fifth and puts a ZV-1 first. Semantic proximity can lose an exact model requirement |
| 5–8 min | Run **Describe a need**: `a compact camera for filming myself` | Read the source to judge the need. Full-text's first result is a video head; vector and hybrid have different camera results. A ranking alone does not establish suitability |
| 8–12 min | Run **Add requirements**, then apply/remove the Sony brand filter. Inspect a hybrid result | Query words influence relevance; the same exact brand filter controls eligibility in all modes. Use passage ranks to explain RRF |
| 12–15 min | Open **Inside this comparison** and inspect commands | Separate embedding cost, retrieval and explanation overhead; design separate latency-under-load, throughput and freshness experiments |

Each guided example resets to all brands. The filter experiment keeps the query
unchanged and reruns all three methods. On narrow screens a product-rank matrix
stays above method tabs; select any product for the same shared evidence panel.
Showing three or five uses the existing response. Keyboard selection moves focus
to the panel; closing it returns to the selecting control.

The seven learning scenarios and actual rankings are recorded in
[learning observations](eval/learning-observations.json), with the developer
experience checks in [the learning audit](docs/search-learning-audit.md).
These queries are authored demonstrations, not newly judged relevance labels.
The older reviewed evaluation examples remain in `eval/demo-observations.json`.
The demo does not force a different winner for each mode.

`eval/cases.yaml` contains a limited assistant-reviewed pool of source-based
relevance judgements, separate from Amazon's original labels. Inspect those
judgements before presenting. `make eval` reports each mode's actual results,
original-label coverage and reviewed first-result assessment. It exits nonzero
on execution errors, not when a ranking improves or changes. To inspect all
selected source queries:

```bash
uv run python -m eval.run --all-source --output /tmp/all-camera-queries.json
```

## Verification

```bash
make lint
make test
npm --prefix web run build
node --experimental-strip-types --test web/src/*.test.mjs
TEST_REDIS_URL=redis://localhost:6379 uv run pytest -q tests/test_live_camera_flow.py
```

The live test needs the prepared model and camera index. It checks all three
methods, identical brand constraints, unique products, source-passage offsets,
empty filters, literal-overlap offsets, verified native fusion arithmetic and
hybrid's zero lexical contribution when no lexical terms match. The ordinary
suite skips that integration check unless `TEST_REDIS_URL` is set. A real-model
unit check also skips if its pinned files have not been prepared.

## Extend the same scenario

The current app implements search comparison. Later episodes can reuse stable
product IDs, source revisions and evidence passages:

- **Context retrieval:** assemble cited evidence for a camera-kit comparison;
  expose missing or conflicting specifications instead of inventing answers.
- **Agent memory:** add explicitly simulated shoppers with remembered bodies,
  preferences and changing needs across sessions. These histories are new demo
  data, not part of ESCI.
- **Semantic caching:** add reviewed equivalent questions and near misses;
  scope reuse to user constraints, model and source version, with invalidation
  when that context changes.

Those capabilities are extension points, not implemented features in this version.
