# Camera Search Lab

Search the camera-related catalogue with a calm, single-list view, powered by
RedisVL and a local embedding model. Open **Compare methods** to show any
combination of Basic, Full-text, Vector, and Hybrid side by side. Basic is
selected by default; each method shows up to five products. On mobile, swipe
across the comparison area to see additional methods.

**Basic** is a case-insensitive literal substring match on original product
titles, sorted alphabetically by title then product ID. It scans the loaded
catalogue, without relevance ranking or a Redis search command. All methods
respect the same exact brand filter. The UI fetches all four result sets once;
changing the checkboxes changes the view without rerunning the search. The API
keeps its three-method default unless `include_basic: true` is requested.

**Autocomplete** has its own toggle, enabled by default. It suggests query text;
it is not a result-ranking method. Disabling it stops suggestion requests.
Select a product to open its evidence in a side panel, including method positions,
source text, verified hybrid contributions, and original source fields.

## Run locally

### Prerequisites

Use Bash or Zsh for the commands below. The fresh-checkout setup has been verified
on macOS with Python 3.12; other operating systems have not yet been validated.
No GPU or model API key is required. The product dataset is already bundled.

| Install | Requirement |
|---|---|
| [Git](https://git-scm.com/install/) | Clone the repository |
| Make | On macOS, install [Apple's command line tools](https://developer.apple.com/xcode/resources/); on Linux, use your distribution's package manager, such as Ubuntu's [make package](https://packages.ubuntu.com/noble/make) |
| [Docker](https://docs.docker.com/get-started/get-docker/) | A running Docker engine and Compose v2; start Docker Desktop if you use it |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Install Python dependencies and run the backend |
| [Python](https://docs.astral.sh/uv/guides/install-python/) | 3.12+; uv can install Python 3.12 with `uv python install 3.12` |
| [Node.js and npm](https://nodejs.org/en/download) | Node.js 22.18+ with npm |

Check your tools before starting. `docker info` must reach the running engine:

```bash
git --version
make --version
docker compose version
docker info
uv --version
node --version
npm --version
```

### Clone and start

While this repository is private, your GitHub account needs access. Accept the
repository invitation and authenticate Git with that account before cloning.

```bash
git clone --branch search https://github.com/s-agbede/redis-iris-webinars.git
cd redis-iris-webinars
cp .env.example .env
make up
```

Copy `.env.example` only for a new checkout; preserve an existing `.env`. Run all
subsequent commands from the repository root. If the default ports are already
occupied, use the [port settings below](#ports) before running `make up`.

The first run installs dependencies, starts Redis, downloads the pinned MiniLM
ONNX model (about 90 MB), builds the frontend and indexes 8,472 passages from
2,317 products. Internet access is needed for the initial downloads. Allow several
minutes for CPU embedding; progress appears as `Indexed 128/8,472 passages` and
continues until the index is complete. Wait for `Application startup complete`,
then open [the lab](http://127.0.0.1:8000). Keep this terminal running.

### Verify readiness and try a search

In a second terminal, check [readiness](http://127.0.0.1:8000/api/health) in your
browser or run this command if you have curl:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/api/health
```

With the bundled data and default passage settings, the expected response is:

```json
{"status":"ready","products":2317,"passages":8472}
```

Search for **`sony zv e10`** in the lab. Open **Compare methods** and select Full-text, Vector, and Hybrid to see
them alongside the default Basic list.
Try **`Sony`** with Basic enabled to compare literal title matching. Select a
product to compare its positions and source passages.
Then try **`a compact camera for filming myself`** to compare how the methods
handle a described need. The interactive [API docs](http://127.0.0.1:8000/docs)
also let you try `POST /api/compare` with `{"query":"sony zv e10"}`.

An HTTP 503 response means setup is incomplete or Redis is unavailable. Read its
error message and follow [troubleshooting](#troubleshooting) below.

### Ports

If app port 8000 is occupied, run `make up PORT=8001` and use port 8001 in the
browser, readiness and API URLs above. For an already prepared app, use
`make serve PORT=8001`.

If Redis port 6379 is occupied, set **both** values in `.env` before the first
startup:

```dotenv
REDIS_PORT=6381
REDIS_URL=redis://localhost:6381
```

`REDIS_PORT` controls Docker's host port; `REDIS_URL` tells the Python app where
to connect. Keep them aligned. To change the port of an existing project container,
stop the app, update `.env`, and run `docker compose up -d --wait redis` to apply
the change, then `make serve`. The named Redis data volume is preserved.

### Stop and restart

Press **Ctrl+C** in the server terminal to stop the app. Redis keeps running;
`make down` stops it while preserving the data volume. To restart after setup:

```bash
make redis
make serve
```

After preparation, `make serve` runs entirely locally. Serving and seeding do not
download a model. An offline restart requires the Docker image, Python dependencies,
model files, indexed data and frontend build to be present. Later `make up` runs
verify the cached model and reuse a matching index, but also run npm installation,
which may need network access.

`make up` keeps an existing Compose service container; it does not automatically
upgrade an older Redis container. The loader requires Redis 8.4+ for native hybrid
search. Compose pins the tested Redis 8.6.2 image digest.

### Edit the app

Complete `make up` once, then stop its server with Ctrl+C. Keep Redis running.
Use two terminals, both in the repository root.

**Terminal 1: backend with automatic reload**

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2: frontend with hot reload**

```bash
make dev
```

Open the URL printed by Vite, normally [http://localhost:5173](http://localhost:5173).
The frontend forwards `/api` and `/photos` to backend port **8000**, as configured
in [web/vite.config.ts](web/vite.config.ts). If you choose another backend port,
update both proxy targets and restart `make dev`; `PORT=8001` does not change them.
The backend reads `.env`; restart it after changing settings. After editing the
frontend, run `make build` before returning to the single-server `make serve` flow.

### Commands

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

### Troubleshooting

| Symptom | What to do |
|---|---|
| Clone says `Repository not found` or authentication fails | Check the repository URL, accept your GitHub invitation, and authenticate Git as an account with access. |
| `make`, `uv`, `node`, `npm` or `docker` is not found | Install the missing prerequisite above, open a new terminal and repeat its version check. |
| Docker cannot connect, or the container is not healthy | Start Docker Desktop or your Docker engine, check `docker info`, then inspect `docker compose ps` and `docker compose logs redis`. Retry `make redis` after resolving the error. |
| `Address already in use`, or Redis connection refused | Follow [Ports](#ports). Check that `REDIS_PORT` and the port in `REDIS_URL` agree and that Redis is running. |
| Model download fails, or the local model is missing | Check network/proxy access to Hugging Face and rerun `make model`. If you set `MODEL_PATH`, it must contain the exact pinned files; unset it to use the standard download/cache flow. Restart the app after preparation. |
| `/api/health` returns 503, or the index is missing/incomplete/mismatched | Read the response body. Stop the app, ensure Redis is running, run `make model` and `make seed`, then restart with `make serve`. Reseeding replaces this namespace's passage index. |
| Redis reports that native hybrid search is unsupported | Stop the app and run `docker compose up -d --wait redis` to apply the pinned image, then `make seed` and `make serve`. The named data volume is preserved. |
| The root URL opens API docs, or the frontend is out of date | Stop the server, run `make build`, then restart `make serve`. In development, open Vite's URL and check its backend proxy port. |

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
- [Sample passages from two real catalogue products](docs/sample-passages.md)
- [Tests and verification](docs/verification.md)
- [15-minute webinar walkthrough and future episodes](docs/webinar.md)
- [Recorded learning audit](docs/search-learning-audit.md)
- [Historical experiments and removed files](docs/history.md)

The current app implements search comparison. Agent memory, context retrieval,
and semantic caching are future extensions.
