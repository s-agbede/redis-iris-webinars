.PHONY: up down seed dev eval fmt lint test clean

up: ## Start Redis, seed the indexes, run the app
	docker compose up -d --wait
	uv run python -m seed.load
	uv run uvicorn app.main:app --reload --port 8000

down:
	docker compose down -v

seed: ## Rebuild the Redis indexes from committed seed artifacts
	uv run python -m seed.load

dev: ## Frontend dev server with hot reload (run alongside `make up`)
	cd web && npm install && npm run dev

eval: ## Retrieval quality. CONFIG=vector|filtered|hybrid|all
	uv run python -m eval.run --config $(or $(CONFIG),all)

fmt:
	uv run ruff format . && uv run ruff check --fix .

lint:
	uv run ruff check . && uv run mypy app seed eval

test:
	uv run pytest -q

clean: down
	rm -rf .venv web/node_modules web/dist
