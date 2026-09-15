# Search learning implementation plan

> Use superpowers:subagent-driven-development for the independent frontend task and inline test-first work for backend evidence. User approval is already in the conversation. Do not commit unrelated uncommitted files or create another user task.

**Goal:** Turn the camera comparison into an evidence-based search teaching lab.

**Architecture:** Preserve native Redis retrieval and source data. Add typed explanation metadata to the existing comparison response. React renders compact results and a single shared panel from that response, fetching original product detail only when selected.

**Stack:** Existing FastAPI, Pydantic, RedisVL, local MiniLM, strict TypeScript and React. No new dependencies.

## Tasks

- [x] Probe native RRF component scores and ranks read-only. Decide exact versus unavailable decomposition from observed Redis responses; preserve the native ranking.
- [x] Add failing backend behavior tests in `tests/test_search.py` and a focused evidence unit test file. Cover literal overlap offsets, passage ranks before dedup, RRF exact arithmetic and unavailable/tied/missing evidence.
- [x] Implement typed evidence in `app/models.py`, focused helpers in `app/evidence.py`, and joins in `app/search.py`. Request `search_text` for all modes. JSON indexes reject native HIGHLIGHT in the live check; annotate literal whole-query-word overlap with safe offsets and clearly label its limits, never engine matches or HTML. Retrieve once per mode with a shared embedding.
- [x] Implement frontend in `web/src/main.tsx`, `results.tsx`, `Inspector.tsx`, `api.ts`, focused helpers/tests and CSS. Default three visible/five fetched, guided objectives, explicit filter experiment, narrow-screen rank matrix and tabs, shared evidence panel with accurate status labels and independent original-source loading.
- [x] Run `.venv/bin/pytest -q`, `.venv/bin/ruff check app tests seed/load.py eval`, `.venv/bin/mypy app seed/load.py eval`, and frontend TypeScript/build plus Node behavior tests. Run the opt-in live Redis integration test with `TEST_REDIS_URL=redis://localhost:6381`.
- [x] Restart only port 8001. Verify browser desktop and 390px/narrow layout, examples, filtering, selection, RRF explanation, source fidelity, keyboard focus and errors. Review for spec compliance, then code quality, fix findings and rerun affected checks.
- [x] Update README's teaching walkthrough and record the final developer-experience audit with reproducible queries, actual findings and known limits.
