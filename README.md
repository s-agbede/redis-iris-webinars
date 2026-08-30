# Northwind Outfitters — a context-aware shopping agent on Redis

Companion repository for the **Redis Iris context engine** tech talk series. Each
episode adds one capability on top of the last; each has its own git tag.

| Episode | Capability | Tag | Runs locally? |
|---|---|---|---|
| 1 | Search — vector, filters, hybrid | `ep1-done` | yes |
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
