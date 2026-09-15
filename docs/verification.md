# Verification


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
