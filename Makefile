.PHONY: up redis model seed serve build dev eval fmt lint test down

up: redis model build ## Prepare once, then open the comparison app
	uv run python -m seed.load --if-needed
	uv run python -m app.runtime --port $(or $(PORT),8000)

redis: ## Preserve an existing service container and its data
	docker compose up -d --no-recreate --wait

model: ## Download the pinned local model once; verify cached files afterwards
	uv run python -m app.embeddings

seed: ## Bootstrap bundled source records; refuse to overwrite managed live catalogues
	uv run python -m seed.load

serve: ## Start the prepared backend and built frontend
	uv run python -m app.runtime --port $(or $(PORT),8000)

build:
	npm --prefix web ci
	npm --prefix web run build

dev: ## Frontend dev server; backend uses port 8000
	npm --prefix web run dev

eval:
	uv run python -m eval.run --check

fmt:
	uv run ruff format app seed/load.py eval tests scripts/prepare_cameras.py scripts/search_load.py
	uv run ruff check --fix app seed/load.py eval tests scripts/prepare_cameras.py scripts/search_load.py

lint:
	uv run ruff check app seed/load.py eval tests scripts/prepare_cameras.py scripts/search_load.py
	uv run mypy app seed/load.py eval scripts/prepare_cameras.py scripts/search_load.py

test:
	uv run pytest -q

down: ## Stop the container without deleting data
	docker compose stop
