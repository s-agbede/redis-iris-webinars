# Northwind Outfitters — a context-aware shopping agent on Redis

Companion repository for the **Redis Iris context engine** tech talk series. Each
episode adds one capability on top of the last; each has its own git tag.

| Episode | Capability | Tag | Runs locally? |
|---|---|---|---|
| 1 | Search — full-text, vector, hybrid | `ep1-done` | yes |
| 2 | Agent Memory | `ep2-done` | needs Redis Cloud |
| 3 | Context Retriever | `ep3-done` | needs Redis Cloud |
| 4 | LangCache — semantic caching | `ep4-done` | needs Redis Cloud |
| 5 | The finished agent | `ep5-done` | needs Redis Cloud |

## Quick start (episode 1)

```bash
cp .env.example .env      # add your OPENAI_API_KEY
make up                   # starts Redis, seeds the indexes, runs the app
```

Then open http://localhost:8000.

If port 6379 is already in use, set `REDIS_PORT` in `.env`.

## Commands

| | |
|---|---|
| `make up` | Start Redis, seed, run |
| `make seed` | Rebuild the Redis indexes from committed seed data |
| `make dev` | Frontend dev server with hot reload |
| `make eval` | Retrieval quality — `CONFIG=vector\|filtered\|hybrid\|all` |
| `make down` | Stop and remove containers |

## Retrieval quality

`make eval` runs 15 labelled queries against the live index in all three modes
and prints a pass count per mode. Cases live in `eval/cases.yaml`.

The three modes are **signals**, not stages: `text` (BM25), `vector` (cosine
similarity), `hybrid` (both, fused with RRF). Filters are a separate axis and
apply identically to all three — price, stock and category constraints are
orthogonal to how you score relevance, and any mode honours any facet.

|  | text | vector | hybrid |
|---|---|---|---|
| passed | 7/15 | 9/15 | 9/15 |
| MRR | 0.52 | 0.72 | 0.66 |

A case passes only when an acceptable answer is ranked **first** and nothing
filtered-out appears anywhere in the results. Every case records what each mode
actually did, so `make eval` exits nonzero when a change moves a verdict in
either direction. Use `--record` to rewrite those baselines after a deliberate
change.

Read that table carefully, because it does not say what a vector-search pitch
would like it to say:

- **Hybrid's MRR is lower than vector's.** On the four shopper-voice queries
  (`shopper-*`), plain vector search beats hybrid on every one. Fusing in a BM25
  ranking that returned socks drags a good vector ranking down — RRF weights the
  text signal equally whether or not it deserves it. Combining signals is what
  production does; deciding *how much* to trust each one is the part that
  actually takes work, and it is where ranking and re-ranking come in.
- **Text does well on the catalogue-vocabulary cases and collapses on the
  shopper-voice ones**, where the answer does not appear in the top 12 at all.
  That, not "missing rare tokens", is the real failure of lexical search: it
  needs the shopper to already know the words the catalogue chose.
- **Two cases stay red on purpose.** `stock-discipline`, where hybrid is worse
  than vector, and `warmth-is-not-weatherproofing`, which every mode fails.
  Same root cause: BM25 scores a decoy on the words *"stitched rather than
  taped"* and *"not built for sustained rain"* precisely because that sentence
  denies having them. Full-text scoring has no notion of negation and no amount
  of fusion tuning fixes it.

## About the data

The product catalogue is derived from Google's public
[`thelook_ecommerce`](https://console.cloud.google.com/marketplace/product/bigquery-public-data/thelook-ecommerce)
BigQuery dataset — a fictitious clothing retailer published by the Looker team.
We use the women's apparel slice: **1,573 products, 658 brands, 22 categories**,
with real product names, brands and price/cost pairs.

Two things are **not** from that dataset and are ours:

- **Product descriptions, sizes, colours, materials and fit** are generated with
  an LLM. They are illustrative demo copy and are **not** claims made by, or
  endorsed by, the brands named in the catalogue.
- **Store policies and ~50 "hero" products** are hand-written. Hero products use
  invented house brands, and carry any specific technical claims (waterproof
  ratings and similar) so that no invented specification is attached to a real
  brand.

Prices are converted from the source USD at a fixed rate of **0.92 EUR/USD** so
the seed is deterministic and reproducible.
