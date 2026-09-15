# Camera Search Lab Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development for the independent frontend task and review; execute the backend and data work in this session. User approved implementation and local models on 2026-09-14.

**Goal:** Replace the apparel search explorer with a locally runnable, evidence-backed camera search comparison lab.

**Architecture:** Keep FastAPI, Pydantic, RedisVL and React/Vite. Preserve ESCI source fields, derive bounded passages with source offsets, and search the same passages with BM25, cosine and native RRF. Group passage hits by product for display. A pinned local MiniLM ONNX model supplies embeddings without API keys; only explicit preparation downloads data/model files.

**Tech stack:** Python 3.12, uv, RedisVL 0.26, Redis 8.4+, ONNX Runtime, Hugging Face tokenizer/hub, Redis JSON, strict TypeScript and React.

## Approved scope and routine implementation choices

- Side-by-side full-text, vector and hybrid search; five products per column.
- Original camera dataset values, no invented prices, stock, product photos or compatibility facts.
- A reviewed query selection preserves all its judged candidates; labels remain outside indexed text.
- Local MiniLM revision `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`, float32, normalized mean pooling, 384 dimensions; model metadata and corpus version checked against the live index.
- FLAT index initially, candidate limit explicit. Hybrid RRF at passage level, then collapse products. The inspector states this so it is not confused with product-level fusion.
- Camera indexes use new prefixes; apparel data and existing unrelated work remain available.
- Offline inference after explicit model preparation. Show missing-data/model/index errors with actionable setup instructions.

## API contract

`GET /api/catalog` returns:
```json
{"name":"Camera Search Lab","product_count":0,"passage_count":0,"source_revision":"...","embedding_model":"sentence-transformers/all-MiniLM-L6-v2","embedding_revision":"...","vector_dimensions":384,"index_algorithm":"FLAT","brands":[{"value":"Canon","count":12}],"examples":[{"query":"canon rf lenses","title":"Model & mount","kind":"exact","origin":"esci"}]}
```

`POST /api/compare` accepts `{"query":"canon rf lenses","brands":[],"num_results":5}`. It returns:
```json
{"query":"canon rf lenses","brands":[],"embedding_ms":1.2,"total_ms":8.1,"embedding_model":"sentence-transformers/all-MiniLM-L6-v2","source_revision":"...","candidate_limit":100,"results":[{"mode":"text","query_ms":1.0,"score_kind":"BM25","redis_query":"...","error":null,"hits":[{"product_id":"B08MFVH7SV","title":"Canon RF50mm F1.8 STM","brand":"Canon","color":"Black","score":2.3,"source_label":"E","passage":{"passage_id":"us:B08MFVH7SV:0","field":"product_bullet_point","text":"...","start":0,"end":100}}]}]}
```
Results contain exactly `text`, `vector`, `hybrid` entries. `source_label` is `E|S|C|I|null`, found only for an exact source-query match; it is a source judgement, never an inferred verdict. Each entry can report its own error with no substitute results. All timing values are milliseconds. Redis request times include client overhead; this is an interactive comparison, not a throughput benchmark.

`GET /api/products/{product_id}` returns original seven ESCI fields plus `source_revision` and `passages` using the passage shape above. Locale is US throughout this app. `GET /api/health` reports readiness. Errors use FastAPI `detail` strings.

## Task 1 — reproducible data and local model

Files: `scripts/prepare_cameras.py`, `seed/cameras/`, `app/catalog.py`, `app/embeddings.py`, `tests/test_catalog.py`, `tests/test_embeddings.py`, `pyproject.toml`.

- [x] Write failing tests for source preservation, HTML cleaning, complete long-text passage coverage and title context within model token limits.
- [x] Review all 497 candidate queries into an explicit inclusion/exclusion manifest, and retain all judged products for included queries.
- [x] Fetch pinned full source records; store compressed source JSONL and judgements, source license/notice and checksums. Missing product text stays missing.
- [x] Implement local ONNX inference, explicit model download command, no network during serving, and model identity checks.
- [x] Run unit tests and a real embedding smoke check with the cached model.

## Task 2 — Redis retrieval and API

Files: `app/models.py`, `app/search.py`, `app/settings.py`, `app/main.py`, `seed/load.py`, `schemas/products.yaml`, `tests/test_search.py`, `tests/test_api.py`.

- [x] Write tests for one shared embedding, consistent brand filters, distinct products, matched source labels, error isolation and blank/oversized queries.
- [x] Load source products and bounded passages into dedicated camera keys and a FLAT index, with a corpus/model manifest.
- [x] Implement the API contract using RedisVL TextQuery, VectorQuery and HybridQuery; preserve source evidence and explicit scores.
- [x] Validate against a real local Redis instance using the dedicated camera index; verify source products and passages join.

## Task 3 — comparison frontend

Files: `web/src/main.tsx`, `web/src/style.css`, optional small `web/src/types.ts` and `web/src/api.ts`.

- [x] Implement the API contract with one query submission, shared brand filter, examples, three columns and product inspector.
- [x] Show raw source evidence, source-label meaning, shared embedding time, per-mode query time and total wall time; never compare scores across modes.
- [x] Handle loading, errors, empty results and stale in-flight requests; keyboard-accessible inspector and narrow layouts.
- [x] Build strict TypeScript and verify an actual browser flow against the real backend.

## Task 4 — evaluation, startup and documentation

Files: `eval/run.py`, `eval/models.py`, `eval/cases.yaml`, `tests/test_eval.py`, `README.md`, `Makefile`, `.env.example`, `docker-compose.yml`.

- [x] Replace apparel evaluation with an honest judged-coverage/ranking report and reviewed checks; do not classify unjudged products as irrelevant or improvements as failures.
- [x] Select three demonstration queries after observing results and save an evidence report.
- [x] Pin Redis image and dependencies; document local setup, downloads, data counts, timing semantics and later-series boundaries.
- [x] Run tests, Ruff, mypy, frontend build, live Redis API checks and browser verification. Review the final diff for source fidelity and scope.

## Completion evidence — 2026-09-14

- Bundled corpus: 2,317 original products, 183 reviewed source queries, 3,147 original judgements, 8,472 derived passages. Rebuilt records verified against canonical source values; partial or edited source input is rejected before provenance is written.
- Cached MiniLM ONNX model verified, existing complete index reused, and serving tested with no hosted model key.
- Live Redis 8.6.2 regression reproduced and fixed RedisVL optional lexical matching in hybrid. With no lexical matches, hybrid now has only vector rank contributions.
- `TEST_REDIS_URL=redis://localhost:6381 .venv/bin/pytest -q`: 25 passed, including real Redis and model checks. Upstream experimental/deprecation warnings remain.
- Ruff passed; mypy passed for all 12 scoped Python files; strict TypeScript/Vite build passed; frontend request tests 5/5 passed. Compose configuration and uv lock verified.
- Real browser: three rankings, shared Canon filter, source evidence, Escape/close and focus restoration, query clearing, no lexical matches, 390px responsive layout and modal without horizontal overflow. Temporary viewport restored.
- Independent specification/code review found two issues (hybrid lexical ranks, source preparation completeness); both fixed and confirmed resolved. No outstanding significant findings.
- Demo observations saved in `eval/demo-observations.json`; setup and 15-minute walkthrough in README.
- Running camera app: http://127.0.0.1:8001. Existing unrelated app on port 8000 left running. Changes remain uncommitted on `codex/camera-search-lab`.
