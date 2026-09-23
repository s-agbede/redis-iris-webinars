# Local development and search reference

New to this project? Start with the [agent-memory quickstart](agent-memory-quickstart.md).
This reference covers search controls, local setup, ports, development commands
and worker recovery.

## Original search lab

Search the camera-related catalogue with a calm, single-list view, powered by
RedisVL and a local embedding model. Open **Compare methods** to show any
combination of Basic, Full-text, Vector, and Hybrid side by side. Basic is
selected by default; each method shows up to five products. On mobile, swipe
across the comparison area to see additional methods.

**Basic** is a case-insensitive literal substring match on original product
titles, sorted alphabetically by title then product ID. It scans the loaded
catalogue, without relevance ranking or a Redis search command. All methods
respect the same brand filter; API clients can also supply color filters. The UI fetches all four result sets once;
changing the checkboxes changes the view without rerunning the search. The API
keeps its three-method default unless `include_basic: true` is requested.

**Autocomplete** has its own toggle, enabled by default. It suggests query text;
it is not a result-ranking method. Disabling it stops suggestion requests.

**Query understanding** has a separate switch under **Advanced**, enabled by
default in the shop. It uses conservative local rules to recognize one leading
catalogue brand (for example, `Sony camera`) and apply it as a metadata filter.
It does not call an LLM or rewrite the query. Turn it off to compare retrieval
without an inferred brand constraint; manual filters and lexical normalization
remain active. Switching it reruns the current search. Removing an inferred-brand
chip dismisses that inference for the current query; switching understanding
back on enables inference again. API clients control this with `interpret_brand`
(default `false`).

Select a product to open its evidence in a side panel, including method positions,
source text, verified hybrid contributions, and original source fields.

## Run locally

### Prerequisites

Use Bash or Zsh for the commands below. The fresh-checkout setup has been verified
on macOS with Python 3.12; other operating systems have not yet been validated.
No GPU or model API key is required for search. For chat credentials, follow the
[agent-memory quickstart](agent-memory-quickstart.md#2-connect-the-memory-service-and-chat-model).
The product dataset is already bundled.

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
git clone --branch agent-memory https://github.com/s-agbede/redis-iris-webinars.git
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
minutes for CPU embedding. The loader processes one product at a time and prints
`Indexed 8,472 passages` after loading all passages; it does not print incremental
batch progress. Wait for `Application startup complete`,
then open [the shop](http://127.0.0.1:8000) or
[the search lab](http://127.0.0.1:8000/?view=compare). Keep this terminal running.
These commands use the `agent-memory` branch. If Git cannot find that remote
branch, ask the presenter for the published webinar branch.

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

To demonstrate metadata filtering, search for **`camera`**, then select
**Brand: Sony** under **Advanced → Filter products**. Every method now searches
within that constraint.
Open a result's **Redis commands for this comparison** to see the filters in
Full-text, Vector and both branches of Hybrid. **Clear filters** searches the
whole catalogue again for this `camera` query; changing the query keeps the selected
brand. For comparison, clear the filter, turn **Query understanding** off, and type
`Sony camera`: query words influence matching and relevance, while a selected
brand restricts eligible products.

Brand values match the source exactly. Dropdown counts describe the whole
catalogue, not the current search results. The API additionally accepts color
filters; the browser has no color selector. For example, this request combines
the Sony brand with white color metadata:

```json
{"query":"camera","brands":["Sony"],"colors":["white"],"include_basic":true}
```

API color filtering merges capitalization and whitespace variants, but does not
infer colors from titles or photos. Products with missing color metadata are
excluded when a color is supplied.

If upgrading an unmanaged checkout from the brand-only schema, stop the app and
run `make seed`, `npm --prefix web run build`, then `make serve` (add `PORT=8001`
if needed). The new color field requires rebuilding the camera index; `make up`
also rebuilds an old bootstrap index. Managed catalogues are preserved: use a
compatible live rebuild or an unused `NAMESPACE` for an independent upgraded demo.

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

After preparation, catalogue search runs entirely locally; chat still calls
Redis Agent Memory and OpenAI over the network. Serving and seeding do not
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

**Terminal 1: API and worker with automatic crash recovery**

```bash
make serve
```

**Terminal 2: frontend with hot reload**

```bash
make dev
```

Open the URL printed by Vite, normally [http://localhost:5173](http://localhost:5173).
The frontend forwards `/api` and `/photos` to backend port **8000**, as configured
in [web/vite.config.ts](../../web/vite.config.ts). If you choose another backend port,
update both proxy targets and restart `make dev`; `PORT=8001` does not change them.
The backend reads `.env`; restart it after changing settings. After editing the
frontend, run `make build` before returning to the single-server `make serve` flow.

### Commands

| Command | Purpose |
|---|---|
| `make model` | Download missing pinned model files; verify and reuse cached files |
| `make redis` | Start the local Redis service and wait for readiness |
| `make seed` | Bootstrap bundled products and passages before live catalogue management starts |
| `make serve PORT=8001` | Serve the prepared API and built frontend |
| `make build` | Install locked frontend dependencies and build strict TypeScript |
| `make dev` | Vite frontend with hot reload; API proxy targets port 8000 |
| `make eval` | Run 10 product-focused queries across four methods, checking full-text/hybrid target ranks |
| `make lint` / `make test` | Python static checks / test suite |
| `make down` | Stop Compose services while preserving their data |

`make up` reuses a matching serving index and its maintained passage count, including
saved demo products, paused changes and deployment state. `make seed` is a bootstrap
operation: once the namespace has a change stream or deployment registry, it refuses
to overwrite that live catalogue. Rebuild a running shop through **Manage shop → Safe
deployment**. For a separate clean demo, choose an unused namespace, for example
`NAMESPACE=camera_fresh make up`, and use that same value on subsequent commands.
If a managed namespace cannot start because its index or manifest is damaged, restore
its saved state or use a fresh namespace; bootstrap does not repair it by deleting data.

The app checks the serving index and its manifest at startup and reads current product
records from Redis. A missing model,
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
| `/api/health` returns 503, or the index is missing/incomplete/mismatched | Read the response body. Ensure Redis and the pinned model are available. Bootstrap an unmanaged namespace with `make seed`; restore a damaged managed namespace or choose an unused `NAMESPACE`. Restart with `make serve` using the same namespace. |
| Redis reports that native hybrid search is unsupported | Stop the app and run `docker compose up -d --wait redis` to apply the pinned image, then restart with `make up`. The named data volume is preserved; managed catalogues are never overwritten by bootstrap. |
| The root URL opens API docs, or the frontend is out of date | Stop the server, run `make build`, then restart `make serve`. In development, open Vite's URL and check its backend proxy port. |

## Understand the code

The backend keeps the search and indexing modules flat, with the conversational
adviser grouped under `app/shop/`. Start with the feature you want to change:

```text
app/
  main.py               # HTTP application and startup
  runtime.py            # Supervises API and worker processes
  worker.py             # Indexing-worker process entry point
  queries.py            # Three RedisVL retrieval query builders
  search.py             # Search execution and result assembly
  indexing.py           # Shared passage and embedding preparation
  sync.py               # Consume catalogue changes and update indexes
  freshness_routes.py   # Catalogue-change and retry controls
  shop/                 # Conversational camera adviser
    service.py          # Conversation flow and tool orchestration
    routes.py           # HTTP endpoints and service construction
    models.py           # Typed requests, context and responses
    llm.py              # OpenAI model transport
    memory.py           # Redis Agent Memory boundary
    playbook.py         # Published guidance retrieval
    settings.py         # Optional adviser configuration
```

Follow the request path for the feature you want to explore:

| Read | Responsibility |
|---|---|
| [app/main.py](../../app/main.py) | FastAPI endpoints, readiness, and static frontend |
| [app/shop/service.py](../../app/shop/service.py) | Camera adviser conversation and tool flow |
| [app/shop/routes.py](../../app/shop/routes.py) | Adviser HTTP API and dependency construction |
| [app/runtime.py](../../app/runtime.py) | Starts and restarts API and worker processes |
| [app/sync.py](../../app/sync.py) | Stream consumption, passage updates and recovery |
| [app/queries.py](../../app/queries.py) | Full-text, vector, and hybrid RedisVL query builders for the live demo |
| [app/search.py](../../app/search.py) | Embedding, shared filters, query execution, and product ranking |
| [app/evidence.py](../../app/evidence.py) | Literal text matches and verified hybrid contributions |
| [app/catalog.py](../../app/catalog.py) | Original records, text cleaning, bounded passages |
| [app/embeddings.py](../../app/embeddings.py) | Pinned local model and embedding generation |
| [seed/load.py](../../seed/load.py) | Load records and build the [passage index](../../schemas/passages.yaml) |
| [web/src/main.tsx](../../web/src/main.tsx) | React comparison page and shared inspector |

`app/models.py` defines the typed boundaries; `app/settings.py` holds configuration.
`tests/` covers the backend, and `web/src/*.test.mjs` covers frontend logic.
`seed/cameras/` holds the canonical source bundle and provenance; `seed/photos/`
holds attributed reference photos. `scripts/prepare_cameras.py` reproduces the
source subset. `eval/` contains assistant-reviewed cases and recorded observations. See [evaluation guide](../../eval/README.md) for targets, checks, and limitations.

## Guides

Start with the [documentation index](../README.md) for architecture, demo runbooks,
presentation material and historical notes.

- [Dataset, limitations, photo attribution, and reproduction](dataset.md)
- [Retrieval architecture, score interpretation, and timing](../architecture/search.md)
- [Sample passages from two real catalogue products](sample-passages.md)
- [Tests and verification](verification.md)
- [15-minute webinar walkthrough and future episodes](../demos/search.md)
- [Recorded learning audit](../archive/search-learning-audit.md)
- [Historical experiments and removed files](../archive/history.md)

The current app implements search comparison and three working production-pattern
demos: freshness, measured traffic and safe index replacement. See the
[production demo runbook](../demos/production.md). The conversational adviser also
implements the [agent-memory demo](../demos/agent-memory.md), using external RAM
and model services when configured. Semantic caching and the dedicated context-retriever
session remain future extensions.

### Worker recovery and failed changes

`make serve` (also used by `make up`) starts `app.runtime`, a local supervisor.
It runs FastAPI and `app.worker` in separate processes, restarting an exited child
after two seconds. Ctrl-C intentionally stops both children. The supervisor itself
is not an OS service: after a machine reboot or supervisor failure, run `make serve`
again. Each process loads its own local model, so isolation uses additional memory.
Running `uvicorn app.main:app` directly starts only the API; use
`uv run python -m app.worker` separately if managing processes yourself.

Redis has append-only persistence, a named data volume and the Compose restart
policy `unless-stopped`. Apply Compose changes with `docker compose up -d redis`.

Product processing failures get three attempts, with 5s then 10s backoff.
Unacknowledged events are reclaimable after 5s idle; an expired worker lock can
add up to 60s after a hard crash. Redis connection failures use reconnect backoff
(up to 30s) and do not consume a product's retry budget.

Exhausted events move to `<namespace>:changes:failed`, recording the original event
ID, product ID, error and attempts. Manage shop shows the failed count and the latest
50 failures. Fix the cause and click **Retry** to enqueue the product's current state
with a fresh retry budget. Failed changes block deployment validation/cutover until
resolved. Acknowledgement and dead-letter transfer are queued together, as are index
writes and successful acknowledgement; Redis transactions do not roll back command
runtime errors. Monitor Redis errors as well as the failure list.
