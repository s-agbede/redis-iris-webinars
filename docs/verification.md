# Verification


```bash
make lint
make test
npm --prefix web run build
node --experimental-strip-types --test web/src/*.test.mjs
TEST_REDIS_URL=redis://localhost:6379 uv run pytest -q tests/test_live_camera_flow.py
```

The live test needs the prepared model and camera index. It checks all three
methods, combined brand and color constraints (including Basic), unique products, source-passage offsets,
empty filters, literal-overlap offsets, verified native fusion arithmetic and
hybrid's zero lexical contribution when no lexical terms match. The ordinary
suite skips that integration check unless `TEST_REDIS_URL` is set. A real-model
unit check also skips if its pinned files have not been prepared.

For the browser flow, open Advanced and select Brand: Sony before searching for
`camera`, then enable all four methods. Every result should show Sony metadata.
Inspect the Redis commands to verify brand constraints in both Hybrid branches.
Change the query and confirm the filters persist, then use Clear filters and
confirm the brand control resets and results update. Try a query and brand with no
matching products and verify the empty states suggest clearing filters. Check this at
desktop width and at 390px, with no page-level horizontal overflow.

Color filtering is API-only. Use `POST /api/compare` with
`{"query":"camera","brands":["Sony"],"colors":["white"],"include_basic":true}` and
check that results have Sony/White metadata and both Hybrid branches include the
color constraint. The live integration test also covers this combined filter.
