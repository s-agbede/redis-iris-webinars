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

## Understand the code

Start with the request path, then follow how its data is prepared:

| Read | Responsibility |
|---|---|
| [app/main.py](app/main.py) | FastAPI endpoints, readiness, and static frontend |
| [app/search.py](app/search.py) | Shared constraints, three retrieval methods, product ranking |
| [app/evidence.py](app/evidence.py) | Literal text matches and verified hybrid contributions |
| [app/catalog.py](app/catalog.py) | Original records, text cleaning, bounded passages |
| [app/embeddings.py](app/embeddings.py) | Pinned local model and embedding generation |
| [seed/load.py](seed/load.py) | Load records and build the [passage index](schemas/passages.yaml) |
| [web/src/main.tsx](web/src/main.tsx) | React comparison page and shared inspector |

`app/models.py` defines the typed boundaries; `app/settings.py` holds configuration.
`tests/` covers the backend, and `web/src/*.test.mjs` covers frontend logic.
`seed/cameras/` holds the canonical source bundle and provenance; `seed/photos/`
holds attributed reference photos. `scripts/prepare_cameras.py` reproduces the
source subset. `eval/` contains reviewed cases and recorded observations.

## Guides

- [Dataset, limitations, photo attribution, and reproduction](docs/dataset.md)
- [Retrieval architecture, score interpretation, and timing](docs/architecture.md)
- [Tests and verification](docs/verification.md)
- [15-minute webinar walkthrough and future episodes](docs/webinar.md)
- [Recorded learning audit](docs/search-learning-audit.md)
- [Historical experiments and removed files](docs/history.md)

The current app implements search comparison. Agent memory, context retrieval,
and semantic caching are future extensions.
