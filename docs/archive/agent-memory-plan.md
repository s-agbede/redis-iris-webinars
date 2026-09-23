# Sam's Camera Shop Implementation Plan

> Execute in this session with test-first changes and independent code review.

**Goal:** Build a real shopping chat that teaches and exposes Redis Agent Memory.

**Architecture:** Add typed memory and chat adapters to the existing FastAPI app,
reuse its catalogue search, and add a React shop page with onboarding and evidence.
Keep the existing comparison and management routes available.

**Tech stack:** Python, Pydantic, FastAPI, Redis, Redis Agent Memory SDK, httpx,
React, TypeScript and Vite. Continue in the requested `agent-memory` branch.

## 1. RAM boundary and configuration

- [x] Add `tests/test_shop_memory.py` for owner filters, event retrieval, direct
  writes, typed record conversion, partial write failures and safe errors.
- [x] Run `uv run pytest tests/test_shop_memory.py -q` to demonstrate missing
  behaviour before implementing `app/shop/memory.py` and typed models.
- [x] Add the official SDK and environment-backed endpoint/store/key settings.
- [x] Verify tests, Ruff and mypy. SDK methods must match the installed version.

## 2. Chat and catalogue orchestration

- [x] Add behavioural tests in `tests/test_shop.py`: session ownership, context
  modes, newly created session, onboarding, products restricted to real search
  results, purchaser isolation, model/memory failures and snapshot differences.
- [x] Implement `app/shop/models.py`, `app/shop/service.py`, `app/shop/routes.py` and a
  model transport. Reuse the existing Searcher and product records.
- [x] Register `/api/shop` endpoints before the frontend static mount.
- [x] Verify `uv run pytest tests/test_shop.py tests/test_api.py -q`.

## 3. Playbook and demo evidence

- [x] Test the remote Playbook discovery/version-loading adapter with controlled
  HTTP responses before implementation; do not label local guidance as remote.
- [x] Add the camera-adviser Skill, fictional purchase fixtures linked to bundled
  IDs, and before/after memory comparisons with observed rather than inferred status.
- [x] Verify guidance source/version and purchase provenance in API responses.

## 4. Shop interface

- [x] Add typed shop API contracts and snapshot and request-state tests alongside existing
  frontend logic tests.
- [x] Build onboarding, conversational messages, product cards/details, new-session
  and shopper controls, memory-mode selection and evidence inspector.
- [x] Include actionable setup/error states and pending extraction observations.
- [x] Add navigation to search comparison and shop management.
- [x] Run `node --test web/src/*.test.mjs` and `npm --prefix web run build`.

## 5. Rehearsal and delivery

- [x] Add `docs/demos/agent-memory.md`, setup documentation and repeatable live
  evaluation tooling. Keep secrets out of output and generated artifacts.
- [x] Run Python tests, lint/type checks, frontend tests and build.
- [x] Exercise browser flows against the local app and run available real-service
  checks for onboarding, recall, reconciliation, PII and owner isolation.
- [x] Review the implementation independently, resolve significant findings,
  and report exactly which checks passed or require service configuration.

## Live outcome

See [the rehearsal report](agent-memory-rehearsal.md). Automatic reconciliation
was observed and manually reviewed. The PII exclusion check failed against the
configured service; email-detector configuration must be checked before presenting
that scenario as successful. No service policy was changed by this build.
